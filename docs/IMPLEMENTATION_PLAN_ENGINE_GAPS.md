# Plan de Implementacion — Callable, IRS y Scheduled en What-If

> Documento de referencia. Actualizar conforme se avance.
> Ultima revision: 2026-03-01

---

## 0. Arquitectura actual (pipeline)

```
Frontend (LoanSpec camelCase)
    |
    v
Router whatif.py :: _loan_spec_from_item()     --> convierte a LoanSpec (snake_case)
    |
    v
Decomposer :: decompose_loan()                --> genera 1-5 motor rows (DataFrame)
    |
    v
EVE :: build_eve_cashflows()                   --> genera cashflows por posicion
NII :: compute_nii_from_cashflows()            --> proyecta 12M de income/expense
    |
    v
EVE Analytics :: compute_eve_full()            --> descuenta y agrupa en buckets
NII Result :: aggregate_nii                    --> escalar NII total
```

Cada capa es independiente. Los cambios se propagan hacia abajo sin romper
las capas superiores. Todos los gaps se resuelven DENTRO de este pipeline,
no en paralelo.

---

## 1. CALLABLE INSTRUMENTS

### 1.1 Que es

Un instrumento callable tiene una fecha (`call_date`) en la que el emisor
puede cancelar anticipadamente. Para IRRBB regulatorio se usa el enfoque
**determinista**: se asume que la call se ejerce siempre (worst-case).
Esto equivale a truncar los cashflows en `call_date` y devolver el principal
restante en esa fecha.

### 1.2 Impacto si no se implementa

Un bono callable a 5Y con maturity 10Y se valora como 10Y puro. La duracion
y sensibilidad EVE estan sobreestimadas. Severidad: ALTA.

### 1.3 Archivos a modificar

#### A. Motor positions — anadir campo `call_date`

**Archivo**: `backend/engine/io/positions_reader.py`
**Linea ~23**: Anadir `"call_date"` al set `_DATE_COLUMNS`:

```python
# ANTES
_DATE_COLUMNS = {"start_date", "maturity_date", "next_reprice_date"}

# DESPUES
_DATE_COLUMNS = {"start_date", "maturity_date", "next_reprice_date", "call_date"}
```

Esto hace que el reader parsee automaticamente `call_date` como date cuando
existe en el CSV/Excel de entrada. No rompe nada si la columna no existe.

#### B. EVE — truncar cashflows en call_date (OPTIMIZADO)

**Archivo**: `backend/engine/services/eve.py`

**OPTIMIZACION CLAVE**: En lugar de modificar las 8 funciones generadoras
individualmente, interceptamos en el UNICO punto de entrada:
`build_eve_cashflows()` (linea ~1218).

Esta funcion recibe el DataFrame completo de posiciones y lo agrupa por
`source_contract_type` via `_positions_by_supported_type()` (linea ~1232).
Esa funcion ya modifica el DataFrame (por ejemplo, para NMD asigna
maturity sintetica a 30Y). Aplicamos el mismo patron para callable.

**Implementacion** — anadir ANTES de la llamada a `_positions_by_supported_type()`:

```python
def build_eve_cashflows(positions: pd.DataFrame, ...) -> pd.DataFrame:
    # ... validaciones existentes ...

    # ── Callable: truncar maturity_date a call_date ──────────────────
    if "call_date" in positions.columns:
        positions = positions.copy()  # no mutar el original
        call_col = pd.to_datetime(positions["call_date"], errors="coerce")
        mat_col  = pd.to_datetime(positions["maturity_date"], errors="coerce")
        mask = call_col.notna() & (call_col < mat_col)
        positions.loc[mask, "maturity_date"] = positions.loc[mask, "call_date"]
    # ─────────────────────────────────────────────────────────────────

    groups = _positions_by_supported_type(positions)
    # ... resto sin cambios ...
```

**Por que esto funciona**: Todas las funciones generadoras (_extend_fixed_bullet,
_extend_variable_linear, etc.) leen `maturity_date` del row iterando sobre
el DataFrame. Al truncarlo ANTES del dispatch, todas las funciones ven
automaticamente la maturity correcta. Cero cambios en las 8 funciones.

**Resultado**: 1 modificacion en lugar de 8. Mismo resultado.

#### C. NII — truncar proyecciones en call_date (OPTIMIZADO)

**Archivo**: `backend/engine/services/nii.py`

Mismo patron. Hay dos entry points para NII:

1. `run_nii_12m_base()` (linea ~155) — usado en pipeline tradicional
2. `compute_nii_from_cashflows()` (linea ~979) — usado en What-If

En ambas funciones, aplicar la misma truncacion al principio:

```python
def run_nii_12m_base(positions: pd.DataFrame, ...) -> float:
    # ── Callable: truncar maturity_date a call_date ──────────────────
    if "call_date" in positions.columns:
        positions = positions.copy()
        call_col = pd.to_datetime(positions["call_date"], errors="coerce")
        mat_col  = pd.to_datetime(positions["maturity_date"], errors="coerce")
        mask = call_col.notna() & (call_col < mat_col)
        positions.loc[mask, "maturity_date"] = positions.loc[mask, "call_date"]
    # ─────────────────────────────────────────────────────────────────
    # ... resto sin cambios ...
```

Y lo mismo en `compute_nii_from_cashflows()` para el `positions_df`.

**Resultado**: 2 modificaciones en lugar de 8. Mismo resultado.

**Total EVE + NII**: 3 puntos de insercion (en lugar de 16 del plan anterior).

#### D. Decomposer — mapear call_date del LoanSpec

**Archivo**: `backend/engine/services/whatif/decomposer.py`
(o `backend/almready/services/whatif/decomposer.py` segun la rama)

**Paso 1**: Anadir campo al dataclass `LoanSpec` (linea ~80):

```python
    call_date: date | None = None
```

**Paso 2**: Anadir parametro a `_motor_row()` (linea ~107):

```python
def _motor_row(
    ...,
    cap_rate: float | None = None,
    call_date: date | None = None,      # NUEVO
) -> dict:
    return {
        ...,
        "cap_rate": cap_rate,
        "call_date": call_date,          # NUEVO
    }
```

**Paso 3**: Pasar `call_date` en todas las llamadas a `_motor_row()` dentro
de `_decompose_simple()` y `_decompose_mixed()`. Buscar cada llamada
`_motor_row(...)` y anadir `call_date=spec.call_date`.

NOTA: NO pasar call_date a las posiciones offset (grace offsets, mixed
cancel legs). Estos son sinteticos internos, no instrumentos callable.

#### E. Schema Pydantic — anadir campo

**Archivo**: `backend/app/schemas.py`
**Modelo**: `LoanSpecItem` (linea ~306)

```python
    call_date: str | None = None       # ISO date, e.g. "2029-06-15"
```

#### F. Router — mapear campo

**Archivo**: `backend/app/routers/whatif.py`
**Funcion**: `_loan_spec_from_item()` (linea ~49)

Anadir al return `LoanSpec(...)`:

```python
    call_date=date.fromisoformat(item.call_date) if item.call_date else None,
```

#### G. Frontend — ya captura callDate

Los templates de bonos, covered bonds, subordinados y wholesale ya exponen
`callDate` en `src/types/whatif.ts`. El campo se mapea en
`src/components/whatif/shared/constants.ts :: buildModificationFromForm()`.

**Unico cambio necesario**: asegurar que `buildModificationFromForm()` incluya
`callDate` en el payload enviado al backend (campo `call_date` en snake_case).

### 1.4 Tests — Bateria completa

Archivo: `backend/engine/tests/test_callable.py`

#### Tests unitarios EVE (5 tests)

```
test_fixed_bullet_callable_truncates_cashflows
    Posicion: fixed_bullet, 100M, 10Y, coupon 5%, call_date a 5Y.
    Verificar: cashflows generados solo hasta 5Y.
    Verificar: principal 100M se devuelve en call_date, no en maturity.
    Verificar: numero de cupones = 5 (no 10).

test_variable_bullet_callable_truncates_cashflows
    Posicion: variable_bullet, 50M, 7Y, EURIBOR 6M + 100bp, call_date a 3Y.
    Verificar: resets solo hasta 3Y.
    Verificar: principal 50M se devuelve en call_date.

test_fixed_linear_callable_truncates_amortization
    Posicion: fixed_linear, 100M, 10Y, call_date a 6Y.
    Verificar: amortizacion lineal genera principal flows solo hasta 6Y.
    Verificar: outstanding at 6Y se devuelve de golpe en call_date.

test_fixed_annuity_callable_truncates_payments
    Posicion: fixed_annuity, 100M, 15Y, coupon 4%, call_date a 8Y.
    Verificar: pagos anuales (P+I) solo hasta 8Y.
    Verificar: outstanding restante al ano 8 se devuelve en call_date.

test_no_call_date_unchanged
    Posicion: fixed_bullet, 100M, 10Y, SIN call_date.
    Verificar: cashflows identicos a los que genera el motor hoy.
    Verificar: resultado EVE no cambia (test de regresion).
```

#### Tests unitarios NII (3 tests)

```
test_nii_callable_within_horizon
    Posicion: fixed_bullet, 100M, 3Y, coupon 5%, call_date a 6M.
    Horizonte NII: 12M.
    Verificar: interes solo por 6 meses (no 12).
    Verificar: si balance_constant=True, renewal empieza a los 6M.

test_nii_callable_beyond_horizon
    Posicion: fixed_bullet, 100M, 10Y, coupon 5%, call_date a 8Y.
    Horizonte NII: 12M.
    Verificar: NII identico a sin call (call > horizon, no afecta NII 12M).

test_nii_variable_callable_repricing
    Posicion: variable_bullet, 100M, 5Y, EURIBOR + 50bp, call_date a 2Y.
    Verificar: repricing solo durante 2 anos.
```

#### Tests de equivalencia numerica (3 tests)

```
test_callable_5y_equals_pure_5y_eve
    Comparar EVE de:
    - Bono 10Y callable a 5Y, coupon 4%
    - Bono 5Y puro, coupon 4%
    Resultado: EVE debe ser IDENTICO (assertAlmostEqual, places=10).

test_callable_5y_equals_pure_5y_nii
    Mismo par de posiciones.
    Resultado: NII 12M debe ser IDENTICO.

test_call_date_after_maturity_ignored
    Posicion: fixed_bullet, 5Y maturity, call_date a 8Y.
    Verificar: call_date se ignora (> maturity).
    Verificar: EVE identico a posicion sin call_date.
```

#### Tests edge cases (4 tests)

```
test_call_date_equals_analysis_date_skip
    call_date = analysis_date.
    Verificar: posicion se salta (ya vencida/called).

test_call_date_before_analysis_date_skip
    call_date < analysis_date.
    Verificar: posicion se salta.

test_call_date_equals_maturity_no_effect
    call_date == maturity_date.
    Verificar: sin efecto, maturity_date no cambia.

test_missing_call_date_column_no_crash
    DataFrame sin columna call_date.
    Verificar: funciona como siempre, sin error.
```

#### Tests decomposer (3 tests)

```
test_decompose_callable_bond_has_call_date
    LoanSpec con call_date.
    Verificar: DataFrame resultante tiene columna call_date.
    Verificar: valor correcto en la posicion principal.

test_decompose_callable_offset_no_call_date
    LoanSpec con grace + call_date.
    Verificar: posiciones offset NO tienen call_date (son sinteticas).

test_decompose_no_call_date_column_absent_or_null
    LoanSpec sin call_date.
    Verificar: call_date es None en el DataFrame.
```

#### Test integracion end-to-end (1 test)

```
test_whatif_callable_bond_full_pipeline
    1. Crear LoanSpec: covered bond, 200M, 10Y, coupon 3.5%, call a 5Y.
    2. Decompose → verificar motor rows con call_date.
    3. build_eve_cashflows → verificar cashflows terminan a 5Y.
    4. compute_eve_full → verificar EVE scalar.
    5. Comparar con bono 5Y puro → deben ser iguales.
```

### 1.5 Estimacion de complejidad (revisada)

- **Esfuerzo**: BAJO.
  - 1 campo nuevo en 4 sitios (LoanSpec, _motor_row, LoanSpecItem, router)
  - 3 bloques de truncacion (build_eve_cashflows, run_nii_12m_base, compute_nii_from_cashflows)
  - 0 cambios en funciones generadoras
- **Riesgo**: MUY BAJO. La truncacion es vectorizada en pandas, no toca la
  logica interna de ningun generador.
- **Lineas de codigo**: ~30 nuevas, ~6 modificadas.
- **Tests**: 19 tests.

---

## 2. IRS (INTEREST RATE SWAPS)

### 2.1 Que es

Un IRS es un derivado que intercambia flujos de interes entre una pata fija
y una pata variable, sin intercambio de principal. Para IRRBB:
- Pata fija: genera cashflows de interes a tasa fija
- Pata variable: genera cashflows de interes a indice + spread
- NO hay flujos de principal (nocional es solo referencia)

Modelizacion: dos posiciones sinteticas con sides opuestos y `notional`
igual pero sin amortizacion de principal (solo interes).

### 2.2 Impacto si no se implementa

No se pueden simular coberturas con IRS en What-If. Es uno de los use cases
principales de la herramienta. Severidad: ALTA.

### 2.3 Estado actual

El template `irs-hedge` YA EXISTE en el frontend (`src/types/whatif.ts`,
lineas 713-739) con todos los campos necesarios:
- payingLeg (Fixed / Floating)
- fixedRate, notional, termYears
- variableIndex, spread
- paymentFreq, daycount

Lo que falta es que el decomposer sepa generar las dos patas.

### 2.4 Archivos a modificar

#### A. Decomposer — nueva funcion `_decompose_irs()`

**Archivo**: `backend/engine/services/whatif/decomposer.py`

**Paso 1**: Ampliar `LoanSpec` (linea ~65):

```python
    rate_type: Literal["fixed", "variable", "mixed", "irs"] = "fixed"
    paying_leg: Literal["fixed", "floating"] | None = None   # solo para IRS
```

**Paso 2**: Nueva funcion (insertar antes de `decompose_loan()`):

```python
def _decompose_irs(spec: LoanSpec, start: date, maturity: date) -> list[dict]:
    """Descompone un IRS en dos patas sinteticas (SOLO 2 posiciones).

    - Pata fija: fixed_bullet con el notional del swap
    - Pata variable: variable_bullet con el notional del swap
    - Sides opuestos: si el banco PAGA fijo, pata fija es L y variable es A

    Principal at maturity se cancela automaticamente:
    - Pata fija (L): genera principal = sign(-1) * notional = -100M
    - Pata variable (A): genera principal = sign(+1) * notional = +100M
    - Neto: -100M + 100M = 0.  Sin offsets necesarios.

    Esto funciona porque ambas patas tienen el MISMO notional, la MISMA
    maturity, y sides OPUESTOS. El convenio de signos del motor
    (side_sign: A=+1, L=-1) garantiza la cancelacion exacta.

    Resultado neto: 2 posiciones (NO 4)
    - fixed_bullet (interes fijo + principal que se cancela)
    - variable_bullet (interes variable + principal que se cancela)

    Ventaja vs enfoque con offsets:
    - 50% menos posiciones → 50% menos calculos EVE/NII
    - Menos codigo, menos tests, misma precision
    - Zero engine changes
    """
    spread = spec.spread_bps / 10_000
    reprice_freq = spec.repricing_freq or spec.payment_freq
    pid = spec.id_prefix

    # Determinar sides segun que pata paga el banco
    if spec.paying_leg == "fixed":
        fixed_side = "L"    # banco paga fijo = pasivo
        float_side = "A"    # banco recibe variable = activo
    else:
        fixed_side = "A"    # banco recibe fijo = activo
        float_side = "L"    # banco paga variable = pasivo

    rows = []

    # 1. Pata fija
    rows.append(_motor_row(
        f"{pid}_fix_leg", fixed_side, "fixed_bullet", spec.notional,
        spec.fixed_rate, 0.0, start, maturity,
        spec.daycount, spec.payment_freq, spec.currency,
        floor_rate=spec.floor_rate, cap_rate=spec.cap_rate,
    ))

    # 2. Pata variable
    rows.append(_motor_row(
        f"{pid}_flt_leg", float_side, "variable_bullet", spec.notional,
        None, spread, start, maturity,
        spec.daycount, spec.payment_freq, spec.currency,
        index_name=spec.variable_index,
        reprice_date=start,
        reprice_freq=reprice_freq,
        rate_type="float",
        floor_rate=spec.floor_rate, cap_rate=spec.cap_rate,
    ))

    # NO se necesitan offsets de principal.  Los flujos de principal
    # al vencimiento se cancelan por convenio de signos:
    # fixed_bullet(L) aporta sign(-1)*notional = -N
    # variable_bullet(A) aporta sign(+1)*notional = +N
    # Neto = 0.

    return rows
```

**Paso 3**: Modificar `decompose_loan()` para despachar IRS:

```python
def decompose_loan(spec: LoanSpec) -> pd.DataFrame:
    start, grace_end, maturity = _resolve_dates(spec)

    if spec.rate_type == "irs":
        rows = _decompose_irs(spec, start, maturity)
    elif spec.rate_type == "mixed":
        rows = _decompose_mixed(spec, start, grace_end, maturity)
    elif spec.rate_type == "variable":
        rows = _decompose_simple(spec, "variable", start, grace_end, maturity)
    else:
        rows = _decompose_simple(spec, "fixed", start, grace_end, maturity)

    return pd.DataFrame(rows)
```

#### B. Schema Pydantic

**Archivo**: `backend/app/schemas.py`
**Modelo**: `LoanSpecItem`

Anadir:

```python
    paying_leg: str | None = None      # "fixed" | "floating" — solo para IRS
```

#### C. Router

**Archivo**: `backend/app/routers/whatif.py`
**Funcion**: `_loan_spec_from_item()`

Anadir al return:

```python
    paying_leg=item.paying_leg,
```

#### D. Frontend types

**Archivo**: `src/types/whatif.ts`

Ampliar `RateType`:

```typescript
// ANTES
export type RateType = 'fixed' | 'variable' | 'mixed';

// DESPUES
export type RateType = 'fixed' | 'variable' | 'mixed' | 'irs';
```

Anadir a `LoanSpec`:

```typescript
    payingLeg?: 'fixed' | 'floating';
```

#### E. Frontend form mapping

**Archivo**: `src/components/whatif/shared/constants.ts`
**Funcion**: `buildModificationFromForm()`

Asegurar que cuando el template es `irs-hedge`, el `rateType` se envie
como `"irs"` y `payingLeg` se incluya en el payload.

### 2.5 Tests — Bateria completa

Archivo: `backend/engine/tests/test_irs_swap.py`

#### Tests unitarios decomposer (4 tests)

```
test_irs_payer_produces_2_positions
    LoanSpec: rate_type="irs", paying_leg="fixed", 100M, 5Y, fixed 3%,
    EURIBOR 6M + 0bp.
    Verificar: 2 rows en DataFrame (NO 4 — sin offsets).
    Verificar: fix_leg.side == "L", flt_leg.side == "A".

test_irs_receiver_produces_2_positions_inverted
    LoanSpec: paying_leg="floating".
    Verificar: fix_leg.side == "A", flt_leg.side == "L".

test_irs_legs_have_correct_rates
    Verificar: fix_leg.fixed_rate == 0.03, fix_leg.spread == 0.0.
    Verificar: flt_leg.fixed_rate == 0.0, flt_leg.spread == spread_bps/10000.
    Verificar: flt_leg.index_name == "EUR_EURIBOR_6M".

test_irs_both_positions_same_notional
    Verificar: 2 posiciones tienen notional == 100M.
```

#### Tests de cancelacion de principal (3 tests)

```
test_irs_principal_net_zero_in_cashflows
    1. Decompose IRS payer 100M 5Y.
    2. build_eve_cashflows() con curva flat 2%.
    3. Filtrar cashflows en maturity_date.
    4. Sumar principal_amount de las 2 posiciones.
    Verificar: suma == 0 (sides opuestos cancelan: L=-100M, A=+100M).
    Razon: side_sign("A")=+1, side_sign("L")=-1, mismo notional y maturity.

test_irs_only_interest_survives
    1. Mismo setup que arriba.
    2. Sumar TODOS los cashflows (interest + principal).
    3. Verificar: la suma de principal neta = 0 en la fecha de maturity.
    4. Verificar: la suma de interes neta != 0 (es el diferencial fijo-variable).

test_irs_eve_is_purely_interest_driven
    1. Decompose IRS 100M 5Y.
    2. Calcular EVE con curva flat.
    3. Calcular EVE con curva +100bp.
    4. Verificar: la diferencia de EVE se debe SOLO a intereses.
    5. Verificar: cambiar el notional por 2x → EVE delta cambia por 2x
       (linearidad, confirma que no hay efecto principal).
```

#### Tests de sensibilidad EVE (4 tests)

```
test_irs_payer_negative_sensitivity
    IRS payer 100M 5Y, fixed 3%, float EURIBOR + 0bp.
    Curva base: flat 3%.
    Curva shock: flat 4% (+100bp).
    Verificar: EVE con shock < EVE base (payer pierde si tipos suben,
    porque la pata fija que paga vale mas).
    NOTA: en realidad el payer GANA si tipos suben porque la pata
    variable que recibe vale mas. Revisar signo segun convencion.

test_irs_receiver_positive_sensitivity
    IRS receiver 100M 5Y (recibe fijo, paga variable).
    Verificar: EVE con shock > EVE base (sensibilidad inversa al payer).

test_irs_payer_vs_receiver_symmetric
    Mismos parametros, solo cambia paying_leg.
    Verificar: EVE_payer + EVE_receiver == 0 (simetria perfecta).

test_irs_at_par_eve_near_zero
    IRS 100M 5Y, fixed_rate == forward rate a 5Y.
    Verificar: EVE base ≈ 0 (el swap esta at-par).
    Tolerancia: abs(EVE) < 0.01% del notional.
```

#### Tests NII (2 tests)

```
test_irs_payer_nii_12m
    IRS payer 100M 3Y, fixed 2.5%, EURIBOR 6M + 0bp.
    Curva forward: EURIBOR 6M = 3% flat.
    NII 12M esperado: (3% - 2.5%) * 100M = +500K (recibe mas de lo que paga).
    Verificar: NII ≈ 500K (con tolerancia por daycount y discretizacion).

test_irs_receiver_nii_12m_negative
    IRS receiver mismos parametros.
    NII 12M esperado: (2.5% - 3%) * 100M = -500K.
    Verificar: NII ≈ -500K.
```

#### Tests edge cases (3 tests)

```
test_irs_with_floor_cap_applied_to_float_leg
    IRS 100M 5Y con floor_rate=1%, cap_rate=5%.
    Curva forward: 0.5% (por debajo del floor).
    Verificar: la pata variable usa 1% (floor), no 0.5%.

test_irs_missing_paying_leg_raises_error
    LoanSpec rate_type="irs", paying_leg=None.
    Verificar: ValueError con mensaje claro.

test_irs_missing_variable_index_raises_error
    LoanSpec rate_type="irs", variable_index=None.
    Verificar: ValueError con mensaje claro.
```

#### Test integracion end-to-end (1 test)

```
test_whatif_irs_hedge_full_pipeline
    1. Crear LoanSpec: IRS payer 150M, 7Y, fixed 2.8%, EURIBOR 12M + 10bp.
    2. Decompose → verificar 2 posiciones con sides correctos.
    3. build_eve_cashflows → verificar principal neto = 0.
    4. compute_eve_full → obtener EVE scalar.
    5. Shock curva +200bp → recalcular EVE.
    6. Verificar: delta EVE tiene el signo esperado (payer gana con subida).
    7. compute_nii_from_cashflows → verificar NII coherente con
       diferencial fijo-variable.
```

### 2.6 Estimacion de complejidad (revisada x2)

- **Esfuerzo**: BAJO-MEDIO. La funcion nueva tiene ~35 lineas (sin offsets). Wiring trivial.
- **Riesgo**: MUY BAJO. Reutiliza fixed_bullet y variable_bullet probados.
  Sin offsets: menos codigo, menos puntos de fallo.
- **Lineas de codigo**: ~50 nuevas (vs ~70 del plan anterior), ~10 modificadas.
- **Tests**: 17 tests (vs 19: se eliminan 2 tests de offsets).

---

## 3. SCHEDULED AMORTIZATION EN WHAT-IF

### 3.1 Que es

Amortizacion programada: el usuario define manualmente las fechas y cantidades
de devolucion de principal, en lugar de usar un patron automatico (bullet,
lineal, annuity).

### 3.2 Estado actual

El motor YA soporta `fixed_scheduled` y `variable_scheduled`:
- `eve.py`: `_extend_fixed_scheduled_cashflows()` (linea ~999)
- `eve.py`: `_extend_variable_scheduled_cashflows()` (linea ~1084)
- `nii_projectors.py`: `project_fixed_scheduled_nii_12m()` (linea ~1824)
- `nii_projectors.py`: `project_variable_scheduled_nii_12m()` (linea ~1923)
- `scheduled_reader.py`: Lector de schedules desde CSV/Excel

El gap esta en:
1. El decomposer no genera posiciones scheduled
2. No hay UI en el frontend para que el usuario introduzca el schedule
3. El pipeline What-If no pasa `flows_by_contract` al motor

### 3.3 Archivos a modificar

#### A. Decomposer — soporte scheduled (EFICIENTE)

**Archivo**: `backend/engine/services/whatif/decomposer.py`

**Paso 1**: Ampliar `LoanSpec` (linea ~65):

```python
    amortization: Literal["bullet", "linear", "annuity", "scheduled"] = "bullet"
    schedule: list[tuple[str, float]] | None = None  # [(iso_date, principal_amount), ...]
```

**Paso 2**: Nueva funcion:

```python
def _decompose_scheduled(
    spec: LoanSpec, rate_prefix: str, start: date, maturity: date
) -> list[dict]:
    """Genera una posicion scheduled a partir del LoanSpec."""
    spread = spec.spread_bps / 10_000 if rate_prefix == "variable" else 0.0
    fixed_rate = spec.fixed_rate if rate_prefix == "fixed" else None
    index = spec.variable_index if rate_prefix == "variable" else None
    reprice_freq = spec.repricing_freq or spec.payment_freq
    sct = f"{rate_prefix}_scheduled"
    pid = spec.id_prefix

    return [_motor_row(
        f"{pid}_main", spec.side, sct, spec.notional,
        fixed_rate, spread, start, maturity,
        spec.daycount, spec.payment_freq, spec.currency,
        index_name=index,
        reprice_date=start if index else None,
        reprice_freq=reprice_freq if index else None,
        rate_type="float" if rate_prefix == "variable" else "fixed",
        floor_rate=spec.floor_rate, cap_rate=spec.cap_rate,
        call_date=spec.call_date,
    )]
```

**Paso 3**: Despachar en `decompose_loan()`:

```python
    if spec.amortization == "scheduled":
        rate_prefix = "variable" if spec.rate_type == "variable" else "fixed"
        rows = _decompose_scheduled(spec, rate_prefix, start, maturity)
    elif spec.rate_type == "irs":
        ...
```

**Paso 4**: Devolver tambien el schedule como dato auxiliar.

El caller necesita pasar `flows_by_contract` al motor.

**DISENO EFICIENTE**: En lugar de cambiar la firma de `decompose_loan()`
(breaking change que afecta a 3 callers), usamos un enfoque mas limpio:
el schedule se pasa como metadato en el DataFrame via una columna auxiliar
`_scheduled_flows_json`. Esto evita cambiar la interfaz publica.

```python
def decompose_loan(spec: LoanSpec) -> pd.DataFrame:
    ...
    df = pd.DataFrame(rows)

    # Inyectar schedule como metadato para que el caller pueda extraerlo
    if spec.amortization == "scheduled" and spec.schedule:
        import json
        flows_json = json.dumps([(d, a) for d, a in spec.schedule])
        df["_scheduled_flows_json"] = flows_json

    return df
```

**Alternativa mas limpia** (si se prefiere no contaminar el DataFrame):
devolver `DecomposeResult` pero SOLO si el caller lo pide:

```python
@dataclass
class DecomposeResult:
    positions: pd.DataFrame
    scheduled_flows: dict[str, list[tuple[date, float]]]

def decompose_loan(spec: LoanSpec) -> pd.DataFrame:
    """Interfaz publica sin cambios — devuelve DataFrame."""
    ...
    return pd.DataFrame(rows)

def decompose_loan_with_schedule(spec: LoanSpec) -> DecomposeResult:
    """Version extendida que incluye scheduled flows."""
    df = decompose_loan(spec)
    scheduled_flows = {}
    if spec.amortization == "scheduled" and spec.schedule:
        contract_id = f"{spec.id_prefix}_main"
        scheduled_flows[contract_id] = [
            (date.fromisoformat(d), amt) for d, amt in spec.schedule
        ]
    return DecomposeResult(positions=df, scheduled_flows=scheduled_flows)
```

**Ventaja**: `decompose_loan()` sigue devolviendo DataFrame (0 callers rotos).
Solo los callers que necesitan scheduled usan `decompose_loan_with_schedule()`.

#### B. Router — pasar scheduled_flows al motor

**Archivo**: `backend/app/routers/whatif.py`
**Funcion**: `_decompose_additions()` (linea ~90)

Modificar para usar `decompose_loan_with_schedule()` cuando hay additions
con amortization=="scheduled":

```python
from engine.services.whatif.decomposer import decompose_loan_with_schedule

def _decompose_additions(additions, analysis_date):
    all_rows = []
    all_scheduled = {}
    for item in additions:
        spec = _loan_spec_from_item(item, analysis_date)
        result = decompose_loan_with_schedule(spec)
        all_rows.extend(result.positions.to_dict("records"))
        all_scheduled.update(result.scheduled_flows)
    df = pd.DataFrame(all_rows) if all_rows else pd.DataFrame()
    return df, all_scheduled
```

Y en `_compute_eve_nii()`, pasar `scheduled_principal_flows` cuando existan.

**Nota**: `decompose_preview()` y `find_limit()` no necesitan cambiar
si no soportan scheduled (fase posterior).

#### C. Schema Pydantic

**Archivo**: `backend/app/schemas.py`

Anadir a `LoanSpecItem`:

```python
    schedule: list[dict] | None = None   # [{"date": "2025-06-30", "amount": 100000}, ...]
```

#### D. Frontend — mini-editor de schedule

**Archivo**: Nuevo componente o extension de `ProductConfigForm.tsx`

Cuando `amortization === "scheduled"`, mostrar una tabla editable:

```
| Fecha       | Principal (EUR) | [+] |
|-------------|-----------------|-----|
| 2025-06-30  | 100,000         | [-] |
| 2025-12-31  | 100,000         | [-] |
| 2026-06-30  | 200,000         | [-] |
```

Con botones para anadir/eliminar filas. Validar que la suma de principal
no exceda el notional.

### 3.4 Tests — Bateria completa

Archivo: `backend/engine/tests/test_scheduled_whatif.py`

#### Tests unitarios decomposer (4 tests)

```
test_decompose_scheduled_fixed_produces_1_position
    LoanSpec: fixed, scheduled, 3 flujos.
    Verificar: 1 row con source_contract_type == "fixed_scheduled".

test_decompose_scheduled_variable_produces_1_position
    LoanSpec: variable, scheduled, 3 flujos.
    Verificar: 1 row con source_contract_type == "variable_scheduled".

test_decompose_with_schedule_returns_flows_dict
    Usar decompose_loan_with_schedule().
    Verificar: scheduled_flows tiene 1 key con 3 tuplas (date, amount).
    Verificar: dates y amounts correctos.

test_decompose_scheduled_without_schedule_raises
    LoanSpec: amortization="scheduled", schedule=None.
    Verificar: ValueError con mensaje claro.
```

#### Tests EVE con scheduled (3 tests)

```
test_eve_fixed_scheduled_follows_exact_dates
    Crear posicion fixed_scheduled + flows_by_contract con 3 amortizaciones:
    - 25% a 2Y, 25% a 4Y, 50% a 6Y.
    Verificar: cashflows de principal solo en esas 3 fechas exactas.
    Verificar: interes se calcula sobre saldo decreciente.

test_eve_variable_scheduled_with_repricing
    Crear posicion variable_scheduled + schedule.
    Verificar: interes reprices a las fechas de reset.
    Verificar: principal sigue el schedule, no un patron automatico.

test_eve_scheduled_vs_linear_different_eve
    Misma posicion, mismo notional, mismo plazo.
    Una con amortizacion linear, otra con scheduled (50% a 1Y, 50% a 5Y).
    Verificar: EVE diferentes (el front-loading de la scheduled
    reduce duracion → EVE menor).
```

#### Tests NII con scheduled (2 tests)

```
test_nii_scheduled_interest_on_declining_balance
    Posicion fixed_scheduled, 100M, 3Y, schedule: 50M a 1Y, 50M a 2Y.
    NII 12M: interes de 100M por 12 meses? No: interes de 100M por Y1,
    luego 50M por Y2 (si horizon incluye Y2).
    Verificar: NII refleja el balance decreciente.

test_nii_scheduled_within_horizon
    Schedule con amortizacion a 6M (dentro del horizon NII de 12M).
    Verificar: NII pre-amortizacion y post-amortizacion correctos.
```

#### Tests edge cases (3 tests)

```
test_schedule_sum_exceeds_notional_warning
    Schedule donde sum(amounts) > notional.
    Verificar: warning o error explicito.

test_schedule_date_before_start_ignored
    Schedule con fecha anterior a start_date.
    Verificar: ese flujo se ignora sin crashear.

test_schedule_date_after_maturity_ignored
    Schedule con fecha posterior a maturity_date.
    Verificar: ese flujo se ignora sin crashear.
```

#### Test integracion (1 test)

```
test_whatif_scheduled_full_pipeline
    1. LoanSpec: fixed, scheduled, 100M, 5Y, 4 pagos de 25M.
    2. decompose_loan_with_schedule() → DataFrame + flows dict.
    3. build_eve_cashflows(scheduled_principal_flows=...) → cashflows.
    4. Verificar: 4 flujos de principal en las fechas exactas.
    5. compute_eve_full → EVE scalar coherente.
```

### 3.5 Estimacion de complejidad (revisada)

- **Esfuerzo**: MEDIO.
  - Decomposer: ~30 lineas (funcion + DecomposeResult)
  - Router: ~15 lineas (actualizar _decompose_additions)
  - Frontend mini-editor: ~100-150 lineas React
  - 0 cambios en el motor EVE/NII (ya soporta scheduled)
- **Riesgo**: BAJO (con el enfoque de dos funciones, no hay breaking change).
- **Tests**: 13 tests.

---

## 4. ORDEN DE IMPLEMENTACION RECOMENDADO

```
Fase 1: Callable          [Esfuerzo: BAJO,  Impacto: ALTO, 19 tests]
  └─ 3 bloques de truncacion + campo nuevo. Zero engine changes.
  └─ Desbloquea valoracion correcta de bonos callable en What-If.

Fase 2: IRS               [Esfuerzo: BAJO-MEDIO, Impacto: ALTO, 17 tests]
  └─ Nueva funcion en decomposer (2 posiciones, sin offsets) + wiring frontend.
  └─ Zero engine changes (principal se cancela por convenio de signos).
  └─ Desbloquea simulacion de coberturas.

Fase 3: Scheduled          [Esfuerzo: MEDIO, Impacto: MEDIO, 13 tests]
  └─ decompose_loan_with_schedule() (sin breaking change).
  └─ UI nueva en frontend (mini-editor).
  └─ Menor prioridad: bullet/linear/annuity cubren 90% de casos.
```

**Total: 49 tests nuevos.**

---

## 5. SUITE DE TESTS DE REGRESION

Ademas de los tests especificos, ejecutar SIEMPRE antes y despues de cada fase:

```
backend/engine/tests/test_eve_engine.py           — EVE exacto y bucketed
backend/engine/tests/test_nii_fixed_bullet.py      — NII fixed bullet
backend/engine/tests/test_nii_fixed_linear.py      — NII fixed linear
backend/engine/tests/test_nii_fixed_annuity.py     — NII fixed annuity
backend/engine/tests/test_nii_fixed_scheduled.py   — NII fixed scheduled
backend/engine/tests/test_nii_variable_bullet.py   — NII variable bullet
backend/engine/tests/test_nii_variable_linear.py   — NII variable linear
backend/engine/tests/test_nii_variable_annuity.py  — NII variable annuity
backend/engine/tests/test_nii_variable_scheduled.py — NII variable scheduled
backend/engine/tests/test_whatif_decomposer.py     — Decomposer existente
backend/engine/tests/test_whatif_scenarios.py      — What-If escenarios
backend/engine/tests/test_whatif_find_limit.py     — Find Limit
backend/engine/tests/test_parser_contracts.py      — Parser contratos
backend/engine/tests/test_positions_pipeline.py    — Pipeline posiciones
```

**Protocolo**: `pytest backend/engine/tests/ -v --tb=short` debe pasar
al 100% antes Y despues de cada fase. Si algun test falla despues de un
cambio, parar y arreglar ANTES de continuar.

---

## 6. CHECKLIST DE VALIDACION CRUZADA

Antes de dar por cerrada cada fase, verificar:

- [ ] **Tests de regresion**: TODOS pasan (suite completa arriba)
- [ ] **Tests nuevos**: TODOS pasan (los 19/19/13 de la fase)
- [ ] **Positions reader**: acepta el nuevo campo sin romper CSVs existentes
- [ ] **EVE**: cashflows generados correctamente (comparar con calculo manual)
- [ ] **NII**: proyeccion 12M respeta la modificacion
- [ ] **Decomposer**: genera posiciones motor validas (todas las columnas)
- [ ] **Router**: convierte frontend → LoanSpec → motor sin perder datos
- [ ] **Frontend**: el campo se captura, se envia al backend, y se refleja
      en el preview de decompose
- [ ] **Find Limit**: funciona con los nuevos tipos (no se rompe el solver)

---

## 7. ARCHIVOS CLAVE (REFERENCIA RAPIDA)

| Capa       | Archivo                                          | Que hace                              |
|------------|--------------------------------------------------|---------------------------------------|
| Frontend   | `src/types/whatif.ts`                            | Types, templates, LoanSpec            |
| Frontend   | `src/components/whatif/shared/constants.ts`      | buildModificationFromForm()           |
| Frontend   | `src/components/whatif/BuySellCompartment.tsx`    | UI del Add/Remove                     |
| Frontend   | `src/components/whatif/shared/ProductConfigForm.tsx` | Formulario de producto            |
| API Schema | `backend/app/schemas.py`                         | LoanSpecItem (Pydantic)               |
| Router     | `backend/app/routers/whatif.py`                  | _loan_spec_from_item(), endpoints     |
| Decomposer | `backend/engine/services/whatif/decomposer.py`   | LoanSpec → motor rows                 |
| EVE        | `backend/engine/services/eve.py`                 | Cashflow generation (8 funciones)     |
| NII        | `backend/engine/services/nii_projectors.py`      | Proyeccion mensual (8 funciones)      |
| NII        | `backend/engine/services/nii.py`                 | Orquestacion NII                      |
| Positions  | `backend/engine/io/positions_reader.py`          | Schema de columnas motor              |
| Scheduled  | `backend/engine/io/scheduled_reader.py`          | Lector de schedules                   |
| Curves     | `backend/engine/core/curves.py`                  | Interpolacion log-lineal              |
| Day Count  | `backend/engine/core/daycount.py`                | yearfrac() con 4 convenciones         |

---

## 8. DECISIONES DE DISENO TOMADAS

1. **Callable — truncacion centralizada**: En lugar de modificar las 16
   funciones generadoras de EVE y NII, se trunca `maturity_date` en los
   3 entry points (`build_eve_cashflows`, `run_nii_12m_base`,
   `compute_nii_from_cashflows`). Esto es mas eficiente (3 vs 16 cambios),
   menos propenso a errores, y vectorizado en pandas.

2. **Callable — enfoque determinista**: Truncar siempre en call_date.
   No se implementa valoracion condicional (PV > par). Alineado con
   estandar regulatorio IRRBB.

3. **IRS — 2 posiciones SIN offsets**: Modelizado como 2 posiciones
   sinteticas (pata fija + pata variable). Los flujos de principal al
   vencimiento se cancelan automaticamente por convenio de signos del motor:
   - Pata fija (L): principal = side_sign("L") * notional = -N
   - Pata variable (A): principal = side_sign("A") * notional = +N
   - Neto: -N + N = 0
   No se necesitan offsets. Zero engine changes. 50% menos posiciones y
   calculos que el enfoque con offsets. Verificado que en What-If no se
   aplica CPR/TDRR (ambos default 0.0), por lo que la cancelacion es exacta.

4. **Scheduled — dos funciones sin breaking change**: `decompose_loan()`
   sigue devolviendo DataFrame (API publica intacta). Nueva funcion
   `decompose_loan_with_schedule()` devuelve `DecomposeResult` con
   scheduled_flows. Solo los callers que necesitan scheduled la usan.
   Zero callers rotos.

5. **NMD repricing beta**: Excluido de este plan. Se abordara en una
   fase posterior cuando se conecte el modulo behavioural al pipeline What-If.

---

## 9. OPTIMIZACIONES FUTURAS (FUERA DE ALCANCE)

Detectadas durante la revision del plan pero fuera del alcance actual:

1. **Filtrado de posiciones duplicado**: `_positions_by_supported_type()` en
   `eve.py` (linea 232) y `_split_implemented_positions()` en `nii.py`
   (linea 62) hacen el mismo trabajo de normalizacion y filtrado. Refactorizar
   a un modulo compartido `engine/services/_position_filters.py` ahorraria
   1 pase completo del DataFrame por calculo. Impacto alto en datasets >100K.

2. **Scheduled flows doble parsing**: `prepare_scheduled_principal_flows()`
   se llama por separado en EVE y NII. Pre-computar una vez en el pipeline
   y pasar el resultado a ambos ahorraria un O(N) por escenario.

3. **Cache de posiciones preparadas**: Tras el filtrado/normalizacion,
   cachear el resultado en `state._positions_df_cache` para que ejecuciones
   repetidas de EVE/NII en la misma sesion no repitan el preprocesado.
