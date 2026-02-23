# PROMPT DE INTEGRACIÓN: Motor de Cálculo → UI Front-Back (ALMReady)

> **Para usar en**: Claude Code (VS Code extension, último modelo)
> **Fecha de generación**: 17 de febrero de 2026
> **Objetivo**: Integrar el motor de cálculo Python (EVE/NII) dentro del proyecto UI front-back para obtener resultados reales de Economic Value of Equity y Net Interest Income.

---

## INSTRUCCIONES PARA CLAUDE CODE

Tienes acceso al filesystem de dos proyectos que forman parte de la misma aplicación ALMReady. Tu trabajo es integrarlos en uno solo. Lee este prompt completo antes de hacer cualquier cambio.

---

## 1. CONTEXTO GLOBAL DE ALMREADY

ALMReady es una aplicación local-first de IRRBB (Interest Rate Risk in the Banking Book) que permite:

1. **Cargar un balance bancario real** (Excel) y explorarlo (Balance Positions + View Details + filtros + búsqueda de contratos).
2. **Cargar curvas de tipos de interés** (Excel) y visualizar curvas base + shocks regulatorios EBA.
3. **Ejecutar un cálculo pesado de EVE y NII** para el balance completo usando un motor Python real.
4. **What-If Builder instantáneo**: añadir/eliminar/ajustar posiciones y ver el impacto en EVE/NII sin recalcular todo (fase 2, fuera de scope ahora).

La filosofía es: un "base run" caro → interacción What-If barata (fase posterior).

---

## 2. DECISIÓN ARQUITECTÓNICA CLAVE

**El motor de cálculo se integra DENTRO del proyecto UI (front-back)**, NO al revés.

**Razones:**
- El proyecto front-back ya tiene: sesiones UUID, persistencia en disco, endpoints REST (FastAPI), orquestación completa, React UI funcional.
- El motor de cálculo es una **librería Python pura** sin framework web, diseñada exactamente para ser importada.
- El motor no tiene IO de red, ni ORM, ni base de datos — solo recibe DataFrames y devuelve resultados.

**Acción concreta:**
- Copiar/mover el paquete completo `almready/` (con `core/`, `config/`, `io/`, `services/`, `scenarios/`) dentro del directorio backend del proyecto front-back.
- Ubicación sugerida: `backend/almready/` (manteniendo la estructura interna intacta).
- Añadir las dependencias del motor (`pandas`, `numpy`, `python-dateutil`, `openpyxl`, `matplotlib`) al `requirements.txt` del backend si no están ya.

---

## 3. LOS DOS PROYECTOS — DÓNDE ESTÁ CADA COSA

### 3.1 Proyecto Front-Back (UI)
```
ALMReady-FrontBack/
├── backend/
│   ├── app/main.py              ← API FastAPI (~1553 líneas), TODA la lógica backend
│   ├── data/sessions/{id}/      ← Persistencia por sesión (JSON + Excels)
│   └── requirements.txt
├── src/                          ← Frontend React + TypeScript
│   ├── pages/Index.tsx           ← Orquestador principal
│   ├── components/
│   │   ├── ResultsCard.tsx       ← Card de resultados EVE/NII (tiene impactos What-If HARDCODED)
│   │   ├── BalancePositionsCard.tsx
│   │   ├── CurvesAndScenariosCard.tsx
│   │   ├── connected/BalancePositionsCardConnected.tsx
│   │   ├── whatif/WhatIfContext.tsx
│   │   ├── behavioural/BehaviouralContext.tsx
│   │   └── results/EVEChart.tsx, NIIChart.tsx
│   ├── lib/
│   │   ├── calculationEngine.ts  ← Motor LOCAL simplificado (HAY QUE REEMPLAZAR)
│   │   ├── api.ts                ← Cliente HTTP
│   │   ├── session.ts            ← Gestión de sesión
│   │   └── scenarios.ts          ← Fórmulas de shocks (visualización)
│   └── types/financial.ts        ← Tipos TypeScript (Position, CalculationResults, etc.)
```

### 3.2 Proyecto Motor de Cálculo
```
almready/
├── core/                   ← Fundamentos matemáticos
│   ├── curves.py           ← ForwardCurve, interpolación log-lineal en ln(DF)
│   ├── daycount.py         ← ACT/360, ACT/365, ACT/ACT, 30/360
│   └── tenors.py           ← Aritmética de tenors (ON, W, M, Y)
├── config/                 ← Adaptación por banco
│   ├── bank_mapping_template.py  ← Contrato de interfaz para mappings
│   ├── bank_mapping_unicaja.py   ← Mapping concreto Unicaja
│   └── eve_buckets.py            ← Buckets temporales regulatorios
├── io/                     ← Carga y canonicalización de datos
│   ├── positions_reader.py       ← Lector de posiciones (CSV/Excel)
│   ├── positions_pipeline.py     ← Orquestador multi-fichero desde SOURCE_SPECS
│   ├── scheduled_reader.py       ← Lector jerárquico contrato+pago
│   └── curves_forward_reader.py  ← Lector de curvas forward desde Excel
├── services/               ← Motores de cálculo
│   ├── market.py                 ← ForwardCurveSet (contenedor central de curvas)
│   ├── margin_engine.py          ← Calibración de márgenes para renovación
│   ├── eve.py                    ← Motor EVE (exact y bucketed, ~1464 líneas)
│   ├── nii_projectors.py         ← 8 proyectores NII por tipo de contrato (~1899 líneas)
│   ├── nii.py                    ← Orquestador NII
│   ├── regulatory_curves.py      ← Curvas estresadas por escenario
│   ├── eve_analytics.py          ← Resúmenes analíticos EVE
│   ├── eve_pipeline.py           ← Pipeline completo EVE end-to-end
│   └── nii_pipeline.py           ← Pipeline completo NII end-to-end
├── scenarios/              ← Shocks regulatorios
│   ├── regulatory.py             ← EU Reg. 2024/856 (BCBS IRRBB)
│   ├── shocks.py                 ← Shocks paralelos ad-hoc
│   └── apply.py                  ← Aplicación de shocks sobre curvas
└── tests/                  ← Tests unitarios y smoke tests
```

---

## 4. EL PUNTO CRÍTICO: EL BALANCE — DOS ESQUEMAS DIFERENTES

Este es el punto más complejo de la integración. Actualmente los dos proyectos leen el balance de forma completamente distinta.

### 4.1 Cómo lee el balance el Front-Back (ACTUAL — hay que adaptar)

- **Formato de entrada**: Excel con hojas prefijadas `A_`, `L_`, `E_`, `D_`.
- **Columnas esperadas**: `num_sec_ac`, `lado_balance`, `categoria_ui`, `subcategoria_ui`, `grupo`, `moneda`, `saldo_ini`, `tipo_tasa`, `book_value`, `tae`, `tasa_fija`, `spread`, `indice_ref`, `fecha_vencimiento`, `fecha_prox_reprecio`, etc.
- **Canonicalización**: genera `balance_positions.json` con campos como `contract_id`, `side` (asset/liability/equity/derivative), `categoria_ui`, `subcategoria_ui`, `subcategory_id`, `group`, `currency`, `amount`, `rate_type` (Fixed/Floating), `rate_display`, `maturity_years`, `maturity_bucket`, etc.
- **Árbol de resumen**: `BalanceSummaryTree` con categorías → subcategorías → métricas agregadas.

### 4.2 Cómo lee el balance el Motor de Cálculo (OBJETIVO — este esquema manda)

- **Formato de entrada**: Múltiples CSVs (uno por tipo de contrato), leídos via `SOURCE_SPECS` del `bank_mapping`.
- **10 tipos de contrato**: `fixed_annuity`, `fixed_bullet`, `fixed_linear`, `fixed_scheduled`, `fixed_non_maturity`, `variable_annuity`, `variable_bullet`, `variable_linear`, `variable_non_maturity`, `variable_scheduled`.
- **Esquema canónico del motor** (las columnas que el motor necesita para calcular):

**REQUERIDAS:**
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `contract_id` | str | Identificador único |
| `start_date` | date | Fecha de inicio |
| `maturity_date` | date | Fecha de vencimiento (opcional para non-maturity) |
| `notional` | float | Nominal vigente (siempre positivo) |
| `side` | str | "A" (activo) o "L" (pasivo) |
| `rate_type` | str | "fixed" o "float" |
| `daycount_base` | str | Base normalizada ("ACT/360", "ACT/365", etc.) |

**OPCIONALES (pero necesarias para cálculo preciso):**
| Columna | Tipo | Descripción |
|---------|------|-------------|
| `index_name` | str | Índice de referencia ("EURIBOR_3M", etc.) — requerida para float |
| `spread` | float | Diferencial sobre índice (en decimal, ej: 0.015) |
| `fixed_rate` | float | Tipo fijo (en decimal, ej: 0.035) — requerida para fixed |
| `repricing_freq` | str | Frecuencia repricing ("3M", "6M", "1Y") |
| `payment_freq` | str | Frecuencia de pago |
| `next_reprice_date` | date | Próxima fecha de repricing |
| `floor_rate` | float | Suelo de tipo (decimal) |
| `cap_rate` | float | Techo de tipo (decimal) |
| `annuity_payment_mode` | str | "reprice_on_reset" o "fixed_payment" |

**METADATA (añadida por pipeline):**
| Columna | Descripción |
|---------|-------------|
| `source_contract_type` | "fixed_annuity", "variable_bullet", etc. |
| `source_bank` | Banco de origen |
| `source_file` | Fichero de origen |

### 4.3 Estrategia de adaptación del balance

**DECISIÓN**: Nos quedamos con la estructura de datos del motor de cálculo. El front-back se adapta.

**Lo que hay que hacer:**

1. **Nuevo parser de balance en el backend** (`main.py`) que lea los CSVs en el formato del motor y genere:
   - `balance_positions.json` en el esquema canónico del motor (contract_id, start_date, maturity_date, notional, side, rate_type, daycount_base, etc.).
   - PERO también debe incluir los campos que la UI necesita para funcionar (categoria_ui, subcategoria_ui, subcategory_id, group, currency, amount, maturity_years, maturity_bucket, rate_display, etc.). Estos campos se derivan/infieren del `source_contract_type` y de los datos del contrato.

2. **Mantener `BalanceSummaryTree`** en el backend: la UI necesita el árbol de categorías/subcategorías para la card de balance. El árbol se construye a partir de las posiciones canonicalizadas, igual que ahora, pero usando el nuevo esquema.

3. **Mapeo source_contract_type → categorías UI:**
   ```python
   # Ejemplo de mapeo para generar los campos que la UI necesita:
   CONTRACT_TYPE_TO_UI = {
       "fixed_annuity":       {"subcategory_id": "loans", "subcategoria_ui": "Loans", "rate_type_ui": "Fixed"},
       "fixed_bullet":        {"subcategory_id": "securities", "subcategoria_ui": "Securities", "rate_type_ui": "Fixed"},
       "fixed_linear":        {"subcategory_id": "loans", "subcategoria_ui": "Loans", "rate_type_ui": "Fixed"},
       "fixed_scheduled":     {"subcategory_id": "loans", "subcategoria_ui": "Loans", "rate_type_ui": "Fixed"},
       "fixed_non_maturity":  {"subcategory_id": "deposits", "subcategoria_ui": "Deposits", "rate_type_ui": "Fixed"},
       "variable_annuity":    {"subcategory_id": "mortgages", "subcategoria_ui": "Mortgages", "rate_type_ui": "Floating"},
       "variable_bullet":     {"subcategory_id": "loans", "subcategoria_ui": "Loans", "rate_type_ui": "Floating"},
       "variable_linear":     {"subcategory_id": "loans", "subcategoria_ui": "Loans", "rate_type_ui": "Floating"},
       "variable_non_maturity": {"subcategory_id": "deposits", "subcategoria_ui": "Deposits", "rate_type_ui": "Floating"},
       "variable_scheduled":  {"subcategory_id": "loans", "subcategoria_ui": "Loans", "rate_type_ui": "Floating"},
   }
   # NOTA: Este mapeo es orientativo. El side (A/L) viene del propio dato del contrato.
   # La subcategoría real puede depender del epígrafe o de otros campos del banco.
   ```

4. **El campo `amount` de la UI** = `notional` del motor. Es un alias directo.

5. **El campo `rate_display` de la UI** = `fixed_rate` si fixed, o `spread` si float.

6. **Compatibilidad**: Mantener temporalmente el endpoint de upload Excel actual como legacy. Añadir nuevo endpoint para el formato del motor (CSVs o ZIP de CSVs).

---

## 5. LAS CURVAS — YA SON COMPATIBLES

Ambos proyectos leen curvas desde el mismo formato Excel (wide: filas = índices, columnas = tenors, valores = rates en decimal). No hay trabajo significativo aquí.

**Lo que ya funciona:**
- El front-back sube el Excel, parsea a `curves_points.json` con formato `{curve_id: [{tenor, t_years, rate}]}`.
- El motor lee el mismo Excel via `curves_forward_reader.py` → `ForwardCurveSet`.

**Para la integración:**
- Cuando el backend necesite ejecutar el motor, puede construir un `ForwardCurveSet` directamente desde el `curves_points.json` de la sesión (sin re-leer el Excel). El motor expone `curve_from_long_df()` que acepta un DataFrame long.
- Alternativamente, puede pasar la ruta del Excel guardado en la sesión (`curves__*.xlsx`) directamente a `load_forward_curve_set()`.

---

## 6. INTEGRACIÓN DEL CÁLCULO — FASE 1 (SCOPE ACTUAL)

### 6.1 Qué hay que eliminar

1. **`src/lib/calculationEngine.ts`** — Motor local simplificado del frontend. Este archivo se elimina o se vacía. El cálculo real lo hará el backend con el motor Python.

2. **Impactos What-If hardcoded en `ResultsCard.tsx`** — Actualmente hay esto:
   ```typescript
   const whatIfImpact = {
     baseEve: hasModifications ? 12_500_000 : 0,
     worstEve: hasModifications ? 8_200_000 : 0,
     baseNii: hasModifications ? -2_100_000 : 0,
     worstNii: hasModifications ? -1_800_000 : 0,
   };
   ```
   Estos valores hardcoded deben eliminarse. ResultsCard solo pintará lo que devuelva el backend.

3. **`runCalculation()` en `Index.tsx`** — La llamada a la función local se reemplaza por una llamada HTTP al backend.

### 6.2 Qué hay que crear/modificar

#### A. Backend: Nuevo endpoint POST /api/sessions/{id}/calculate

```python
@app.post("/api/sessions/{session_id}/calculate")
async def calculate_eve_nii(session_id: str, request: CalculationRequest):
    """
    request body:
    {
        "analysis_date": "2025-12-31",          # Fecha de análisis
        "discount_curve_id": "EUR_ESTR_OIS",    # Curva de descuento seleccionada
        "risk_free_index": "EUR_ESTR_OIS",      # Índice risk-free para escenarios
        "currency": "EUR",                       # Divisa
        "scenario_ids": ["parallel-up", "parallel-down", "steepener", "flattener", "short-up", "short-down"],
        "method": "exact",                       # "exact" o "bucketed"
        "balance_constant": true                 # Para NII: renovar al vencimiento
    }
    """
```

**Flujo interno del endpoint:**

1. Cargar `balance_positions.json` de la sesión → convertir a DataFrame canónico del motor.
2. Cargar `curves_points.json` de la sesión → construir `ForwardCurveSet`.
3. Cargar flujos scheduled si existen.
4. Invocar `run_eve_from_specs()` y `run_nii_from_specs()` del motor (o las funciones de nivel intermedio `run_eve_scenarios()` / `run_nii_12m_scenarios()`).
5. Transformar `EVEPipelineResult` + `NIIPipelineResult` → `CalculationResults` (el formato que el frontend espera).
6. Persistir `calculation_results.json` en la sesión.
7. Devolver la respuesta.

#### B. Adapter: Transformar resultados del motor → formato frontend

El frontend espera `CalculationResults`:
```typescript
interface CalculationResults {
    baseEve: number;
    baseNii: number;
    worstCaseEve: number;
    worstCaseDeltaEve: number;
    worstCaseScenario: string;
    scenarioResults: ScenarioResult[];  // [{scenarioId, scenarioName, eve, nii, deltaEve, deltaNii}]
    calculatedAt: string;
}
```

El motor produce:
- `EVEPipelineResult`: `base_eve`, `scenario_eve: dict[str, float]`, `scenario_summary: DataFrame`, `worst_scenario: str`
- `NIIPipelineResult`: `base_nii_12m`, `scenario_nii_12m: dict[str, float]`

**Función adapter necesaria:**
```python
def motor_results_to_api(eve_result, nii_result) -> dict:
    scenario_results = []
    for scenario_name, eve_val in eve_result.scenario_eve.items():
        nii_val = nii_result.scenario_nii_12m.get(scenario_name, nii_result.base_nii_12m)
        scenario_results.append({
            "scenarioId": scenario_name,
            "scenarioName": scenario_name,
            "eve": eve_val,
            "nii": nii_val,
            "deltaEve": eve_val - eve_result.base_eve,
            "deltaNii": nii_val - nii_result.base_nii_12m,
        })

    worst = min(scenario_results, key=lambda s: s["eve"])

    return {
        "baseEve": eve_result.base_eve,
        "baseNii": nii_result.base_nii_12m,
        "worstCaseEve": worst["eve"],
        "worstCaseDeltaEve": worst["deltaEve"],
        "worstCaseScenario": worst["scenarioName"],
        "scenarioResults": scenario_results,
        "calculatedAt": datetime.utcnow().isoformat(),
    }
```

#### C. Frontend: Reemplazar cálculo local por llamada API

**En `src/lib/api.ts`** — Añadir:
```typescript
export interface CalculateRequest {
    analysis_date: string;
    discount_curve_id: string;
    risk_free_index: string;
    currency: string;
    scenario_ids: string[];
    method?: "exact" | "bucketed";
    balance_constant?: boolean;
}

export async function calculateEveNii(
    sessionId: string,
    request: CalculateRequest
): Promise<CalculationResults> {
    return http(`/api/sessions/${sessionId}/calculate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
    });
}
```

**En `src/pages/Index.tsx`** — Modificar `handleCalculate()`:
```typescript
async function handleCalculate() {
    setIsCalculating(true);
    try {
        const enabledScenarios = scenarios.filter(s => s.enabled);
        const results = await calculateEveNii(sessionId, {
            analysis_date: analysisDate || new Date().toISOString().split('T')[0],
            discount_curve_id: selectedCurves[0],
            risk_free_index: selectedCurves[0],  // O la curva que corresponda
            currency: "EUR",
            scenario_ids: enabledScenarios.map(s => mapScenarioNameToId(s.name)),
            method: "exact",
            balance_constant: true,
        });
        setResults(results);
    } catch (error) {
        console.error("Calculation failed:", error);
        // Mostrar error en UI
    } finally {
        setIsCalculating(false);
    }
}
```

**Mapeo de nombres de escenarios frontend → IDs del motor:**
```typescript
function mapScenarioNameToId(name: string): string {
    const MAP: Record<string, string> = {
        "Parallel Up": "parallel-up",
        "Parallel Down": "parallel-down",
        "Steepener": "steepener",
        "Flattener": "flattener",
        "Short Up": "short-up",
        "Short Down": "short-down",
    };
    return MAP[name] || name.toLowerCase().replace(/\s+/g, '-');
}
```

#### D. En `ResultsCard.tsx` — Eliminar What-If hardcoded

Eliminar por completo el bloque de `whatIfImpact` con valores fijos. ResultsCard debe pintar exclusivamente lo que venga en `results`:
```typescript
// ANTES (ELIMINAR):
const whatIfImpact = {
    baseEve: hasModifications ? 12_500_000 : 0,
    // ...
};
const finalBaseEve = results.baseEve + whatIfImpact.baseEve;

// DESPUÉS:
const finalBaseEve = results.baseEve;
const finalWorstEve = results.worstCaseEve;
// etc. — solo datos reales del backend
```

---

## 7. MAPEO DETALLADO: scenario_ids DEL MOTOR

El motor regulatorio (`scenarios/regulatory.py`) implementa EU Regulation 2024/856 con estos IDs exactos:

**EVE (6 escenarios):** `parallel-up`, `parallel-down`, `short-up`, `short-down`, `steepener`, `flattener`

**NII (2 escenarios):** `parallel-up`, `parallel-down`

**Parámetros EUR:** parallel=200bps, short=250bps, long=100bps

Las fórmulas de shock del motor son las regulatorias reales (exponenciales con decaimiento), NO las simplificaciones lineales que tiene `calculationEngine.ts`.

---

## 8. FUNCIONALIDADES QUE NO SE PUEDEN ROMPER

Al hacer la integración, estas funcionalidades de la UI deben seguir funcionando exactamente igual:

1. **Balance Positions Card**: visualización del árbol de categorías/subcategorías, importes, posiciones, avg rate, avg maturity.
2. **View Details modal**: desglose por grupo con filtros (categoría, subcategoría, currency, rate_type, counterparty, maturity).
3. **Búsqueda de contratos**: paginación, búsqueda full-text por contract_id/sheet/group.
4. **Upload de curvas**: parseo, visualización de curvas base, overlays de escenarios shockeados.
5. **Selección de curvas y escenarios**: toggle de escenarios, selección de curva de descuento.
6. **What-If Builder**: añadir/eliminar posiciones (la UI se mantiene; los impactos serán reales en fase 2).
7. **Behavioural Assumptions modal**: configuración de NMD, prepagos, term deposits (la UI se mantiene; uso en cálculo será fase 3).
8. **EVEChart y NIIChart**: gráficos de resultados.
9. **Gestión de sesiones**: creación, persistencia, recuperación.

---

## 9. CÓMO INVOCAR EL MOTOR DESDE EL BACKEND

**Opción recomendada: importación directa como librería Python.**

Una vez copiado `almready/` dentro de `backend/`, el endpoint puede hacer:

```python
import pandas as pd
from almready.services.market import load_forward_curve_set, ForwardCurveSet
from almready.core.curves import curve_from_long_df, ForwardCurve
from almready.services.eve import run_eve_scenarios
from almready.services.nii import run_nii_12m_scenarios
from almready.services.regulatory_curves import build_regulatory_curve_sets
from almready.services.margin_engine import calibrate_margin_set

# 1. Construir DataFrame de posiciones desde balance_positions.json
positions_df = pd.DataFrame(positions_data)

# 2. Construir ForwardCurveSet desde curves_points.json
# Convertir {curve_id: [{tenor, t_years, rate}]} → DataFrame long → ForwardCurveSet
long_rows = []
for curve_id, points in curves_data.items():
    for p in points:
        long_rows.append({
            "IndexName": curve_id,
            "Tenor": p["tenor"],
            "FwdRate": p["rate"],
            "TenorDate": add_tenor(analysis_date, p["tenor"]),  # Calcular fecha
            "YearFrac": p["t_years"],
        })
df_long = pd.DataFrame(long_rows)
curves_dict = {}
for idx_name in df_long["IndexName"].unique():
    subset = df_long[df_long["IndexName"] == idx_name]
    curves_dict[idx_name] = curve_from_long_df(subset, idx_name)

base_curve_set = ForwardCurveSet(
    analysis_date=analysis_date,
    base="ACT/365",
    points=df_long,
    curves=curves_dict,
)

# 3. Generar curvas estresadas
scenario_curve_sets = build_regulatory_curve_sets(
    base_curve_set,
    scenarios=scenario_ids,
    risk_free_index=risk_free_index,
    currency=currency,
)

# 4. Ejecutar EVE
eve_result = run_eve_scenarios(
    positions=positions_df,
    base_discount_curve_set=base_curve_set,
    scenario_discount_curve_sets=scenario_curve_sets,
    analysis_date=analysis_date,
    method="exact",
)

# 5. Ejecutar NII
nii_result = run_nii_12m_scenarios(
    positions=positions_df,
    base_curve_set=base_curve_set,
    scenario_curve_sets=scenario_curve_sets,
    analysis_date=analysis_date,
    risk_free_index=risk_free_index,
    balance_constant=True,
)

# 6. Transformar a formato API
api_results = motor_results_to_api(eve_result, nii_result)
```

**IMPORTANTE**: Las funciones del motor esperan un DataFrame con columnas en el esquema canónico (contract_id, start_date, maturity_date, notional, side, rate_type, daycount_base, source_contract_type, etc.). Si `balance_positions.json` no tiene esas columnas exactas, necesitas un paso de transformación.

---

## 10. FLUJO SCHEDULED — DETALLE ESPECIAL

Los contratos `fixed_scheduled` y `variable_scheduled` necesitan flujos de principal explícitos (tabla `principal_flows`). El motor los lee con `scheduled_reader.py`.

Para la integración:
- Si el balance subido contiene contratos scheduled, los flujos deben cargarse y pasarse al motor como `scheduled_flow_map` (dict: contract_id → [(fecha, monto_principal)]).
- Si no hay contratos scheduled, se puede omitir.

---

## 11. REGLAS DE INVALIDACIÓN DE CACHE

Implementar en el backend:

| Evento | Qué se invalida |
|--------|-----------------|
| Cambia balance (re-upload) | Todo: posiciones, resultados, contribuciones |
| Cambia curvas (re-upload) | Resultados + contribuciones (posiciones OK) |
| Cambia selección de escenarios | Resultados (posiciones + curvas OK) |
| Cambia What-If | En fase 1: requiere recálculo. En fase 2: solo delta |
| Cambia behavioural params | Lo que afecte (fase 3) |

**Implementación mínima**: antes de devolver resultados cacheados, verificar que el hash de (positions + curves + scenarios) no ha cambiado. Si cambió, invalidar y recalcular.

---

## 12. ORDEN DE EJECUCIÓN RECOMENDADO

Sigue este orden estrictamente:

### Paso 1: Copiar motor al backend
- Copiar `almready/` → `backend/almready/`
- Actualizar `requirements.txt`
- Verificar que `import almready` funciona desde el backend

### Paso 2: Crear endpoint de cálculo básico
- Nuevo `POST /api/sessions/{id}/calculate` en `main.py`
- Implementar el adapter de resultados motor → API
- Probar con datos de prueba (los smoke tests del motor tienen datos de ejemplo)

### Paso 3: Adaptar el parser de balance (si es necesario)
- Si el balance que sube el usuario ya viene en formato compatible con el motor: bien.
- Si viene en formato Excel actual del front-back: crear transformación intermedia que genere las columnas del esquema canónico del motor.
- El `balance_positions.json` persistido debe contener AMBOS conjuntos de campos: los del motor (para cálculo) y los de la UI (para visualización).

### Paso 4: Conectar frontend al backend
- Añadir `calculateEveNii()` en `api.ts`
- Modificar `handleCalculate()` en `Index.tsx`
- Eliminar import/uso de `calculationEngine.ts`

### Paso 5: Limpiar ResultsCard
- Eliminar impactos What-If hardcoded
- ResultsCard pinta solo datos reales del backend

### Paso 6: Verificar que nada se ha roto
- Upload de balance → árbol de posiciones visible
- Upload de curvas → gráficos visibles
- View Details → filtros funcionan
- Búsqueda de contratos → paginación funciona
- What-If → UI de add/remove funciona (aunque los impactos serán reales solo en fase 2)
- Calculate → resultados reales de EVE/NII aparecen en ResultsCard, EVEChart, NIIChart

---

## 13. FUERA DE SCOPE (NO HACER AHORA)

- What-If instantáneo con deltas/contribuciones (fase 2)
- Modelo behavioural para NMD/prepagos (fase 3)
- Multi-divisa
- Cache de contribuciones por contrato
- Prepayment models
- UFR extrapolation

---

## 14. PREGUNTAS QUE CLAUDE CODE DEBE RESOLVER LEYENDO EL CÓDIGO

Antes de implementar, lee estos ficheros y responde internamente:

1. **¿Qué columnas tiene `balance_positions.json` actualmente?** → Lee `main.py`, función `_canonicalize_position_row()`.
2. **¿Qué columnas espera el motor?** → Lee `config/bank_mapping_template.py` (REQUIRED_CANONICAL_COLUMNS + OPTIONAL_CANONICAL_COLUMNS).
3. **¿Cómo se construye `ForwardCurveSet` programáticamente?** → Lee `services/market.py` y `core/curves.py`.
4. **¿Qué parámetros exactos esperan `run_eve_scenarios()` y `run_nii_12m_scenarios()`?** → Lee `services/eve.py` y `services/nii.py`.
5. **¿Cómo se mapean los scenario_ids a los shocks?** → Lee `scenarios/regulatory.py`.
6. **¿Qué estructura tienen `EVEPipelineResult` y `NIIPipelineResult`?** → Lee `services/eve_pipeline.py` y `services/nii_pipeline.py`.
7. **¿Cómo invoca `Index.tsx` al cálculo actualmente?** → Lee `src/pages/Index.tsx`, función `handleCalculate()`.
8. **¿Qué espera exactamente `ResultsCard.tsx`?** → Lee el componente y busca dónde usa `results`.
