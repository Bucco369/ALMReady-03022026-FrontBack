# Analisis Tecnico — Motor de Calculo ALMReady

> **Fecha de analisis**: 17 de febrero de 2026
> **Proyecto**: Motor de Calculo IRRBB (almready)
> **Version analizada**: estado actual del branch `master`
> **Alcance**: Analisis exhaustivo de arquitectura, modulos, modelos de datos, logica de calculo y preparacion para integracion con el front-back.

---

## Indice

1. [Vision general del proyecto](#1-vision-general-del-proyecto)
2. [Estructura de directorios](#2-estructura-de-directorios)
3. [Dependencias y stack tecnologico](#3-dependencias-y-stack-tecnologico)
4. [Modulo `core/` — Fundamentos matematicos](#4-modulo-core--fundamentos-matematicos)
   - 4.1 [Curvas forward (`curves.py`)](#41-curvas-forward-curvespy)
   - 4.2 [Convenciones de calculo de dias (`daycount.py`)](#42-convenciones-de-calculo-de-dias-daycountpy)
   - 4.3 [Tenors (`tenors.py`)](#43-tenors-tenorspy)
5. [Modulo `config/` — Adaptacion por banco](#5-modulo-config--adaptacion-por-banco)
   - 5.1 [Template de mapping (`bank_mapping_template.py`)](#51-template-de-mapping-bank_mapping_templatepy)
   - 5.2 [Mapping Unicaja (`bank_mapping_unicaja.py`)](#52-mapping-unicaja-bank_mapping_unicajapy)
   - 5.3 [Buckets EVE (`eve_buckets.py`)](#53-buckets-eve-eve_bucketspy)
6. [Modulo `io/` — Carga y canonicalizacion de datos](#6-modulo-io--carga-y-canonicalizacion-de-datos)
   - 6.1 [Lector de posiciones (`positions_reader.py`)](#61-lector-de-posiciones-positions_readerpy)
   - 6.2 [Pipeline de posiciones (`positions_pipeline.py`)](#62-pipeline-de-posiciones-positions_pipelinepy)
   - 6.3 [Lector de scheduled (`scheduled_reader.py`)](#63-lector-de-scheduled-scheduled_readerpy)
   - 6.4 [Lector de curvas forward (`curves_forward_reader.py`)](#64-lector-de-curvas-forward-curves_forward_readerpy)
7. [Modulo `services/` — Motores de calculo](#7-modulo-services--motores-de-calculo)
   - 7.1 [Curvas de mercado (`market.py`)](#71-curvas-de-mercado-marketpy)
   - 7.2 [Motor de margenes (`margin_engine.py`)](#72-motor-de-margenes-margin_enginepy)
   - 7.3 [Motor EVE (`eve.py`)](#73-motor-eve-evepy)
   - 7.4 [Proyectores NII (`nii_projectors.py`)](#74-proyectores-nii-nii_projectorspy)
   - 7.5 [Motor NII (`nii.py`)](#75-motor-nii-niipy)
   - 7.6 [Curvas regulatorias estresadas (`regulatory_curves.py`)](#76-curvas-regulatorias-estresadas-regulatory_curvespy)
   - 7.7 [Analytics EVE (`eve_analytics.py`)](#77-analytics-eve-eve_analyticspy)
   - 7.8 [Charts EVE y NII (`eve_charts.py`, `nii_charts.py`)](#78-charts-eve-y-nii-eve_chartspy-nii_chartspy)
   - 7.9 [Pipeline EVE (`eve_pipeline.py`)](#79-pipeline-eve-eve_pipelinepy)
   - 7.10 [Pipeline NII (`nii_pipeline.py`)](#710-pipeline-nii-nii_pipelinepy)
8. [Modulo `scenarios/` — Shocks regulatorios](#8-modulo-scenarios--shocks-regulatorios)
   - 8.1 [Parametros regulatorios (`regulatory.py`)](#81-parametros-regulatorios-regulatorypy)
   - 8.2 [Shocks ad-hoc (`shocks.py`)](#82-shocks-ad-hoc-shockspy)
   - 8.3 [Aplicacion de shocks (`apply.py`)](#83-aplicacion-de-shocks-applypy)
9. [Modulo `tests/` — Cobertura de tests](#9-modulo-tests--cobertura-de-tests)
10. [Esquema canonico de datos](#10-esquema-canonico-de-datos)
    - 10.1 [Columnas requeridas y opcionales](#101-columnas-requeridas-y-opcionales)
    - 10.2 [Tipos de contrato soportados](#102-tipos-de-contrato-soportados)
    - 10.3 [Convenciones de signo](#103-convenciones-de-signo)
11. [Flujo de datos end-to-end](#11-flujo-de-datos-end-to-end)
    - 11.1 [Pipeline EVE](#111-pipeline-eve)
    - 11.2 [Pipeline NII](#112-pipeline-nii)
12. [Decisiones de diseno criticas](#12-decisiones-de-diseno-criticas)
13. [Limitaciones actuales y scope futuro](#13-limitaciones-actuales-y-scope-futuro)
14. [Preparacion para integracion con front-back](#14-preparacion-para-integracion-con-front-back)

---

## 1. Vision general del proyecto

ALMReady Motor de Calculo es un motor IRRBB (Interest Rate Risk in the Banking Book) escrito en Python puro. Su objetivo es calcular las dos metricas regulatorias principales:

- **EVE (Economic Value of Equity)**: Valor presente neto de todos los flujos futuros de activos y pasivos, sensible a variaciones en la curva de tipos.
- **NII (Net Interest Income)**: Proyeccion a 12 meses del ingreso/gasto neto por intereses, bajo diferentes escenarios de tipos.

El motor esta disenado como **producto vendible a multiples bancos**. La premisa arquitectonica fundamental es:

> Los motores de calculo (EVE, NII, margenes, curvas) son **universales**.
> Solo la **capa de entrada/mapping** cambia por cliente.

Esto se consigue mediante el sistema de `bank_mapping` en `config/`, donde cada banco define su propio diccionario de traduccion de columnas, escalas numericas, formatos de fecha y SOURCE_SPECS sin modificar una sola linea del motor.

---

## 2. Estructura de directorios

```
almready/
├── core/                          # Fundamentos matematicos
│   ├── curves.py                  # ForwardCurve, interpolacion log-lineal en ln(DF)
│   ├── daycount.py                # Convenciones ACT/360, ACT/365, ACT/ACT, 30/360
│   └── tenors.py                  # Aritmetica de tenors (ON, W, M, Y)
│
├── config/                        # Adaptacion por banco
│   ├── bank_mapping_template.py   # Template base para nuevos bancos
│   ├── bank_mapping_unicaja.py    # Implementacion concreta: Unicaja
│   └── eve_buckets.py             # Buckets temporales para EVE regulatorio y ALCO
│
├── io/                            # Carga y canonicalizacion de datos
│   ├── __init__.py                # Re-exports publicos
│   ├── positions_reader.py        # Lector tabular de posiciones (CSV/Excel)
│   ├── positions_pipeline.py      # Orquestador multi-fichero desde SOURCE_SPECS
│   ├── scheduled_reader.py        # Lector jerarquico contrato+pago (scheduled)
│   └── curves_forward_reader.py   # Lector de curvas forward desde Excel wide
│
├── services/                      # Motores de calculo
│   ├── __init__.py                # Re-exports publicos
│   ├── market.py                  # ForwardCurveSet (contenedor central de curvas)
│   ├── margin_engine.py           # Calibracion de margenes para renovacion
│   ├── eve.py                     # Motor EVE (exact y bucketed)
│   ├── nii_projectors.py          # 8 proyectores NII individuales por tipo de contrato
│   ├── nii.py                     # Orquestador NII (dispatch + perfiles mensuales)
│   ├── regulatory_curves.py       # Generacion de curvas estresadas por escenario
│   ├── eve_analytics.py           # Resumenes y desgloses analiticos EVE
│   ├── eve_charts.py              # Graficos matplotlib para EVE
│   ├── nii_charts.py              # Graficos matplotlib para NII
│   ├── eve_pipeline.py            # Pipeline completo EVE (end-to-end)
│   └── nii_pipeline.py            # Pipeline completo NII (end-to-end)
│
├── scenarios/                     # Shocks regulatorios
│   ├── __init__.py
│   ├── regulatory.py              # EU Reg. 2024/856 (BCBS IRRBB) - parametros y formulas
│   ├── shocks.py                  # Shocks paralelos ad-hoc
│   └── apply.py                   # Aplicacion de shocks sobre curvas
│
├── tests/                         # Tests unitarios y smoke tests
│   ├── test_*.py                  # Tests unitarios (17 ficheros)
│   ├── smoke_*.py                 # Smoke tests end-to-end (4 ficheros)
│   └── out/                       # Outputs generados (PNG, CSV)
│
├── inputs/                        # Datos de ejemplo
│   ├── positions/unicaja/         # 11 CSVs de posiciones Unicaja
│   └── curves/forwards/           # Excel de curvas forward
│
└── docs/                          # Documentacion tecnica
    └── analisis-tecnico-motor-calculo-2026-02-17.md  (este documento)
```

**Metricas del codigo fuente:**

| Modulo | Ficheros .py | Lineas aprox. |
|--------|-------------|---------------|
| `core/` | 3 | ~390 |
| `config/` | 3 | ~420 |
| `io/` | 4 (+init) | ~1,430 |
| `services/` | 10 (+init) | ~4,800 |
| `scenarios/` | 3 (+init) | ~320 |
| `tests/` | 21 | ~2,500 |
| **Total** | **~44** | **~9,860** |

---

## 3. Dependencias y stack tecnologico

- **Python 3.14** (sin framework web ni ORM)
- **pandas** — DataFrames para posiciones, curvas, flujos
- **numpy** — Operaciones vectorizadas (usado implicitamente via pandas)
- **python-dateutil** — `relativedelta` para aritmetica de fechas con tenors
- **matplotlib** — Generacion de graficos PNG (charts de EVE y NII)
- **openpyxl** — Lectura de ficheros Excel (.xlsx) para curvas forward
- **math** (stdlib) — `exp`, `log` para interpolacion de curvas
- **bisect** (stdlib) — Busqueda binaria para interpolacion de pilares

No hay ORM, base de datos, framework web, ni dependencias de red. El motor es una **libreria Python pura** que recibe DataFrames/ficheros y devuelve resultados.

---

## 4. Modulo `core/` — Fundamentos matematicos

### 4.1 Curvas forward (`curves.py`)

**Fichero**: `core/curves.py` (~173 lineas)

Este es el bloque mas critico del motor. Define como se almacenan, interpolan y consultan las curvas de tipos de interes.

#### Estructuras de datos

```python
@dataclass(frozen=True)
class CurvePoint:
    year_frac: float      # T (fraccion de ano desde analysis_date)
    rate: float           # r(T) en decimal, composicion continua
    tenor: str            # "ON", "1M", "3M", "5Y", etc.
    tenor_date: date      # Fecha pilar = analysis_date + tenor
```

```python
@dataclass
class ForwardCurve:
    index_name: str               # e.g. "EURIBOR_3M", "EUR_ESTR_OIS"
    points: list[CurvePoint]      # Pilares ordenados por year_frac
```

#### Interpolacion: log-lineal en ln(DF)

El motor NO interpola directamente sobre rates. En su lugar, opera sobre el logaritmo natural del discount factor:

```
ln(DF_i) = -r_i * T_i    (composicion continua)
```

La interpolacion es **lineal en `ln(DF)` vs `T`**, lo que equivale a **forward instantaneo constante** entre pilares. Esto es matematicamente superior a interpolar rates directamente porque:

1. Garantiza DF(0) = 1 y DF estrictamente decreciente
2. Evita discontinuidades en el forward rate
3. Es la convencion estandar en risk engines profesionales

**Regiones de interpolacion:**

| Region | Comportamiento |
|--------|---------------|
| `t <= 0` | DF = 1.0 |
| `0 < t < primer pilar` | Interpola lineal entre (0, ln(DF)=0) y primer pilar |
| `pilar_i <= t <= pilar_{i+1}` | Interpola lineal en ln(DF) entre pilares adyacentes |
| `t > ultimo pilar` | **Extrapolacion**: extiende pendiente del ultimo tramo en ln(DF) |

La extrapolacion en cola larga implica **flat forward instantaneo** (no flat zero rate). Si se requiere convergencia a UFR (Ultimate Forward Rate) para regulacion Solvencia II, debe implementarse como modo alternativo explicito.

#### Derivacion del zero rate

```python
def zero_rate(self, t: float) -> float:
    # r(t) = -ln(DF(t)) / t
    df = self.discount_factor(t)
    return -log(df) / t
```

Para `t = 0`, devuelve el rate del primer pilar como convencion.

#### Factory function

```python
curve_from_long_df(df_long, index_name, ...) -> ForwardCurve
```

Construye una `ForwardCurve` a partir de un DataFrame en formato long con columnas: `IndexName`, `Tenor`, `FwdRate`, `TenorDate`, `YearFrac`.

---

### 4.2 Convenciones de calculo de dias (`daycount.py`)

**Fichero**: `core/daycount.py` (~183 lineas)

Implementa las 4 bases canonicas del motor:

| Base canonica | Denominador |
|--------------|-------------|
| `ACT/360` | dias_reales / 360 |
| `ACT/365` | dias_reales / 365 |
| `ACT/ACT` (ISDA) | Prorrateo por ano: dias_en_ano_i / diy(ano_i) |
| `30/360` (US) | (360*(Y2-Y1) + 30*(M2-M1) + (D2-D1)) / 360 |

#### Normalizacion robusta

La funcion `normalizar_base_de_calculo(valor)` mapea ~30 variantes tipicas de notacion bancaria a las 4 bases canonicas:

```python
"ACTUAL/360"  -> "ACT/360"
"ACT/365F"    -> "ACT/365"
"ACTACT"      -> "ACT/ACT"
"30E/360ISDA" -> "30/360"
"30/360(US)"  -> "30/360"   # elimina parentesis
```

Elimina espacios, guiones, parentesis, sufijos como `US`, `NASD`, `FIXED`, y variantes de `30E/360`.

#### ACT/ACT ISDA

Cuando `d0` y `d1` estan en el mismo ano:
```
yf = (d1 - d0).days / diy(d0.year)
```

Cuando cruzan anos, prorratea:
```
yf = dias_restantes_ano_d0 / diy(d0.year)
   + (d1.year - d0.year - 1)              # anos completos intermedios
   + dias_transcurridos_ano_d1 / diy(d1.year)
```

#### 30/360 US

Implementa ajustes especiales:
- Fin de febrero: `d0_day = 30` si `d0` es ultimo dia de febrero
- Si `d1` es fin de febrero y `d0_day >= 30`: `d1_day = 30`
- Si `d0_day == 31`: `d0_day = 30`
- Si `d1_day == 31` y `d0_day >= 30`: `d1_day = 30`

---

### 4.3 Tenors (`tenors.py`)

**Fichero**: `core/tenors.py` (~31 lineas)

Funcion unica `add_tenor(d, tenor)` que suma tenors estandar a una fecha:

| Token | Efecto |
|-------|--------|
| `ON`, `O/N`, `1D` | +1 dia |
| `nW` | +n semanas |
| `nM` | +n meses |
| `nY` | +n anos |

Usa `dateutil.relativedelta` para la aritmetica. **No aplica ajuste de calendario habil** (business day adjustment) — esto es intencionado para mantener simplicidad y no depender de calendarios TARGET2/SWIFT.

---

## 5. Modulo `config/` — Adaptacion por banco

### 5.1 Template de mapping (`bank_mapping_template.py`)

**Fichero**: `config/bank_mapping_template.py` (~170 lineas)

Define el **contrato de interfaz** que cada banco debe implementar. Es un fichero Python (no YAML/JSON) para maximizar flexibilidad.

#### Esquema canonico

```python
REQUIRED_CANONICAL_COLUMNS = (
    "contract_id",      # Identificador unico del contrato
    "start_date",       # Fecha de inicio
    "maturity_date",    # Fecha de vencimiento
    "notional",         # Nominal vigente
    "side",             # A (activo) o L (pasivo)
    "rate_type",        # "fixed" o "float"
    "daycount_base",    # Base de calculo (e.g. "ACT/360")
)

OPTIONAL_CANONICAL_COLUMNS = (
    "index_name",              # Indice de referencia (e.g. "EURIBOR_3M")
    "spread",                  # Diferencial sobre indice (en decimal)
    "fixed_rate",              # Tipo fijo (en decimal)
    "repricing_freq",          # Frecuencia de repricing (e.g. "3M", "6M")
    "payment_freq",            # Frecuencia de pago (e.g. "1M", "3M")
    "annuity_payment_mode",    # "reprice_on_reset" o "fixed_payment"
    "next_reprice_date",       # Proxima fecha de repricing
    "floor_rate",              # Suelo de tipo de interes
    "cap_rate",                # Techo de tipo de interes
)
```

#### Diccionarios de configuracion

| Diccionario | Proposito |
|-------------|-----------|
| `BANK_COLUMNS_MAP` | Mapeo nombre_columna_banco -> nombre_canonico |
| `SIDE_MAP` | Normalizacion de lado: "LONG"/"ASSET"/"ACTIVO" -> "A" |
| `RATE_TYPE_MAP` | Normalizacion de tipo: "FIJO"/"FIXED" -> "fixed" |
| `NUMERIC_SCALE_MAP` | Escala post-parsing (e.g. `{"spread": 0.01}` para porcentajes) |
| `DEFAULT_CANONICAL_VALUES` | Defaults inyectados si la columna falta o esta vacia |
| `INDEX_NAME_ALIASES` | Alias de normalizacion de nombres de indice |
| `SOURCE_SPECS` | Configuracion declarativa de fuentes de datos |

#### SOURCE_SPECS (declarativo)

Cada entrada define como cargar un fichero:

```python
{
    "name": "fixed_annuity",           # nombre logico
    "pattern": "Fixed annuity.csv",    # glob relativo a root_path
    "file_type": "csv",                # "csv", "excel", "auto"
    "delimiter": ";",                  # separador CSV
    "encoding": "cp1252",             # codificacion de fichero
    "header_token": "Identifier",      # token para localizar fila de cabecera
    "row_kind_column": 0,             # columna que clasifica filas (contract/payment)
    "include_row_kinds": ["contract"], # tipos de fila a incluir
    "defaults": {"rate_type": "fixed"},# valores default
    "source_contract_type": "fixed_annuity",  # tipo de contrato
    "source_bank": "unicaja",         # banco de origen
}
```

---

### 5.2 Mapping Unicaja (`bank_mapping_unicaja.py`)

**Fichero**: `config/bank_mapping_unicaja.py` (~199 lineas)

Primera implementacion concreta. Diferencias clave respecto al template:

1. **`maturity_date` es OPCIONAL** (no requerido) — necesario para productos non-maturity.
2. **10 SOURCE_SPECS** para los 10 ficheros CSV de Unicaja.
3. **`NUMERIC_SCALE_MAP`** escala rates por 0.01 (Unicaja envia porcentajes: 2.50 = 2.50%).
4. **`INDEX_NAME_ALIASES`** maneja problemas de encoding con la n con tilde (DEUDA_ESPANOLA).
5. **Delimitador `;`**, encoding `cp1252`, `DATE_DAYFIRST = True`.

#### Mapeo de columnas Unicaja -> canonico

```
"Identifier"              -> contract_id
"Start date"              -> start_date
"Maturity date"           -> maturity_date
"Outstanding principal"   -> notional
"Position"                -> side        (LONG -> A, SHORT -> L)
"Day count convention"    -> daycount_base
"Indexed curve"           -> index_name
"Interest spread"         -> spread
"Indexed rate"            -> fixed_rate  (para fijos)
"Last adjusted rate"      -> fixed_rate  (fallback si "Indexed rate" no existe)
"Reset period"            -> repricing_freq
"Payment period"          -> payment_freq
"Interest payment period" -> payment_freq (alias)
"Reset anchor date"       -> next_reprice_date
"Interest rate floor"     -> floor_rate
"Interest rate cap"       -> cap_rate
```

#### Los 10 tipos de contrato Unicaja

| # | source_contract_type | Fichero | rate_type default |
|---|---------------------|---------|-------------------|
| 1 | `fixed_annuity` | Fixed annuity.csv | fixed |
| 2 | `fixed_bullet` | Fixed bullet.csv | fixed |
| 3 | `fixed_linear` | Fixed linear.csv | fixed |
| 4 | `fixed_scheduled` | Fixed scheduled.csv | fixed |
| 5 | `fixed_non_maturity` | Non-maturity.csv | fixed |
| 6 | `variable_annuity` | Variable annuity.csv | float |
| 7 | `variable_bullet` | Variable bullet.csv | float |
| 8 | `variable_linear` | Variable linear.csv | float |
| 9 | `variable_non_maturity` | Variable non-maturity.csv | float |
| 10 | `variable_scheduled` | Variable scheduled.csv | float |

> **Nota**: `Static_position.csv` esta deliberadamente excluido — carece de campos clave (start/maturity/daycount) necesarios para los pipelines de NII/EVE.

---

### 5.3 Buckets EVE (`eve_buckets.py`)

**Fichero**: `config/eve_buckets.py` (~53 lineas)

Define dos rejillas de buckets temporales:

#### `DEFAULT_REGULATORY_BUCKETS` (18 buckets)

Alineados con los buckets regulatorios BCBS/EBA:

```
0-1M, 1-3M, 3-6M, 6-9M, 9-12M,
1-1.5Y, 1.5-2Y, 2-3Y, 3-4Y, 4-5Y,
5-6Y, 6-7Y, 7-8Y, 8-9Y, 9-10Y,
10-15Y, 15-20Y, 20Y+
```

El ultimo bucket (`20Y+`) es abierto (`end_years = None`). Su punto representativo para descuento se calcula como `20 + open_ended_years/2`, con default `open_ended_years = 10.0` produciendo un midpoint de 25 anos (alineado con BCBS d368 que asume rango 20-30Y).

#### `EVE_VIS_BUCKETS_OPTIMAL` (15 buckets)

Optimizados para visualizacion ALCO con mas detalle en corto plazo y granularidad progresiva en plazos largos. Extiende hasta 50Y+ para posiciones de deuda publica a muy largo plazo.

---

## 6. Modulo `io/` — Carga y canonicalizacion de datos

### 6.1 Lector de posiciones (`positions_reader.py`)

**Fichero**: `io/positions_reader.py` (~746 lineas)

Es el modulo mas extenso de la capa IO. Responsable de:

1. **Lectura raw** de CSV/Excel
2. **Mapeo** de columnas banco -> canonico
3. **Parsing numerico** robusto (comas, puntos, porcentajes)
4. **Parsing de fechas** con soporte `dayfirst`
5. **Normalizacion categorica** (side, rate_type, daycount_base, index_name)
6. **Aplicacion de defaults** y escalas numericas
7. **Validacion** de integridad

#### Funciones principales

**`read_tabular_raw(path, ...)`** — Lectura bruta del fichero:
- Detecta formato por extension (`.csv` / `.xlsx` / `.xls`)
- Soporta `header_token` para localizar la fila de cabecera en ficheros con cabeceras no estandar
- Soporta `row_kind_column` + `include_row_kinds` para filtrar filas por tipo (e.g., solo "contract", no "payment")

**`read_positions_dataframe(df, mapping_module, ...)`** — Canonicalizacion sobre DataFrame:
- Aplica `BANK_COLUMNS_MAP` para renombrar columnas
- Parsea numericos con `_parse_numeric_series()` (maneja `1.234,56` y `1,234.56`)
- Parsea fechas con `pd.to_datetime(dayfirst=...)`
- Normaliza `side` via `SIDE_MAP` y `rate_type` via `RATE_TYPE_MAP`
- Normaliza `daycount_base` via `normalizar_base_de_calculo()`
- Aplica `NUMERIC_SCALE_MAP` (e.g., multiplicar spread por 0.01)
- Aplica `DEFAULT_CANONICAL_VALUES` donde la columna falta o esta vacia
- Aplica `INDEX_NAME_ALIASES` para normalizar nombres de indice
- Si `PRESERVE_UNMAPPED_COLUMNS = True`, conserva columnas extra con prefijo `extra_`

**`read_positions_tabular(path, mapping_module, ...)`** — Wrapper completo: lee raw + canonicaliza.

#### Validaciones de integridad

El reader valida:
- Columnas requeridas no nulas
- `start_date < maturity_date` (donde maturity_date existe)
- Posiciones `float` tienen `index_name` no vacio
- Posiciones `fixed` tienen `fixed_rate` no nulo
- `side` esta en {A, L}
- `rate_type` esta en {fixed, float}

---

### 6.2 Pipeline de posiciones (`positions_pipeline.py`)

**Fichero**: `io/positions_pipeline.py` (~133 lineas)

Orquesta la carga multi-fichero desde SOURCE_SPECS:

```python
def load_positions_from_specs(root_path, mapping_module, *, source_specs=None) -> pd.DataFrame
```

Para cada spec en SOURCE_SPECS:
1. Resuelve el glob pattern contra `root_path`
2. Para cada fichero match, para cada sheet:
   - Llama a `read_positions_tabular()` con parametros del spec
   - Anade columnas de metadata: `source_spec`, `source_file`, `source_sheet`, `source_bank`, `source_contract_type`
3. Concatena todos los DataFrames resultantes

Si un pattern no resuelve y `required=True` (default), lanza `FileNotFoundError`.

---

### 6.3 Lector de scheduled (`scheduled_reader.py`)

**Fichero**: `io/scheduled_reader.py` (~403 lineas)

Maneja ficheros con **estructura jerarquica** donde las filas alternan entre:
- Filas de **contrato** (con datos del instrumento)
- Filas de **pago** (flujos de principal vinculados al contrato previo)

#### Resultado

```python
@dataclass
class ScheduledLoadResult:
    contracts: pd.DataFrame         # Posiciones canonicalizadas
    principal_flows: pd.DataFrame   # Flujos de principal
```

La tabla `principal_flows` tiene columnas:
```
contract_id | flow_type | flow_date | principal_amount | source_row
```

#### Algoritmo de parsing

El lector recorre las filas secuencialmente. Mantiene un puntero al "contrato activo":
- Cuando encuentra una fila de tipo `contract`, la anade a la lista de contratos y la marca como contrato activo.
- Cuando encuentra una fila de tipo `payment`, la vincula al contrato activo por posicion.
- Si encuentra un payment sin contrato activo, lanza error.

**`load_scheduled_from_specs()`** — Equivalente multi-fichero para scheduled, analogamente a `load_positions_from_specs()`.

---

### 6.4 Lector de curvas forward (`curves_forward_reader.py`)

**Fichero**: `io/curves_forward_reader.py` (~151 lineas)

Pipeline completo para cargar curvas forward desde Excel:

1. **`read_forward_curves_wide(path, sheet_name)`** — Lee Excel con formato:
   - Columna A: `IndexName` (e.g., "EURIBOR_3M")
   - Columnas B+: Tenors como cabecera ("ON", "1M", "3M", ..., "30Y")
   - Valores: rates en decimal

2. **`wide_to_long(df_wide)`** — Melt a formato long:
   ```
   IndexName | Tenor | FwdRate
   ```

3. **`enrich_with_dates(df_long, analysis_date, base)`** — Anade:
   - `TenorDate` = `analysis_date + add_tenor(tenor)`
   - `YearFrac` = `yearfrac(analysis_date, tenor_date, base)`

4. **`load_forward_curves(path, analysis_date, base)`** — Pipeline completo: wide -> long -> enriched.

---

## 7. Modulo `services/` — Motores de calculo

### 7.1 Curvas de mercado (`market.py`)

**Fichero**: `services/market.py` (~151 lineas)

Define el **contenedor central de curvas** que usa todo el motor:

```python
@dataclass
class ForwardCurveSet:
    analysis_date: date                    # Fecha de valoracion
    base: str                              # Base de calculo para yearfrac (e.g. "ACT/365")
    points: pd.DataFrame                   # Tabla long canonica (para debug/export)
    curves: dict[str, ForwardCurve]       # index_name -> ForwardCurve
```

#### API principal

| Metodo | Descripcion |
|--------|-------------|
| `get(index_name)` | Obtiene ForwardCurve por nombre de indice |
| `rate_on_date(index_name, d)` | Zero rate (comp. continua) en fecha `d` |
| `df_on_date(index_name, d)` | Discount factor en fecha `d` |
| `require_indices(required)` | Valida que todos los indices requeridos existen |
| `require_float_index_coverage(positions)` | Valida cobertura de curvas para posiciones float |

La conversion fecha -> year_frac usa internamente `yearfrac(analysis_date, d, base)`.

#### Factory function

```python
load_forward_curve_set(path, analysis_date, base, sheet_name) -> ForwardCurveSet
```

Pipeline completo: Excel -> long canonic -> ForwardCurve por indice -> ForwardCurveSet.

---

### 7.2 Motor de margenes (`margin_engine.py`)

**Fichero**: `services/margin_engine.py` (~322 lineas)

El motor de margenes es critico para la asuncion de **balance constante** en NII. Cuando un contrato vence dentro del horizonte de 12 meses, se renueva al tipo de mercado + un margen calibrado. Este modulo calibra dichos margenes.

#### Calibracion

```python
calibrate_margin_set(recent_positions, *, curve_set, risk_free_index, ...) -> CalibratedMarginSet
```

**Para contratos fijos:**
```
margin = fixed_rate - rf(benchmark_date)
```
Donde `benchmark_date` depende de:
- Con `repricing_freq`: `as_of + repricing_freq`
- Sin `repricing_freq`: `as_of + plazo_original` (maturity - start)
- Fallback: `as_of + 1Y`

**Para contratos float:**
```
margin = spread
```

Los margenes se ponderan por notional absoluto y se agregan por dimensiones: `(source_contract_type, side, repricing_freq, index_name)`.

#### Lookup jerarquico

`CalibratedMarginSet.lookup_margin()` busca el margen con granularidad decreciente:

```
1. (source_contract_type, side, repricing_freq, index_name)  # mas especifico
2. (source_contract_type, side, repricing_freq)
3. (source_contract_type, repricing_freq)
4. (source_contract_type, side)
5. (source_contract_type,)
6. (repricing_freq,)
7. ()                                                          # agregado global
```

Esto permite que el motor encuentre un margen razonable incluso cuando no hay datos exactos para todas las dimensiones.

#### Persistencia

- `save_margin_set_csv(margin_set, path)` — Export a CSV
- `load_margin_set_csv(path)` — Import desde CSV

---

### 7.3 Motor EVE (`eve.py`)

**Fichero**: `services/eve.py` (~1,464 lineas)

El modulo mas grande del motor. Calcula el Economic Value of Equity mediante dos metodos:

#### Metodo `exact` (flow-by-flow)

1. **Genera cashflows** via `build_eve_cashflows()` para cada contrato
2. **Descuenta cada flujo** individualmente con `DF(t_flujo)`
3. **Suma** todos los PVs (signed: activos positivos, pasivos negativos)

#### Metodo `bucketed`

1. **Asigna cashflows a buckets temporales** usando `EVEBucket.contains(t)`
2. **Agrega notional por bucket**
3. **Descuenta** cada bucket usando `DF(representative_t)` del midpoint del bucket

#### EVEBucket

```python
@dataclass(frozen=True)
class EVEBucket:
    name: str
    start_years: float
    end_years: float | None = None  # None = bucket abierto (e.g. 20Y+)

    def contains(self, t_years) -> bool: ...
    def representative_t(self, *, open_ended_years=10.0) -> float: ...
```

#### Generacion de cashflows

`build_eve_cashflows()` genera el run-off completo (todos los flujos futuros hasta vencimiento) para los 8 tipos de contrato soportados:

| Tipo de contrato | Logica de cashflows |
|-----------------|---------------------|
| `fixed_bullet` | Intereses periodicos + principal al vencimiento |
| `fixed_annuity` | Cuota constante (French amortization) hasta vencimiento |
| `fixed_linear` | Amortizacion lineal + intereses decrecientes |
| `fixed_scheduled` | Flujos de principal explicitos + intereses sobre balance residual |
| `variable_bullet` | Intereses con reset periodico + principal al vencimiento |
| `variable_annuity` | Cuota con reset periodico (dos modos: reprice_on_reset / fixed_payment) |
| `variable_linear` | Amortizacion lineal + intereses con reset |
| `variable_scheduled` | Flujos explicitos + intereses con reset |

Para **productos variable**, EVE genera "stubs" (periodos parciales) en cada fecha de reset, proyectando el tipo forward para calcular los flujos futuros.

#### Convenciones de signo

```
Activo  (side = "A"): sign = +1  (el banco recibe cashflows)
Pasivo  (side = "L"): sign = -1  (el banco paga cashflows)
```

El EVE se calcula como:
```
EVE = sum(PV_activos) + sum(PV_pasivos)    [pasivos ya negativos]
    = sum(PV_activos) - |sum(PV_pasivos)|
```

#### Funciones de orquestacion

```python
run_eve_base(positions, base_discount_curve_set, ...) -> float
run_eve_scenarios(positions, base_..., scenario_...) -> EVERunResult
```

`run_eve_scenarios` calcula EVE base y luego re-evalua bajo cada escenario estresado, devolviendo:

```python
@dataclass
class EVERunResult:
    analysis_date: Any
    method: str           # "exact" o "bucketed"
    base_eve: float
    scenario_eve: dict[str, float]  # scenario_name -> EVE estresado
```

---

### 7.4 Proyectores NII (`nii_projectors.py`)

**Fichero**: `services/nii_projectors.py` (~1,899 lineas)

El modulo mas extenso del proyecto. Contiene **8 funciones de proyeccion NII** (una por tipo de contrato), cada una proyectando el ingreso/gasto por intereses a 12 meses.

#### Funcion comun a todos los proyectores

Cada proyector recibe:
- `row`: una fila del DataFrame de posiciones (dict-like)
- `curve_set`: `ForwardCurveSet` para consultar tipos forward
- `analysis_date`: fecha de valoracion
- `months`: horizonte en meses (default 12)
- `balance_constant`: booleano para renovacion automatica
- `margin_set`: `CalibratedMarginSet` (opcional)
- `scheduled_flow_map`: mapa de flujos para scheduled (solo scheduled types)
- `variable_annuity_payment_mode`: modo de cuota para variable annuity

Y devuelve un `float`: el NII total (signed) del contrato para el horizonte.

#### Logica de balance constante (renovacion)

Cuando `balance_constant = True` y un contrato vence dentro del horizonte:

1. Se calcula el NII **pre-vencimiento** normalmente
2. En la fecha de vencimiento, el contrato se "renueva":
   - **Fijo**: nuevo_rate = rf(vencimiento, tenor_original) + margen_calibrado
   - **Float**: se mantiene el indice + spread original (el spread es el margen)
3. Se calcula el NII **post-renovacion** hasta fin del horizonte

La renovacion mantiene el mismo notional, daycount_base y payment_freq que el contrato original.

#### Detalle por tipo de proyector

**`project_fixed_bullet_nii_12m`**:
- Intereses = notional * fixed_rate * yearfrac(period)
- Si vence en el horizonte y balance_constant: renueva con nuevo tipo fijo

**`project_fixed_annuity_nii_12m`**:
- Cuota French constante: `PMT = notional * r / (1 - (1+r)^{-n})`
- Intereses = balance_residual * rate * yearfrac
- Amortizacion = cuota - intereses (balance decrece)

**`project_fixed_linear_nii_12m`**:
- Amortizacion periodica constante = notional / numero_periodos
- Intereses = balance_residual * rate * yearfrac (decreciente)

**`project_fixed_scheduled_nii_12m`**:
- Usa `scheduled_flow_map` (contrato_id -> [(fecha, monto_principal)])
- Aplica amortizaciones explicitas, calcula intereses sobre balance residual

**`project_variable_bullet_nii_12m`**:
- Rate = forward_rate(index, reset_date) + spread
- Floor/cap sobre rate all-in (no sobre indice aislado)
- En cada reset: recalcula rate
- Si vence y balance_constant: renueva

**`project_variable_annuity_nii_12m`** (2 modos):
- **`reprice_on_reset`** (legacy): En cada reset, recalcula cuota French con nuevo rate y balance residual
- **`fixed_payment`**: Cuota fija durante todo el ciclo de tipo; solo cambia la descomposicion intereses/amortizacion en cada reset

**`project_variable_linear_nii_12m`**:
- Amortizacion lineal constante
- Rate variable: forward + spread (con floor/cap) en cada reset

**`project_variable_scheduled_nii_12m`**:
- Combinacion de flujos scheduled + rate variable con resets

#### Floor/Cap

```python
all_in_rate = forward_rate + spread
capped = min(all_in_rate, cap_rate)  if cap_rate exists
floored = max(capped, floor_rate)     if floor_rate exists
```

Aplicados sobre el **tipo all-in**, no sobre el indice aislado. Esta es la convencion estandar en banca europea.

#### Utilidades compartidas

El fichero exporta ~20 funciones auxiliares usadas tanto por NII como por EVE:

- `_build_payment_dates()` / `_build_reset_dates()` — Generacion de calendarios
- `_annuity_payment_amount()` — Calculo de cuota French
- `_apply_floor_cap()` — Aplicacion de suelo/techo
- `_linear_notional_at()` — Balance residual para amortizacion lineal
- `_side_sign()` — Signo segun activo/pasivo
- `_coerce_date()` / `_coerce_float()` — Parsing robusto de valores individuales
- `_parse_frequency_token()` — Parsing de tokens de frecuencia ("3M", "6M", etc.)

---

### 7.5 Motor NII (`nii.py`)

**Fichero**: `services/nii.py` (~480 lineas)

Orquesta el calculo NII sobre todo el portfolio:

#### Dispatch por tipo de contrato

```python
_IMPLEMENTED_SOURCE_CONTRACT_TYPES = {
    "fixed_annuity", "fixed_bullet", "fixed_linear", "fixed_scheduled",
    "variable_annuity", "variable_bullet", "variable_linear", "variable_scheduled",
}
```

Para cada posicion, `run_nii_12m_base()` identifica su `source_contract_type` y delega al proyector correspondiente.

#### Funciones principales

**`run_nii_12m_base()`**: Calcula NII base (sin stress).
**`run_nii_12m_scenarios()`**: Calcula NII base + NII bajo cada escenario estresado.

```python
@dataclass
class NIIRunResult:
    analysis_date: Any
    base_nii_12m: float
    scenario_nii_12m: dict[str, float]
```

**`build_nii_monthly_profile()`**: Desglosa el NII en 12 columnas mensuales (income, expense, net por mes), util para reporting y graficos.

```python
@dataclass
class NIIMonthlyProfileResult:
    run_result: NIIRunResult
    monthly_profile: pd.DataFrame
```

#### Auto-calibracion de margenes

Si `balance_constant = True` y no se proporciona `margin_set`, el motor lo calibra automaticamente:

```python
if balance_constant and margin_set is None:
    margin_set = calibrate_margin_set(
        positions, curve_set=base_curve_set, risk_free_index=risk_free_index
    )
```

---

### 7.6 Curvas regulatorias estresadas (`regulatory_curves.py`)

**Fichero**: `services/regulatory_curves.py` (~154 lineas)

Genera versiones estresadas del `ForwardCurveSet` para cada escenario regulatorio.

#### Para el indice risk-free

```python
stressed_rate(t) = apply_regulatory_shock_rate(base_rate(t), t, scenario_id, ...)
```

Donde `apply_regulatory_shock_rate` viene de `scenarios/regulatory.py`.

#### Para indices no risk-free (preservacion de basis)

Si `preserve_basis_for_non_risk_free = True` (default):

```
idx_stressed(t) = rf_stressed(t) + (idx_base(t) - rf_base(t))
```

Es decir, el **spread sobre risk-free** (basis) se mantiene constante bajo stress. Solo se mueve la curva risk-free; los demas indices se desplazan en paralelo manteniendo su basis.

Esta es la convencion regulatoria: el IRRBB solo mide riesgo de tipos de interes, no riesgo de basis.

#### Salida

```python
build_regulatory_curve_sets(base_set, *, scenarios, risk_free_index, currency, ...)
    -> dict[str, ForwardCurveSet]
```

Devuelve un diccionario `scenario_name -> ForwardCurveSet_estresado`.

---

### 7.7 Analytics EVE (`eve_analytics.py`)

**Fichero**: `services/eve_analytics.py`

Funciones analiticas post-calculo:

**`build_eve_scenario_summary(base_eve, scenario_eve)`** — Tabla resumen:
```
scenario | eve_value | delta_vs_base | delta_pct
```

**`build_eve_bucket_breakdown_exact()`** — Desglose per-bucket:
```
bucket | asset_pv | liability_pv | net_pv | base_scenario_pv | worst_scenario_pv | delta
```

Nota: el PV por bucket es siempre **exacto** (flow-by-flow); el bucket solo se usa para agrupar, no para aproximar.

**`worst_scenario_from_summary()`** — Identifica el escenario con mayor impacto negativo sobre EVE.

---

### 7.8 Charts EVE y NII (`eve_charts.py`, `nii_charts.py`)

#### EVE Charts

- `plot_eve_scenario_deltas()` — Barras horizontales: delta EVE por escenario
- `plot_eve_base_vs_worst_by_bucket()` — Barras agrupadas: base vs worst por bucket
- `plot_eve_worst_delta_by_bucket()` — Barras: delta neto por bucket + linea acumulada

#### NII Charts

- `plot_nii_monthly_profile()` — Lineas: income/expense/net por mes para base y escenarios
- `plot_nii_base_vs_worst_by_month()` — Comparacion base vs peor escenario por mes

Todos los graficos: matplotlib, 180 DPI, salida PNG.

---

### 7.9 Pipeline EVE (`eve_pipeline.py`)

**Fichero**: `services/eve_pipeline.py` (~281 lineas)

Punto de entrada unico para ejecutar EVE end-to-end:

```python
run_eve_from_specs(
    *, positions_root_path, mapping_module, curves_path,
    analysis_date, risk_free_index, currency, scenario_ids,
    method, buckets, ...
) -> EVEPipelineResult
```

#### Flujo interno

```
1. load_positions_and_scheduled_flows()     # Carga posiciones + flujos scheduled
2. Filtrar source_contract_types soportados  # Excluir static_position y desconocidos
3. load_forward_curve_set()                  # Cargar curvas base desde Excel
4. build_regulatory_curve_sets()             # Generar curvas estresadas
5. run_eve_scenarios()                       # Calcular EVE base + escenarios
6. build_eve_scenario_summary()              # Resumen analitico
7. build_eve_bucket_breakdown_exact()        # Desglose por bucket
8. plot_eve_*()                              # Graficos (opcional)
9. export CSVs                               # Tablas (opcional)
```

#### Resultado

```python
@dataclass
class EVEPipelineResult:
    analysis_date: date
    method: str
    base_eve: float
    scenario_eve: dict[str, float]
    scenario_summary: pd.DataFrame
    worst_scenario: str | None
    bucket_breakdown: pd.DataFrame
    chart_paths: dict[str, Path]
    table_paths: dict[str, Path]
    positions_count: int
    scheduled_flows_count: int
    excluded_source_contract_types: dict[str, int]
```

---

### 7.10 Pipeline NII (`nii_pipeline.py`)

**Fichero**: `services/nii_pipeline.py` (~199 lineas)

Punto de entrada unico para ejecutar NII end-to-end:

```python
run_nii_from_specs(
    *, positions_root_path, mapping_module, curves_path,
    analysis_date, risk_free_index, currency, scenario_ids,
    balance_constant, variable_annuity_payment_mode, ...
) -> NIIPipelineResult
```

#### Flujo interno

```
1. load_positions_and_scheduled_flows()     # Reutiliza funcion de eve_pipeline
2. Filtrar source_contract_types soportados
3. load_forward_curve_set()                  # Curvas base
4. build_regulatory_curve_sets()             # Curvas estresadas
5. run_nii_12m_scenarios_with_monthly_profile()  # NII + perfil mensual
6. plot_nii_monthly_profile()                # Grafico base+escenarios (opcional)
7. plot_nii_base_vs_worst_by_month()         # Grafico base vs worst (opcional)
```

#### Parametros destacados

| Parametro | Default | Descripcion |
|-----------|---------|-------------|
| `balance_constant` | `True` | Renovar contratos que vencen en horizonte |
| `margin_lookback_months` | `12` | Ventana para calibracion de margenes |
| `variable_annuity_payment_mode` | `"reprice_on_reset"` | Modo de cuota variable annuity |

---

## 8. Modulo `scenarios/` — Shocks regulatorios

### 8.1 Parametros regulatorios (`regulatory.py`)

**Fichero**: `scenarios/regulatory.py` (~235 lineas)

Implementa la normativa **EU Regulation (Delegated) 2024/856** (derivada de BCBS IRRBB standards).

#### Escenarios oficiales

**EVE**: 6 escenarios
```
parallel-up, parallel-down, short-up, short-down, steepener, flattener
```

**NII**: 2 escenarios
```
parallel-up, parallel-down
```

Ademas, 2 escenarios internos opcionales: `long-up`, `long-down`.

#### Formulas de shock

Para una maturity `t` en anos:

| Escenario | Formula |
|-----------|---------|
| `parallel-up` | `+R_parallel` |
| `parallel-down` | `-R_parallel` |
| `short-up` | `+R_short * exp(-t/4)` |
| `short-down` | `-R_short * exp(-t/4)` |
| `long-up` | `+R_long * (1 - exp(-t/4))` |
| `long-down` | `-R_long * (1 - exp(-t/4))` |
| `steepener` | `-0.65 * |delta_short| + 0.90 * |delta_long|` |
| `flattener` | `+0.80 * |delta_short| - 0.60 * |delta_long|` |

La funcion `exp(-t/4)` produce un decaimiento exponencial: los shocks short tienen maximo impacto en t=0 y decaen hacia 0 en plazos largos; los shocks long tienen impacto 0 en t=0 y convergen a `R_long` en plazos largos.

#### Parametros por divisa (Annex Part A)

27 divisas con shocks calibrados en bps:

```python
"EUR": CurrencyShockBps(parallel=200, short=250, long=100)
"USD": CurrencyShockBps(parallel=200, short=300, long=150)
"GBP": CurrencyShockBps(parallel=250, short=300, long=150)
"JPY": CurrencyShockBps(parallel=100, short=100, long=100)
# ... 23 mas
```

#### Post-shock floor

Implementa Art. 3(7) del reglamento:

```python
floor(t) = min(max_floor, immediate_floor + annual_step * t)
```

Con defaults:
- `immediate_floor = -1.50%`
- `annual_step = +0.03%` por ano
- `max_floor = 0.0%`

El floor efectivo es: `min(floor_curve, base_rate)` — nunca se eleva por encima del rate base observado.

---

### 8.2 Shocks ad-hoc (`shocks.py`)

Soporte para shocks paralelos simples fuera del marco regulatorio:

```python
apply_parallel_shock(curve_set, shock_bps) -> ForwardCurveSet
```

Util para analisis what-if rapidos.

---

### 8.3 Aplicacion de shocks (`apply.py`)

Funciones auxiliares para aplicar shocks sobre DataFrames de curvas forward, desplazando `FwdRate` por una cantidad en bps.

---

## 9. Modulo `tests/` — Cobertura de tests

### Tests unitarios (17 ficheros)

| Test | Modulo bajo test | Que valida |
|------|-----------------|------------|
| `test_curve_interpolation.py` | `core/curves` | Interpolacion log-lineal, extrapolacion, DF |
| `test_eve_engine.py` | `services/eve` | EVE exact y bucketed, signos, multiples tipos |
| `test_eve_analytics.py` | `services/eve_analytics` | Resumenes, breakdown por bucket |
| `test_margin_engine.py` | `services/margin_engine` | Calibracion, lookup jerarquico |
| `test_market_loader.py` | `services/market` | Carga de ForwardCurveSet |
| `test_nii_fixed_annuity.py` | `nii_projectors` | NII annuity fijo, cuota French |
| `test_nii_fixed_bullet.py` | `nii_projectors` | NII bullet fijo |
| `test_nii_fixed_linear.py` | `nii_projectors` | NII lineal fijo |
| `test_nii_fixed_scheduled.py` | `nii_projectors` | NII scheduled fijo |
| `test_nii_variable_annuity.py` | `nii_projectors` | NII annuity variable (2 modos) |
| `test_nii_variable_bullet.py` | `nii_projectors` | NII bullet variable + floor/cap |
| `test_nii_variable_linear.py` | `nii_projectors` | NII lineal variable |
| `test_nii_variable_scheduled.py` | `nii_projectors` | NII scheduled variable |
| `test_nii_monthly_profile.py` | `services/nii` | Perfil mensual income/expense/net |
| `test_positions_pipeline.py` | `io/positions_pipeline` | Carga multi-fichero |
| `test_regulatory_curves.py` | `services/regulatory_curves` | Curvas estresadas, basis preservation |
| `test_scheduled_reader.py` | `io/scheduled_reader` | Parsing jerarquico |

### Smoke tests (4 ficheros)

| Smoke test | Que ejecuta |
|-----------|------------|
| `smoke_eve_unicaja.py` | Pipeline EVE completo con datos Unicaja |
| `smoke_nii_unicaja.py` | Pipeline NII completo con datos Unicaja |
| `smoke_market_plot.py` | Visualizacion de curvas forward |
| `smoke_market_view.py` | Inspeccion de ForwardCurveSet |

Los smoke tests generan outputs en `tests/out/`: graficos PNG y tablas CSV.

---

## 10. Esquema canonico de datos

### 10.1 Columnas requeridas y opcionales

#### Posiciones (despues de canonicalizacion)

| Columna | Tipo | Requerida | Descripcion |
|---------|------|-----------|-------------|
| `contract_id` | str | Si | Identificador unico |
| `start_date` | date | Si | Fecha de inicio del contrato |
| `maturity_date` | date | Depende* | Fecha de vencimiento |
| `notional` | float | Si | Nominal vigente (siempre positivo) |
| `side` | str | Si | "A" (activo) o "L" (pasivo) |
| `rate_type` | str | Si | "fixed" o "float" |
| `daycount_base` | str | Si | Base normalizada (e.g. "ACT/360") |
| `index_name` | str | float only | Nombre del indice (e.g. "EURIBOR_3M") |
| `spread` | float | No | Diferencial sobre indice (decimal) |
| `fixed_rate` | float | fixed only | Tipo fijo (decimal) |
| `repricing_freq` | str | No | Frecuencia repricing (e.g. "3M") |
| `payment_freq` | str | No | Frecuencia pago (e.g. "1M") |
| `annuity_payment_mode` | str | No | "reprice_on_reset" o "fixed_payment" |
| `next_reprice_date` | date | No | Proxima fecha de repricing |
| `floor_rate` | float | No | Suelo de tipo (decimal) |
| `cap_rate` | float | No | Techo de tipo (decimal) |

> (*) `maturity_date` es requerida en el template pero opcional en Unicaja para soportar non-maturity.

#### Columnas de metadata (anadidas por pipeline)

| Columna | Descripcion |
|---------|-------------|
| `source_spec` | Nombre del spec en SOURCE_SPECS |
| `source_file` | Path del fichero de origen |
| `source_sheet` | Sheet de Excel (o NA para CSV) |
| `source_bank` | Banco de origen |
| `source_contract_type` | Tipo de contrato |
| `source_row` | Fila original en el fichero |

#### Flujos scheduled (principal_flows)

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `contract_id` | str | Vinculo al contrato |
| `flow_type` | str | Tipo de flujo (e.g. "Principal") |
| `flow_date` | date | Fecha del flujo |
| `principal_amount` | float | Monto de amortizacion |
| `source_row` | int | Fila original |

---

### 10.2 Tipos de contrato soportados

El motor soporta **8 tipos de contrato** para calculo NII/EVE activo:

| Tipo | Rate | Amortizacion | Descripcion |
|------|------|-------------|-------------|
| `fixed_bullet` | Fijo | Bullet | Intereses periodicos, principal al vencimiento |
| `fixed_annuity` | Fijo | French | Cuota constante (interes + amortizacion) |
| `fixed_linear` | Fijo | Lineal | Amortizacion constante, intereses decrecientes |
| `fixed_scheduled` | Fijo | Explicita | Flujos de principal predeterminados |
| `variable_bullet` | Float | Bullet | Tipo variable con resets, principal al final |
| `variable_annuity` | Float | French | Cuota variable/fija segun modo, con resets |
| `variable_linear` | Float | Lineal | Amortizacion constante, tipo variable |
| `variable_scheduled` | Float | Explicita | Flujos explicitos con tipo variable |

Ademas existen 2 tipos que se cargan pero no se calculan actualmente:
- `fixed_non_maturity` — Productos sin vencimiento (cuentas corrientes, etc.)
- `variable_non_maturity` — Productos sin vencimiento con tipo variable

> **Non-maturity**: Requieren modelo behavioural (distribucion de plazos ficticios) que esta fuera del scope actual.

---

### 10.3 Convenciones de signo

```
Activo (A):  sign = +1   → NII positivo = ingreso para el banco
Pasivo (L):  sign = -1   → NII negativo = gasto para el banco

EVE = sum(signed PV de todos los flujos)

NII_total = sum(NII_activos) + sum(NII_pasivos)
          = ingresos_intereses - gastos_intereses
```

`notional` siempre es positivo en el esquema canonico. El signo se aplica al calcular NII/EVE.

---

## 11. Flujo de datos end-to-end

### 11.1 Pipeline EVE

```
                     ┌─────────────────┐
                     │  SOURCE_SPECS   │
                     │  (bank mapping) │
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │  CSV/Excel      │
                     │  (posiciones)   │
                     └────────┬────────┘
                              │
                    ┌─────────▼──────────┐
                    │ load_positions_    │
                    │ from_specs()       │
                    │ + load_scheduled_  │
                    │ from_specs()       │
                    └─────────┬──────────┘
                              │
              ┌───────────────▼───────────────┐
              │  Posiciones canonicas (DF)     │
              │  + Flujos scheduled (DF)       │
              └───────────────┬───────────────┘
                              │
            ┌─────────────────┼──────────────────┐
            │                 │                  │
   ┌────────▼────────┐  ┌────▼─────┐   ┌───────▼────────┐
   │ ForwardCurveSet │  │ Scenario │   │ build_regulatory│
   │ (base)          │  │ params   │   │ _curve_sets()   │
   └────────┬────────┘  └────┬─────┘   └───────┬────────┘
            │                │                  │
            └────────────────┼──────────────────┘
                             │
                    ┌────────▼────────┐
                    │ run_eve_        │
                    │ scenarios()     │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼────┐  ┌─────▼─────┐  ┌────▼──────┐
     │ EVE base    │  │ EVE por   │  │ Bucket    │
     │             │  │ escenario │  │ breakdown │
     └────────┬────┘  └─────┬─────┘  └────┬──────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────▼────────┐
                    │ EVEPipeline     │
                    │ Result          │
                    │ (+ charts/CSV)  │
                    └─────────────────┘
```

### 11.2 Pipeline NII

```
                     ┌─────────────────┐
                     │  Posiciones      │
                     │  canonicas       │
                     └────────┬────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
     ┌────────▼────┐  ┌──────▼──────┐  ┌────▼────────┐
     │ Curvas base │  │ Curvas      │  │ Calibrate   │
     │             │  │ estresadas  │  │ margin_set  │
     └────────┬────┘  └──────┬──────┘  └────┬────────┘
              │               │               │
              └───────────────┼───────────────┘
                              │
                    ┌─────────▼──────────┐
                    │ run_nii_12m_       │
                    │ scenarios()        │
                    │                    │
                    │ Para cada posicion:│
                    │  dispatch por      │
                    │  contract_type     │
                    │  al proyector      │
                    │  correspondiente   │
                    └─────────┬──────────┘
                              │
              ┌───────────────┼──────────────┐
              │               │              │
     ┌────────▼────┐  ┌──────▼──────┐  ┌───▼──────┐
     │ NII base    │  │ NII por     │  │ Monthly  │
     │ 12M         │  │ escenario   │  │ profile  │
     └────────┬────┘  └──────┬──────┘  └───┬──────┘
              │               │              │
              └───────────────┼──────────────┘
                              │
                    ┌─────────▼──────────┐
                    │ NIIPipeline        │
                    │ Result             │
                    │ (+ charts/CSV)     │
                    └────────────────────┘
```

---

## 12. Decisiones de diseno criticas

### 12.1 Composicion continua para curvas internas

El motor usa **composicion continua** internamente para todas las operaciones de curva:
```
DF(t) = exp(-r(t) * t)
r(t) = -ln(DF(t)) / t
```

Los rates de los contratos (fixed_rate, spread, floor_rate, cap_rate) se interpretan como tasas **simples** en base al `daycount_base` del contrato. La conversion se maneja implicitamente en los proyectores.

### 12.2 Floor/cap sobre tipo all-in

Los floors y caps se aplican sobre el **tipo all-in** (indice + spread), no sobre el indice aislado:

```python
all_in = forward_rate + spread
all_in = max(all_in, floor_rate)  # si hay floor
all_in = min(all_in, cap_rate)    # si hay cap
```

Esta decision refleja la realidad contractual: el contrato garantiza un tipo minimo/maximo total, no un floor sobre el indice.

### 12.3 Balance constante como default

El NII opera por defecto con `balance_constant = True`:
- Contratos que vencen se renuevan automaticamente
- Margenes se calibran del portfolio existente
- Es la convencion regulatoria IRRBB para NII

### 12.4 Basis preservation bajo stress

Para indices no risk-free (e.g. EURIBOR_3M que no es exactamente EUR_ESTR_OIS):

```
EURIBOR_3M_stressed(t) = ESTR_stressed(t) + (EURIBOR_3M_base(t) - ESTR_base(t))
```

Se preserva el spread (basis) sobre la curva risk-free. El regulador solo mide riesgo de tipos, no riesgo de basis.

### 12.5 Separacion motor / mapping

El motor nunca accede directamente a nombres de columnas bancarias. Todo pasa por el esquema canonico:

```
Fichero banco -> positions_reader (usa mapping) -> DataFrame canonico -> Motor
```

Esto permite adaptar a un nuevo banco creando solo un fichero `config/bank_mapping_<banco>.py`.

### 12.6 Modularidad por tipo de contrato

Cada tipo de contrato tiene su propio proyector NII y su propia logica de cashflows EVE. No hay un "super-proyector" generico. Esto es intencionado:
- Cada tipo tiene matices especificos (annuity vs linear vs bullet)
- Facilita testing individual
- Facilita extension futura sin riesgo de regresion

### 12.7 Extrapolacion flat forward

La curva extrapola con pendiente constante en ln(DF) mas alla del ultimo pilar. Esto produce un **forward rate instantaneo constante** en cola, que es la convencion mas conservadora. Alternativas (UFR, flat zero) requeririan implementacion explicita.

---

## 13. Limitaciones actuales y scope futuro

### Limitaciones del estado actual

| Limitacion | Impacto | Complejidad estimada |
|-----------|---------|---------------------|
| **Non-maturity deposits** no calculados | NII/EVE ignora cuentas corrientes/vista | Alta — requiere modelo behavioural |
| **Sin calendario habil** (business day adjustment) | Fechas de pago/reset pueden caer en festivos | Media — requiere calendario TARGET2 |
| **Sin multi-divisa** en NII/EVE | Solo opera en moneda unica (EUR implicitamente) | Media — requiere FX rate + curvas por divisa |
| **Sin convexity adjustment** | Futuros/swaps pueden necesitar ajuste | Baja — solo relevante para derivados |
| **Sin opcionalidades** (prepayment, behavioural) | No modela prepagos ni opciones implicitas | Alta — requiere modelo CPR/PSA |
| **EVE no incluye equity** | EVE = PV(assets) - PV(liabilities), sin capital propio | Baja — puede anadirse como pasivo negativo |
| **Graficos basicos** | Matplotlib suficiente para smoke tests, no para produccion | N/A — el front-back se encargara |

### Scope futuro planeado

1. **Modelo behavioural para non-maturity** — Distribucion de plazos ficticios para depositos a la vista (Phase 3 de integracion)
2. **Instant What-If** — Cache de contribuciones por contrato para edicion instantanea (Phase 2)
3. **Multi-divisa** — Soporte nativo para portfolios multi-currency
4. **Prepayment models** — CPR condicionales para hipotecas
5. **UFR extrapolation** — Convergencia a Ultimate Forward Rate para Solvencia II

---

## 14. Preparacion para integracion con front-back

### Contrato de integracion

El motor de calculo esta disenado para recibir:

1. **Posiciones**: DataFrame canonico con las columnas del esquema canonico (seccion 10.1)
2. **Curvas forward**: `ForwardCurveSet` (puede construirse desde Excel o directamente)
3. **Parametros de escenario**: Divisa, scenario_ids, risk_free_index
4. **Parametros de calculo**: balance_constant, annuity_payment_mode, etc.

Y devuelve:
- `EVEPipelineResult` o `NIIPipelineResult` con todos los resultados, tablas y paths de graficos

### Puntos de integracion natural

| Componente front-back | Punto de integracion motor | Notas |
|-----------------------|---------------------------|-------|
| Carga de datos (session upload) | `io/positions_pipeline` | El front-back puede pasar DataFrames directamente |
| Curvas de mercado | `services/market.ForwardCurveSet` | El front-back puede construir curvas desde API |
| Ejecucion de calculo | `services/eve_pipeline` / `nii_pipeline` | Funciones `run_*_from_specs()` |
| Resultados para UI | `EVEPipelineResult` / `NIIPipelineResult` | Contienen DataFrames listos para serializar |
| What-If | Motor NII/EVE a nivel contrato | Requiere refactor para cache por contrato |

### Prerequisitos para integracion

1. **Definir formato de intercambio**: El front-back debe enviar posiciones como DataFrame canonico (no como ficheros crudos del banco).
2. **Desacoplar IO de fichero**: El motor puede recibir DataFrames directamente via `read_positions_dataframe()`, sin pasar por ficheros CSV/Excel.
3. **API sincrona vs asincrona**: El motor actual es sincrono. Para ejecucion interactiva (what-if), puede necesitarse wrapping asincrono.
4. **Serialización de resultados**: `EVEPipelineResult` y `NIIPipelineResult` contienen DataFrames y Paths. Para la API, habra que serializar a JSON/dict.

### Estrategia de cache para What-If

El motor actual calcula NII/EVE sobre todo el portfolio. Para what-if instantaneo:

1. **Phase 1**: Ejecutar motor completo por session (correctness first)
2. **Phase 2**: Cachear contribucion NII/EVE por contrato. Para "quitar contrato X": restar su contribucion. Para "anadir contrato Y": mini-run sobre Y y sumar.
3. **Phase 3**: Modelo behavioural para non-maturity integrado.

La arquitectura actual es **compatible** con esta estrategia: los proyectores NII ya operan contrato-por-contrato, y `build_eve_cashflows` genera flujos por contrato individual.

---

> **Fin del documento.**
> Generado el 17 de febrero de 2026 como analisis tecnico exhaustivo del Motor de Calculo ALMReady para preparar la integracion con el sistema front-back.
