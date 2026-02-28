# What-If Workbench Integration Plan

> **Status:** Draft
> **Created:** 2026-02-28
> **Branch strategy:** Cherry-pick `origin/What-If` onto `main`
> **Divergence point:** `937445f` (Modularize balance parser)

---

## Table of Contents

1. [Situation Overview](#1-situation-overview)
2. [Architecture Inventory](#2-architecture-inventory)
3. [Phase 1 — Backend Port (Engine Layer)](#3-phase-1--backend-port-engine-layer)
4. [Phase 2 — Backend Port (API Layer)](#4-phase-2--backend-port-api-layer)
5. [Phase 3 — Frontend Types & API Client](#5-phase-3--frontend-types--api-client)
6. [Phase 4 — Frontend Components Port](#6-phase-4--frontend-components-port)
7. [Phase 5 — WhatIfContext Upgrade & Wiring](#7-phase-5--whatifcontext-upgrade--wiring)
8. [Phase 6 — Results Display (Base vs What-If Comparison)](#8-phase-6--results-display-base-vs-what-if-comparison)
9. [Phase 7 — Charts (Per-Tenor & Per-Month Overlays)](#9-phase-7--charts-per-tenor--per-month-overlays)
10. [Phase 8 — Behavioural Compartment ↔ BehaviouralContext Bridge](#10-phase-8--behavioural-compartment--behaviouralcontext-bridge)
11. [Phase 9 — Integration Testing & Validation](#11-phase-9--integration-testing--validation)
12. [Deferred Work](#12-deferred-work)
13. [Risk Register](#13-risk-register)
14. [File Inventory (What Gets Created / Modified)](#14-file-inventory)

---

## 1. Situation Overview

### What happened

Two branches diverged from commit `937445f`:

- **`main`** (10 commits): Pipeline optimizations (240s→67s), Tauri desktop packaging,
  bank adapter refactoring (`app/bank_adapters/` → `engine/banks/`), balance schema
  expansion (8 asset + 6 liability subcategories with hierarchical groups),
  DataFrame-based queries, Excel export, behavioural assumptions Phase 0-1.

- **`origin/What-If`** (3 commits): Full What-If Workbench with 4 compartments
  (Buy/Sell, Find Limit, Behavioural, Pricing), a loan decomposer engine,
  binary-search solver, 16-product catalog with progressive-reveal forms.

### What we're doing

Cherry-picking the What-If branch's logic onto main's architecture. Main has the
right foundation (engine layer separation, vectorized queries, Tauri). The What-If
code is 90% additive (new files) with only 5 files overlapping, and those overlaps
are in different sections.

### Scope boundaries

| In scope | Out of scope (deferred) |
|---|---|
| Port all What-If frontend components to main | Exotic cashflow variability (irregular schedules, callable bonds) |
| Port decomposer + find-limit to `engine/services/whatif/` | Additional visual representations of individual edits |
| Connect frontend → backend for what-if EVE/NII calculation | Multi-currency what-if support |
| Display base vs what-if comparison in ResultsCard | Scheduled amortization uploads |
| Per-tenor EVE overlay + per-month NII overlay on charts | IRS swap decomposition |
| Bridge BehaviouralCompartment ↔ main's BehaviouralContext | Persistent what-if scenarios (save/load) |
| V1 endpoint (existing) serves all calculate requests | V2 decomposer endpoint (build but wire later) |

### Key design decisions

1. **Base calculation untouched.** The existing `POST /api/sessions/{id}/calculate`
   endpoint and its results pipeline are not modified.

2. **What-If calculation uses V1 endpoint** (`POST /api/sessions/{id}/calculate/whatif`).
   The existing engine on main already computes standalone EVE/NII on synthetic
   positions. We enrich the request payload with the new fields (amortization,
   floor/cap, grace, mixed rates) and let the existing `create_synthetic_motor_row()`
   handle them. Where the engine can't handle a feature yet (e.g., grace periods,
   mixed rates), we decompose on the frontend into multiple simpler modifications
   or document the gap.

3. **Decomposer is ported but not wired as the primary path.** We copy
   `decomposer.py` and `find_limit.py` into `engine/services/whatif/` and build
   the V2 router endpoints, but the main "Apply to Analysis" flow continues to
   use V1. The decomposer serves `find-limit` (which needs it) and is available
   for future V2 migration.

4. **Results comparison = deltas overlaid on base.** The backend returns
   `eve_bucket_deltas[]` and `nii_month_deltas[]` per scenario. The frontend
   overlays these on the base case charts and shows a 3-column summary table
   (Baseline | What-If Impact | Post What-If).

5. **Behavioural compartment reads/writes main's BehaviouralContext.** No duplicate
   state. The workbench compartment is a UI surface for the same context the
   standalone modal uses.

---

## 2. Architecture Inventory

### Motor row schema (what the engine needs)

Every position fed to EVE/NII must be a dict/DataFrame row with:

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| `contract_id` | str | Always | Unique identifier |
| `side` | str | Always | "A" (asset) or "L" (liability) |
| `source_contract_type` | str | Always | One of 8 types (see below) |
| `notional` | float | Always | Absolute value; sign from side |
| `start_date` | date | Always | Contract inception |
| `maturity_date` | date | Always* | *Except NMDs |
| `fixed_rate` | float | Fixed types | Decimal (0.035 = 3.5%) |
| `spread` | float | Variable types | Decimal (0.015 = 150bps) |
| `index_name` | str | Variable types | Must match curve_set key |
| `next_reprice_date` | date | Variable types | Anchor for first reset |
| `daycount_base` | str | Always | "ACT/360", "30/360", etc. |
| `payment_freq` | str | Recommended | "1M", "3M", "6M", "12M" |
| `repricing_freq` | str | Variable types | Reset frequency |
| `currency` | str | Always | "EUR" |
| `floor_rate` | float | Optional | Interest rate floor |
| `cap_rate` | float | Optional | Interest rate cap |

### 8 motor-executable contract types

| Type | Rate | Amortization |
|------|------|-------------|
| `fixed_bullet` | Fixed | None (principal at maturity) |
| `fixed_annuity` | Fixed | Equal periodic payments |
| `fixed_linear` | Fixed | Linear principal amortization |
| `fixed_scheduled` | Fixed | Bank-provided schedule |
| `variable_bullet` | Floating | None |
| `variable_annuity` | Floating | Equal periodic payments |
| `variable_linear` | Floating | Linear amortization |
| `variable_scheduled` | Floating | Bank-provided schedule |

### Current endpoints (main)

| Endpoint | Purpose | Status |
|----------|---------|--------|
| `POST /api/sessions/{id}/calculate` | Base EVE/NII calculation | Working |
| `POST /api/sessions/{id}/calculate/whatif` | What-if EVE/NII deltas (V1) | Working |
| `GET /api/sessions/{id}/balance/contracts` | Search/filter contracts | Working |

### New endpoints (from What-If branch, to be ported)

| Endpoint | Purpose | Status |
|----------|---------|--------|
| `POST /api/sessions/{id}/whatif/decompose` | Preview decomposed positions | To port |
| `POST /api/sessions/{id}/whatif/calculate` | V2 what-if with decomposer | To port |
| `POST /api/sessions/{id}/whatif/find-limit` | Binary search solver | To port |

---

## 3. Phase 1 — Backend Port (Engine Layer)

### Goal
Copy decomposer and find-limit from the What-If branch into main's `engine/services/whatif/` package, adapting to main's import conventions.

### 3.1 Create `backend/engine/services/whatif/` package

**Source:** `git show origin/What-If:backend/almready/services/whatif/`

**Target:** `backend/engine/services/whatif/`

Files to create:

#### `backend/engine/services/whatif/__init__.py`
```python
"""What-If analysis services.

This package contains the business logic for the What-If workbench:
- decomposer: Converts high-level instrument specs into motor positions
- find_limit: Binary search solver for EVE/NII constraints
"""
from .decomposer import LoanSpec, decompose_loan  # noqa: F401
```

#### `backend/engine/services/whatif/decomposer.py`

Copy from `git show origin/What-If:backend/almready/services/whatif/decomposer.py`.

No import changes needed — this module only imports from `dataclasses`, `datetime`,
`typing`, and `pandas`. It has zero project-internal imports.

**Key classes/functions:**
- `LoanSpec` dataclass — high-level instrument description
- `decompose_loan(spec: LoanSpec) -> pd.DataFrame` — returns 1-5 motor rows
- `_motor_row()` — builds a single motor-compatible dict
- `_resolve_dates()` — derives start/grace_end/maturity from spec
- `_decompose_simple()` — fixed/variable without mixed rate
- `_decompose_mixed()` — mixed-rate decomposition (fixed then variable)

**Decomposition matrix:**

| Rate | Amortization | Grace | Positions |
|------|-------------|-------|-----------|
| Fixed/Variable | Bullet | Any | 1 |
| Fixed/Variable | Linear/Annuity | No | 1 |
| Fixed/Variable | Linear/Annuity | Yes | 3 (grace bullet + amort + offset) |
| Mixed | Bullet | No | 3 (fixed bullet + var bullet + offset) |
| Mixed | Linear/Annuity | Yes | 5 (grace + amort + cancel + var + offset) |

#### `backend/engine/services/whatif/find_limit.py`

Copy from `git show origin/What-If:backend/almready/services/whatif/find_limit.py`.

**Import changes required:**
- Replace: `from almready.services.whatif.decomposer import ...`
- With: `from engine.services.whatif.decomposer import ...`

**Key classes/functions:**
- `FindLimitResult` dataclass — solver output
- `find_limit()` — entry point, dispatches to linear or binary search
- `solve_notional_linear()` — O(1) for notional (linear scaling)
- `solve_binary_search()` — O(~15 iterations) for rate/maturity/spread
- `_evaluate_metric()` — decompose → compute EVE or NII for one parameter value
- `_mutate_spec()` — clone LoanSpec with one field changed

**Solver bounds:**

| Solve-for | Lower | Upper | Tolerance |
|-----------|-------|-------|-----------|
| Notional | 0 | (linear) | 1000.0 |
| Rate | 0.0 | 0.20 (20%) | 1000.0 |
| Maturity | 0.25 years | 50 years | 1000.0 |
| Spread | 0.0 | 0.10 (1000bps) | 1000.0 |

### 3.2 Verify existing `backend/engine/services/whatif.py` (V1)

Main already has this file with 3 functions:
- `create_synthetic_motor_row()` — builds a single motor row from a modification
- `build_whatif_delta_dataframe()` — processes adds + removals into DataFrames
- `unified_whatif_map()` — computes EVE/NII across scenarios

**No changes needed** to this file. The V1 path continues to work.

### 3.3 Verification

```bash
cd backend && .venv/bin/python -c "from engine.services.whatif.decomposer import LoanSpec, decompose_loan; print('OK')"
cd backend && .venv/bin/python -c "from engine.services.whatif.find_limit import find_limit, FindLimitResult; print('OK')"
```

All 186 existing tests must still pass.

---

## 4. Phase 2 — Backend Port (API Layer)

### Goal
Port the What-If router endpoints (decompose, V2 calculate, find-limit) and add
the new Pydantic schemas.

### 4.1 Add schemas to `backend/app/schemas.py`

Append (do NOT modify existing schemas) the following Pydantic models:

```python
# ── What-If V2 (Decomposer) ──────────────────────────────────

class LoanSpecItem(BaseModel):
    """Rich loan spec sent from frontend — maps to decomposer.LoanSpec."""
    id: str
    notional: float
    term_years: float
    side: str = "A"
    currency: str = "EUR"
    rate_type: str = "fixed"
    fixed_rate: float | None = None
    variable_index: str | None = None
    spread_bps: float = 0.0
    mixed_fixed_years: float | None = None
    amortization: str = "bullet"
    grace_years: float = 0.0
    daycount: str = "30/360"
    payment_freq: str = "12M"
    repricing_freq: str | None = None
    start_date: str | None = None
    floor_rate: float | None = None
    cap_rate: float | None = None
    label: str = ""

class DecomposedPosition(BaseModel):
    """Single motor position from decomposer."""
    contract_id: str
    side: str
    source_contract_type: str
    notional: float
    fixed_rate: float
    spread: float
    start_date: str
    maturity_date: str
    index_name: str | None = None
    next_reprice_date: str | None = None
    daycount_base: str
    payment_freq: str
    repricing_freq: str | None = None
    currency: str
    floor_rate: float | None = None
    cap_rate: float | None = None
    rate_type: str

class DecomposeResponse(BaseModel):
    session_id: str
    positions: list[DecomposedPosition]
    position_count: int

class WhatIfV2CalculateRequest(BaseModel):
    additions: list[LoanSpecItem] = Field(default_factory=list)
    removals: list[WhatIfModificationItem] = Field(default_factory=list)

class FindLimitRequest(BaseModel):
    product_spec: LoanSpecItem
    target_metric: str          # "eve" | "nii"
    target_scenario: str        # "base" | "worst" | scenario name
    limit_value: float          # absolute target
    solve_for: str              # "notional" | "rate" | "maturity" | "spread"

class FindLimitResponse(BaseModel):
    session_id: str
    found_value: float
    achieved_metric: float
    target_metric: str
    target_scenario: str
    solve_for: str
    converged: bool
    iterations: int
    tolerance: float
    product_spec: LoanSpecItem
```

### 4.2 Create `backend/app/routers/whatif.py`

Copy from `git show origin/What-If:backend/app/routers/whatif.py`.

**Import changes required:**

| What-If branch import | Main replacement |
|---|---|
| `from almready.services.whatif.decomposer import LoanSpec, decompose_loan` | `from engine.services.whatif.decomposer import LoanSpec, decompose_loan` |
| `from almready.services.whatif.find_limit import find_limit, FindLimitResult` | `from engine.services.whatif.find_limit import find_limit, FindLimitResult` |

**Bank config injection:** The router must import bank-specific mappings from
`engine.banks.unicaja.whatif` (main's location) instead of hardcoding them.

**Three endpoints:**

1. **`POST /api/sessions/{sid}/whatif/decompose`**
   - Receives `LoanSpecItem`, converts to `LoanSpec`, calls `decompose_loan()`
   - Returns `DecomposeResponse` with list of motor positions
   - Purpose: Preview what the decomposer will create (UX validation)

2. **`POST /api/sessions/{sid}/whatif/calculate`**
   - Receives `WhatIfV2CalculateRequest` with `additions[]` and `removals[]`
   - Decomposes additions via decomposer → motor positions
   - Loads existing positions, filters removals
   - Computes EVE/NII deltas per scenario
   - Returns same `WhatIfResultsResponse` shape as V1
   - **Note:** Not wired as primary path yet — serves find-limit internally

3. **`POST /api/sessions/{sid}/whatif/find-limit`**
   - Receives `FindLimitRequest` (product spec + constraint + solve-for)
   - Loads base calculation params (curves, scenarios)
   - Dispatches to linear solver (notional) or binary search (rate/maturity/spread)
   - Returns `FindLimitResponse` with solved value

### 4.3 Register router in `backend/app/main.py`

Add one import and one `include_router` call:

```python
from app.routers import whatif
app.include_router(whatif.router)
```

This line goes alongside the existing `balance`, `calculate`, etc. router registrations.

### 4.4 Verification

```bash
# Import check
cd backend && .venv/bin/python -c "from app.routers.whatif import router; print('Router registered:', len(router.routes), 'routes')"

# All tests pass
cd backend && .venv/bin/python -m pytest engine/tests/ -v
```

---

## 5. Phase 3 — Frontend Types & API Client

### Goal
Expand `src/types/whatif.ts` and `src/lib/api.ts` with the new types and API
functions needed by the workbench components.

### 5.1 Expand `src/types/whatif.ts`

Add the following types (append, don't modify existing):

```typescript
// ── Rate & Amortization enums ──────────────────────────────
export type RateType = 'fixed' | 'variable' | 'mixed';
export type AmortizationType = 'bullet' | 'linear' | 'annuity' | 'scheduled';
export type Side = 'A' | 'L';

// ── Decomposer types ──────────────────────────────────────
export interface LoanSpec {
  id: string;
  notional: number;
  termYears: number;
  side?: Side;
  currency?: string;
  rateType: RateType;
  fixedRate?: number;
  variableIndex?: string;
  spreadBps?: number;
  mixedFixedYears?: number;
  amortization: AmortizationType;
  graceYears?: number;
  daycount?: string;
  paymentFreq?: string;
  repricingFreq?: string;
  startDate?: string;
  floorRate?: number;
  capRate?: number;
  label?: string;
}

export interface DecomposedPosition {
  contractId: string;
  side: string;
  sourceContractType: string;
  notional: number;
  fixedRate: number;
  spread: number;
  startDate: string;
  maturityDate: string;
  indexName?: string;
  nextRepriceDate?: string;
  daycountBase: string;
  paymentFreq: string;
  repricingFreq?: string;
  currency: string;
  floorRate?: number;
  capRate?: number;
  rateType: string;
}

// ── Find Limit types ──────────────────────────────────────
export type FindLimitMetric = 'eve' | 'nii';
export type FindLimitSolveFor = 'notional' | 'rate' | 'maturity' | 'spread';

export interface FindLimitRequest {
  product_spec: LoanSpec;
  target_metric: FindLimitMetric;
  target_scenario: string;
  limit_value: number;
  solve_for: FindLimitSolveFor;
}

export interface FindLimitResponse {
  session_id: string;
  found_value: number;
  achieved_metric: number;
  target_metric: string;
  target_scenario: string;
  solve_for: string;
  converged: boolean;
  iterations: number;
  tolerance: number;
  product_spec: LoanSpec;
}

// ── Behavioural override (for What-If compartment) ────────
export interface BehaviouralOverride {
  family: 'nmd' | 'loan-prepayments' | 'term-deposits';
  coreProportion?: number;
  coreAverageMaturity?: number;
  passThrough?: number;
  smm?: number;
  tdrr?: number;
}

// ── Repricing override (for What-If compartment) ──────────
export interface RepricingOverride {
  subcategoryId: string;
  side: 'asset' | 'liability';
  productLabel: string;
  currentVolume: number;
  currentAvgRate: number;
  currentAnnualInterest: number;
  scope: 'entire' | 'new-production';
  newProductionPct?: number;
  affectedVolume: number;
  rateMode: 'absolute' | 'delta';
  newRate: number;
  deltaBps: number;
  newAnnualInterest: number;
  deltaInterest: number;
  deltaNii: number;
  deltaNimBps: number;
}
```

**Expand existing `WhatIfModification` interface** to support the 4 modification types:

```typescript
// Add these fields to the existing WhatIfModification:
type: 'add' | 'remove' | 'behavioural' | 'pricing';  // was: 'add' | 'remove'

// New optional fields:
productTemplateId?: string;
amortization?: AmortizationType;
grace_years?: number;
floorRate?: number;
capRate?: number;
mixedFixedYears?: number;
formValues?: Record<string, string>;
behaviouralOverride?: BehaviouralOverride;
repricingOverride?: RepricingOverride;
```

### 5.2 Expand `src/lib/api.ts`

Add these API functions (append after existing `calculateWhatIf()`):

```typescript
// ── V2 Decompose ──────────────────────────────────────────
export async function decomposePosition(
  sessionId: string,
  spec: LoanSpecItem,
): Promise<DecomposeResponse> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/whatif/decompose`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(spec),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── Find Limit ────────────────────────────────────────────
export async function findLimit(
  sessionId: string,
  request: FindLimitRequestBody,
): Promise<FindLimitResponseBody> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/whatif/find-limit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

Add the matching type aliases for request/response bodies.

The existing `calculateWhatIf()` function is NOT modified — it continues to use
the V1 endpoint.

---

## 6. Phase 4 — Frontend Components Port

### Goal
Copy all new What-If components from the What-If branch into main. These are
100% new files with zero conflicts.

### 6.1 New files to copy (verbatim from What-If branch)

| Source (What-If branch) | Target (main) | Lines | Purpose |
|---|---|---|---|
| `src/components/whatif/WhatIfWorkbench.tsx` | Same path | ~319 | Main modal — 4-tab workbench container |
| `src/components/whatif/BuySellCompartment.tsx` | Same path | ~874 | Add/Remove positions (left: remove accordion, right: product form) |
| `src/components/whatif/FindLimitCompartment.tsx` | Same path | ~588 | Binary search solver UI |
| `src/components/whatif/BehaviouralCompartment.tsx` | Same path | ~662 | NMD/prepayment/TDRR overrides |
| `src/components/whatif/PricingCompartment.tsx` | Same path | ~1096 | Repricing simulation |
| `src/components/whatif/CompartmentPlaceholder.tsx` | Same path | ~30 | Empty state placeholder |
| `src/components/whatif/shared/ProductConfigForm.tsx` | Same path | ~1010 | Shared product form engine (progressive reveal) |
| `src/components/whatif/shared/constants.ts` | Same path | ~197 | Product catalog, template→subcategory maps, helpers |

**Total: ~4,776 new lines across 8 files.**

### 6.2 Copy method

```bash
for f in \
  src/components/whatif/WhatIfWorkbench.tsx \
  src/components/whatif/BuySellCompartment.tsx \
  src/components/whatif/FindLimitCompartment.tsx \
  src/components/whatif/BehaviouralCompartment.tsx \
  src/components/whatif/PricingCompartment.tsx \
  src/components/whatif/CompartmentPlaceholder.tsx \
  src/components/whatif/shared/ProductConfigForm.tsx \
  src/components/whatif/shared/constants.ts; do
  mkdir -p "$(dirname "$f")"
  git show origin/What-If:"$f" > "$f"
done
```

### 6.3 Import path adjustments needed in copied files

These components import from `@/types/whatif`, `@/lib/api`, `@/components/ui/*` —
all of which exist on main. The key imports to verify:

| Import | Exists on main? | Action |
|--------|----------------|--------|
| `@/types/whatif` | Yes (expanded in Phase 3) | No change |
| `@/lib/api` | Yes (expanded in Phase 3) | No change |
| `@/components/ui/dialog` | Yes (shadcn) | No change |
| `@/components/ui/tabs` | Yes (shadcn) | No change |
| `@/components/ui/select` | Yes (shadcn) | No change |
| `@/components/ui/input` | Yes (shadcn) | No change |
| `@/components/ui/button` | Yes (shadcn) | No change |
| `@/components/ui/badge` | Yes (shadcn) | No change |
| `@/components/ui/accordion` | Verify exists | Install if missing |
| `@/components/whatif/shared/constants` | Created in 6.1 | No change |
| `@/components/whatif/shared/ProductConfigForm` | Created in 6.1 | No change |

### 6.4 CSS additions

The What-If branch adds ~36 lines of custom CSS to `src/index.css` for the
workbench layout (compartment grid, scroll behavior, badge positioning). These
must be appended to main's `src/index.css`.

Extract via: `git diff 937445f..origin/What-If -- src/index.css`

---

## 7. Phase 5 — WhatIfContext Upgrade & Wiring

### Goal
Expand `WhatIfContext` to support the 4 modification types and per-type badge
counts. Replace the old `WhatIfBuilder` side-sheet with the new `WhatIfWorkbench`
modal.

### 7.1 WhatIfContext changes

**Current state (main):**
```typescript
modifications: WhatIfModification[]     // type: 'add' | 'remove' only
isApplied: boolean
applyCounter: number
analysisDate: Date | null
cet1Capital: number
```

**Target state:**
```typescript
modifications: WhatIfModification[]     // type: 'add' | 'remove' | 'behavioural' | 'pricing'
isApplied: boolean
applyCounter: number
analysisDate: Date | null
cet1Capital: number

// New computed counts
addCount: number           // modifications.filter(m => m.type === 'add').length
removeCount: number        // modifications.filter(m => m.type === 'remove').length
behaviouralCount: number   // modifications.filter(m => m.type === 'behavioural').length
pricingCount: number       // modifications.filter(m => m.type === 'pricing').length
```

**Apply the diff from What-If branch:**
```bash
git diff 937445f..origin/What-If -- src/components/whatif/WhatIfContext.tsx
```

Key changes:
- Add `addCount`, `removeCount`, `behaviouralCount`, `pricingCount` to context value
- Compute them via `useMemo` filtering on `modifications`
- Add `setAnalysisDate()` and `setCet1Capital()` methods to context

### 7.2 Replace WhatIfBuilder with WhatIfWorkbench

**Current flow (main):**
```
BalancePositionsCard → "What-If" button → opens WhatIfBuilder (Sheet side-panel)
  ├─ WhatIfAddTab (simple form)
  └─ WhatIfRemoveTab (search + tree browse)
```

**Target flow:**
```
BalancePositionsCard → "What-If" button → opens WhatIfWorkbench (Dialog modal)
  ├─ BuySellCompartment (rich product catalog + remove accordion)
  ├─ FindLimitCompartment (binary search UI)
  ├─ BehaviouralCompartment (NMD/prepayment/TDRR)
  └─ PricingCompartment (repricing simulation)
```

**In `BalancePositionsCard.tsx`:**
1. Replace `<WhatIfBuilder>` import with `<WhatIfWorkbench>`
2. Pass the required props:
   - `sessionId` — from balance load context
   - `balanceTree` — the hierarchical tree for remove accordion + pricing snapshot
   - `scenarios` — interest rate scenarios (passed down from Index.tsx)
   - `open` / `onOpenChange` — dialog state

**The old `WhatIfBuilder.tsx`, `WhatIfAddTab.tsx`, `WhatIfRemoveTab.tsx` are NOT
deleted** — they become dead code. We can remove them in a follow-up cleanup
commit once the workbench is confirmed working.

### 7.3 Wire up WhatIfWorkbench in Index.tsx

`Index.tsx` must pass `scenarios` to `BalancePositionsCard` so the workbench can
display scenario names in the Find Limit compartment. Currently `scenarios` lives
in Index state — thread it down as a prop.

---

## 8. Phase 6 — Results Display (Base vs What-If Comparison)

### Goal
When the user clicks "Apply to Analysis" in the workbench, ResultsCard sends the
modifications to the V1 backend, receives deltas, and displays a 3-column
comparison table.

### 8.1 Current ResultsCard flow (already working on main)

```
applyCounter increments
  → ResultsCard useEffect fires
  → Builds WhatIfModificationRequest[] from modifications
  → POST /api/sessions/{id}/calculate/whatif
  → Receives WhatIfResultsResponse:
      base_eve_delta, worst_eve_delta, base_nii_delta, worst_nii_delta
      scenario_eve_deltas: { [name]: number }
      scenario_nii_deltas: { [name]: number }
      eve_bucket_deltas: Array<{ scenario, bucket_name, asset_pv_delta, liability_pv_delta }>
      nii_month_deltas: Array<{ scenario, month_index, month_label, income_delta, expense_delta }>
```

### 8.2 What needs to change

**Request payload enrichment:**

The current `WhatIfModificationRequest` on main sends these fields for `type='add'`:
```typescript
{
  id, type, label, notional, currency, category, subcategory,
  rate, maturity, productTemplateId, startDate, maturityDate,
  paymentFreq, repricingFreq, refIndex, spread
}
```

We need to also include:
```typescript
{
  amortization,    // 'bullet' | 'linear' | 'annuity'
  floorRate,       // decimal (0.001 = 10bps)
  capRate,         // decimal
  grace_years,     // years (0 if none)
  mixedFixedYears, // years (null if not mixed)
}
```

These additional fields must be:
1. Added to the `WhatIfModificationItem` Pydantic model in `schemas.py`
2. Handled in `create_synthetic_motor_row()` in `engine/services/whatif.py`

**For `amortization`:** The V1 `create_synthetic_motor_row()` already maps
`productTemplateId` → `source_contract_type` which encodes amortization
(e.g., `fixed-loan` → `fixed_annuity`). But the What-If workbench lets users
pick amortization independently (bullet/linear/annuity for the same template).
We need to update the mapping logic to:
```python
# If explicit amortization provided, override the template default
if mod.amortization:
    base_type = template_motor_type.split('_')[0]  # 'fixed' or 'variable'
    source_contract_type = f"{base_type}_{mod.amortization}"
```

**For `floorRate` / `capRate`:** Already supported in the motor schema. Just pass
them through:
```python
row["floor_rate"] = mod.floorRate if mod.floorRate else None
row["cap_rate"] = mod.capRate if mod.capRate else None
```

**For `grace_years` and `mixedFixedYears`:** These CANNOT be handled by V1's
single-row approach. For now, we:
1. **Ignore grace_years** in V1 — the position starts at start_date, amortization
   begins immediately. This is an approximation.
2. **Ignore mixedFixedYears** in V1 — treat as fixed-rate for the full term.
   This is an approximation.
3. **Document** that V2 (with decomposer) will handle these correctly. The
   frontend can show a small info tooltip: "Grace period and mixed rates require
   V2 engine (coming soon)".

### 8.3 Summary table display

**3-column layout (already exists on main, may need polish):**

```
┌──────────────┬────────────┬──────────────┬──────────────┐
│              │  Baseline  │  What-If Δ   │  Post What-If│
├──────────────┼────────────┼──────────────┼──────────────┤
│ Base EVE     │  €123.4M   │  -€2.1M      │  €121.3M     │
│ Base NII     │   €45.6M   │  +€0.8M      │  €46.4M      │
│ Worst EVE    │  €110.2M   │  -€5.3M      │  €104.9M     │
│ Worst NII    │   €42.1M   │  +€0.3M      │  €42.4M      │
│ ΔEVE %CET1   │  -10.2%    │  -1.6%       │  -11.8%      │
│ ΔNII %CET1   │   -2.7%    │  +0.2%       │   -2.5%      │
├──────────────┼────────────┼──────────────┼──────────────┤
│ Scenario ▼   │ (dropdown to select specific scenario)   │
│ Scenario EVE │  €115.8M   │  -€3.7M      │  €112.1M     │
│ Scenario NII │   €43.2M   │  +€0.5M      │  €43.7M      │
└──────────────┴────────────┴──────────────┴──────────────┘
```

**Scenario selector:** Dropdown to pick which scenario's per-bucket/per-month
data is displayed on the charts.

### 8.4 Handling `behavioural` and `pricing` modification types

The V1 backend endpoint currently only handles `type: 'add'` and `type: 'remove'`.
When the user has behavioural or pricing modifications, ResultsCard needs to:

1. **Filter modifications** before sending to V1: only send `add` and `remove` types
2. **For `behavioural` modifications:** These override the BehaviouralContext values.
   The base `/calculate` endpoint already accepts behavioural params (CPR, TDRR,
   NMD core%). The what-if endpoint should accept them too. **Add optional
   behavioural params to the V1 request:**
   ```python
   class WhatIfCalculateRequest(BaseModel):
       modifications: list[WhatIfModificationItem]
       # NEW: Optional behavioural overrides
       nmd_core_proportion: float | None = None
       nmd_core_avg_maturity: float | None = None
       nmd_pass_through: float | None = None
       loan_smm: float | None = None
       term_deposit_tdrr: float | None = None
   ```
3. **For `pricing` modifications:** These are pure frontend calculations (delta
   NII = delta_rate × volume × yearfrac). No backend call needed. ResultsCard
   can compute the NII impact locally and add it to the backend's deltas.
   *Alternatively*, defer pricing to V2.

---

## 9. Phase 7 — Charts (Per-Tenor & Per-Month Overlays)

### Goal
Overlay what-if deltas on the base case EVE and NII charts, showing both the
original profile and the post-what-if profile.

### 9.1 EVE Chart — Per-Tenor Bucket Overlay

**Data source:** `eve_bucket_deltas[]` from `WhatIfResultsResponse`

Each bucket delta has:
```typescript
{
  scenario: string,
  bucket_name: string,       // "0-1Y", "1-2Y", ..., "20+"
  asset_pv_delta: number,    // Change in asset present value
  liability_pv_delta: number // Change in liability present value
}
```

**Chart visualization (stacked bar with overlay):**

```
EVE by Tenor (Base scenario)

  PV (€M)
  │
  │  ████  ████                    ← Base case (solid)
  │  ████  ████  ████
  │  ████  ████  ████  ████       ← What-If delta (hatched/transparent overlay)
  │  ████  ████  ████  ████  ████
  ├──────┬──────┬──────┬──────┬──
  │ 0-1Y │ 1-2Y │ 2-3Y │ 3-5Y │ ...
```

**Implementation:**
1. Base EVE buckets come from the base `/calculate` response (already stored)
2. What-If bucket deltas come from `/calculate/whatif` response
3. Chart renders two series per bucket:
   - **Base:** Original asset/liability PV (solid bars)
   - **Post What-If:** Base + delta (outlined bars or second color)
4. Net delta line on secondary axis (optional)

**Filter by scenario:** Chart shows data for the currently selected scenario
(from the dropdown in the summary table).

### 9.2 NII Chart — Per-Month Overlay

**Data source:** `nii_month_deltas[]` from `WhatIfResultsResponse`

Each month delta has:
```typescript
{
  scenario: string,
  month_index: number,       // 0-11
  month_label: string,       // "Mar 2026", "Apr 2026", ...
  income_delta: number,      // Change in interest income (assets)
  expense_delta: number      // Change in interest expense (liabilities)
}
```

**Chart visualization (line chart with area fill):**

```
NII Monthly (Base scenario)

  NII (€M)
  │
  │  ────────────────────── Base NII (solid line)
  │     ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ Post What-If NII (dashed line)
  │  ░░░░░░░░░░░░░░░░░░░░░ Delta area (shaded between lines)
  │
  ├──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──
  │ M1│ M2│ M3│ M4│ M5│ M6│ M7│ M8│ M9│M10│M11│M12│
```

**Implementation:**
1. Base NII monthly comes from the base `/calculate` response
2. What-If month deltas from `/calculate/whatif` response
3. Chart renders:
   - **Base:** Original monthly NII (solid line)
   - **Post What-If:** Base + delta (dashed line)
   - **Delta area:** Shaded between the two lines (green for positive, red for negative)

### 9.3 Chart component changes

The existing chart components on main (likely in `ResultsCard.tsx` or separate
chart files) need to accept optional `whatIfDeltas` props:

```typescript
interface EVEChartProps {
  baseBuckets: EVEBucket[];
  whatIfBucketDeltas?: WhatIfBucketDelta[];  // NEW
  selectedScenario: string;                   // NEW
}

interface NIIChartProps {
  baseMonthly: NIIMonthly[];
  whatIfMonthDeltas?: WhatIfMonthDelta[];     // NEW
  selectedScenario: string;                    // NEW
}
```

When `whatIfBucketDeltas` / `whatIfMonthDeltas` are provided, the chart adds
the overlay series. When absent (no what-if applied), it renders base-only.

---

## 10. Phase 8 — Behavioural Compartment ↔ BehaviouralContext Bridge

### Goal
The What-If branch has a `BehaviouralCompartment` that lets users override
NMD/prepayment/TDRR assumptions inside the workbench. Main already has a
standalone `BehaviouralContext` + `BehaviouralAssumptionsModal`. Bridge them.

### 10.1 Architecture: Single context, two UI surfaces

```
BehaviouralContext (single source of truth)
  ├─ BehaviouralAssumptionsModal (standalone, from main Phase 0-1)
  │   → Quick access from BalancePositionsCard header
  │   → Sets NMD/prepayment/TDRR values
  │
  └─ BehaviouralCompartment (inside WhatIfWorkbench)
      → Same values, different UI (inline in workbench)
      → Reads from BehaviouralContext
      → Writes to BehaviouralContext
      → Shows current values + pending overrides
```

### 10.2 Implementation

1. `BehaviouralCompartment.tsx` imports `useBehavioural()` from main's
   `BehaviouralContext`
2. The "Current Assumptions" left panel reads from context:
   ```typescript
   const { nmdCoreProportion, nmdCoreAvgMaturity, nmdPassThrough,
           loanPrepaymentSMM, termDepositTDRR } = useBehavioural();
   ```
3. The "Override Form" right panel writes to context:
   ```typescript
   const { setNmdCoreProportion, setLoanPrepaymentSMM, ... } = useBehavioural();
   ```
4. When user creates a `behavioural` modification in the workbench, it:
   a. Stores the modification in WhatIfContext (for badge display + apply tracking)
   b. Updates BehaviouralContext values (so the override takes effect immediately)

### 10.3 Reconciling the two UIs

- **Standalone modal:** Shows 3-tab layout (NMDs / Loans / Term Deposits) with
  19-bucket NMD distribution chart. More detailed.
- **Workbench compartment:** Shows summary + override form. Less detailed but
  integrated into the what-if workflow.

Both are kept. They read/write the same context. Changes in one are immediately
visible in the other.

---

## 11. Phase 9 — Meticulous Testing & Validation

This phase is comprehensive. Every layer is tested independently, then integrated.
Nothing ships until every check passes.

---

### 11.1 Backend Unit Tests — Decomposer

**File:** `backend/engine/tests/test_whatif_decomposer.py`

#### 11.1.1 Motor row schema compliance

Every row produced by `decompose_loan()` must have all required columns with
correct types. This is the most critical test — a schema mismatch crashes the
EVE/NII engine at runtime.

```python
REQUIRED_COLUMNS = {
    "contract_id": str,
    "side": str,            # "A" or "L"
    "source_contract_type": str,
    "notional": float,
    "fixed_rate": float,
    "spread": float,
    "start_date": date,
    "maturity_date": date,
    "daycount_base": str,
    "payment_freq": str,
    "currency": str,
    "rate_type": str,       # "fixed" or "float"
}

OPTIONAL_COLUMNS = {
    "index_name": (str, type(None)),
    "next_reprice_date": (date, type(None)),
    "repricing_freq": (str, type(None)),
    "floor_rate": (float, type(None)),
    "cap_rate": (float, type(None)),
}
```

**Tests:**
- `test_schema_fixed_bullet` — 1 position, all required columns present
- `test_schema_variable_linear` — verify index_name, repricing_freq populated
- `test_schema_mixed_with_grace` — 5 positions, ALL rows pass schema check
- `test_schema_no_extra_columns` — no unexpected columns that would confuse engine
- `test_side_values` — side is always "A" or "L", never "asset"/"liability"
- `test_source_contract_type_values` — always one of the 8 motor types
- `test_rate_type_values` — "fixed" or "float", never "variable" or "mixed"

#### 11.1.2 Simple decomposition (1 position)

| Test | Spec | Expected |
|------|------|----------|
| `test_fixed_bullet` | 10M, 5Y, fixed 3%, bullet | 1 row: `fixed_bullet`, notional=10M |
| `test_fixed_linear` | 10M, 5Y, fixed 3%, linear | 1 row: `fixed_linear`, notional=10M |
| `test_fixed_annuity` | 10M, 5Y, fixed 3%, annuity | 1 row: `fixed_annuity`, notional=10M |
| `test_variable_bullet` | 10M, 5Y, EURIBOR+50bps, bullet | 1 row: `variable_bullet`, spread=0.005 |
| `test_variable_linear` | 10M, 5Y, EURIBOR+50bps, linear | 1 row: `variable_linear` |
| `test_bullet_with_grace` | 10M, 5Y, bullet, grace=2Y | 1 row (grace irrelevant for bullet) |

#### 11.1.3 Grace period decomposition (3 positions)

| Test | Spec | Expected positions |
|------|------|-------------------|
| `test_fixed_linear_grace` | 100M, 13Y, fixed 2.4%, linear, grace=2Y | 3: grace_bullet + amort_linear + offset |
| `test_fixed_annuity_grace` | 50M, 10Y, fixed 3%, annuity, grace=1Y | 3: grace_bullet + amort_annuity + offset |
| `test_variable_linear_grace` | 100M, 13Y, EURIBOR+17.5bps, linear, grace=2Y | 3: all variable type |

**Invariant checks for grace decomposition:**
- `test_grace_dates` — grace_bullet maturity == grace_end; amort_leg start == grace_end
- `test_grace_offset_cancels` — offset position has INVERSE side of main position
- `test_grace_offset_zero_rate` — offset fixed_rate == 0.0
- `test_grace_offset_one_day` — offset start = grace_end - 1 day, maturity = grace_end
- `test_grace_notionals_match` — grace_bullet.notional == amort_leg.notional == spec.notional

#### 11.1.4 Mixed rate decomposition (3-5 positions)

| Test | Spec | Expected |
|------|------|----------|
| `test_mixed_bullet_no_grace` | 100M, 13Y, 2.4% for 4Y then EURIBOR+17.5bps, bullet | 3: fixed_bullet (4Y) + variable_bullet (9Y) + offset |
| `test_mixed_linear_no_grace` | 100M, 13Y, same, linear | 3: fixed_linear + cancel_linear + variable_linear |
| `test_mixed_linear_with_grace` | 100M, 13Y, same, linear, grace=2Y | 5: grace + amort + cancel + variable + offset |

**Invariant checks for mixed decomposition:**
- `test_mixed_switch_date` — fixed leg maturity == start + mixed_fixed_years
- `test_mixed_variable_start` — variable leg start == fixed leg maturity
- `test_mixed_cancel_inverse_side` — cancel position has inverse side
- `test_mixed_residual_notional` — cancel/variable notional < original (amortized)

#### 11.1.5 Date calculation tests

- `test_dates_from_term_years` — no start_date given → uses today; maturity = today + term_years
- `test_dates_from_explicit_start` — start_date="2025-01-15", term=5Y → maturity = 2030-01-15
- `test_dates_from_analysis_date` — analysis_date provided, no start_date → uses analysis_date
- `test_grace_end_calculation` — grace_years=2.5 → grace_end = start + 913 days
- `test_maturity_after_start` — always maturity > start (no zero-duration positions)

#### 11.1.6 Floor/Cap passthrough

- `test_floor_rate_propagated` — floor_rate=0.001 appears in ALL decomposed positions
- `test_cap_rate_propagated` — cap_rate=0.05 appears in ALL decomposed positions
- `test_floor_cap_none_default` — no floor/cap → None in output (not 0.0)

#### 11.1.7 Edge cases

- `test_zero_notional` — notional=0 → valid output (0-notional positions)
- `test_very_short_term` — term_years=0.25 (3 months) → valid dates
- `test_very_long_term` — term_years=50 → valid dates
- `test_zero_grace` — grace_years=0 → same as no grace (1 position)
- `test_liability_side` — side="L" → all positions have side="L"
- `test_id_prefix` — id_prefix="custom" → contract_ids start with "custom_"

---

### 11.2 Backend Unit Tests — Find Limit Solver

**File:** `backend/engine/tests/test_whatif_find_limit.py`

#### 11.2.1 Linear solver (notional)

- `test_linear_notional_positive_target` — target EVE delta = +50M → finds correct notional
- `test_linear_notional_negative_target` — target EVE delta = -50M → finds correct notional
- `test_linear_notional_zero_target` — target = 0 → notional = 0
- `test_linear_notional_result_type` — returns `FindLimitResult` with converged=True, iterations=1

#### 11.2.2 Binary search solver

- `test_binary_rate_converges` — solve for rate, ~15 iterations, converged=True
- `test_binary_maturity_converges` — solve for maturity, converged=True
- `test_binary_spread_converges` — solve for spread, converged=True
- `test_binary_within_tolerance` — |achieved_metric - target| < tolerance (1000.0)
- `test_binary_max_iterations` — doesn't exceed ~20 iterations

#### 11.2.3 Convergence edge cases

- `test_target_at_lower_bound` — target achievable only at min value → returns lower bound
- `test_target_at_upper_bound` — target achievable only at max value → returns upper bound
- `test_target_unreachable` — target beyond max possible → converged=False, returns best estimate
- `test_floor_cap_affects_convergence` — floor/cap changes the rate sensitivity → still converges

#### 11.2.4 _mutate_spec correctness

- `test_mutate_notional` — changes only notional, all else identical
- `test_mutate_rate` — changes only fixed_rate (or spread_bps for variable)
- `test_mutate_maturity` — changes only term_years
- `test_mutate_spread` — changes only spread_bps
- `test_mutate_immutable` — original spec is not modified (returns new copy)

---

### 11.3 Backend Unit Tests — V1 Service Enrichment

**File:** `backend/engine/tests/test_whatif_v1_enrichment.py`

Tests for the new fields added to `create_synthetic_motor_row()`:

#### 11.3.1 Amortization override

- `test_amortization_bullet` — amortization="bullet" + template "fixed-loan" → `fixed_bullet` (not `fixed_annuity`)
- `test_amortization_linear` — amortization="linear" → `fixed_linear`
- `test_amortization_annuity` — amortization="annuity" → `fixed_annuity`
- `test_amortization_none_uses_template_default` — amortization=None → uses PRODUCT_TEMPLATE_TO_MOTOR default
- `test_amortization_with_variable` — variable template + amortization="linear" → `variable_linear`

#### 11.3.2 Floor/Cap passthrough

- `test_floor_rate_decimal` — floorRate=0.001 → row["floor_rate"]=0.001
- `test_cap_rate_decimal` — capRate=0.05 → row["cap_rate"]=0.05
- `test_floor_cap_none` — no floor/cap → row["floor_rate"]=None, row["cap_rate"]=None
- `test_floor_cap_zero` — floorRate=0.0 → row["floor_rate"]=0.0 (not None)

#### 11.3.3 Grace & mixed (V1 approximations)

- `test_grace_years_ignored_v1` — grace_years=2 → start_date unchanged (no adjustment)
- `test_mixed_treated_as_fixed_v1` — mixedFixedYears=4 → source_contract_type is fixed_* (full term)
- `test_grace_warning_logged` — grace_years>0 → warning message logged (optional)

---

### 11.4 Backend Integration Tests — API Endpoints

**File:** `backend/engine/tests/test_whatif_api_integration.py`

These tests require a running session with uploaded balance data. Use the
existing `conftest.py` fixtures.

#### 11.4.1 Decompose endpoint

- `test_decompose_fixed_bullet` — POST /whatif/decompose → 200, 1 position
- `test_decompose_with_grace` — POST /whatif/decompose → 200, 3 positions
- `test_decompose_mixed_with_grace` — POST /whatif/decompose → 200, 5 positions
- `test_decompose_invalid_spec` — missing notional → 422
- `test_decompose_invalid_session` — nonexistent session → 404

#### 11.4.2 Find-limit endpoint

- `test_find_limit_notional` — solve_for="notional" → converged=True, found_value > 0
- `test_find_limit_rate` — solve_for="rate" → converged=True, 0 < found_value < 0.20
- `test_find_limit_invalid_metric` — target_metric="invalid" → 422
- `test_find_limit_invalid_session` — nonexistent session → 404

#### 11.4.3 V1 calculate/whatif with enriched payload

- `test_whatif_add_with_amortization` — amortization="linear" → EVE delta reflects linear amort
- `test_whatif_add_with_floor_cap` — floorRate + capRate → EVE delta differs from no floor/cap
- `test_whatif_add_and_remove_combined` — 1 add + 1 remove → both reflected in deltas
- `test_whatif_empty_modifications` — empty list → all deltas = 0

#### 11.4.4 Response shape validation

For every API response, validate:
- `test_response_has_session_id` — session_id matches request
- `test_response_has_all_scenarios` — scenario_eve_deltas keys match loaded scenarios
- `test_response_eve_buckets_count` — eve_bucket_deltas has entries for every scenario × bucket
- `test_response_nii_months_count` — nii_month_deltas has 12 entries per scenario
- `test_response_bucket_names_ordered` — buckets in chronological order (0-1Y, 1-2Y, ...)
- `test_response_month_labels_ordered` — months in calendar order

---

### 11.5 Backend Schema Tests

**File:** `backend/engine/tests/test_whatif_schemas.py`

Pydantic model validation:

- `test_loan_spec_item_defaults` — only id + notional + term_years required; rest has defaults
- `test_loan_spec_item_all_fields` — all 19 fields populated → valid
- `test_loan_spec_item_negative_notional` — negative notional → accepted (abs taken by engine)
- `test_find_limit_request_valid` — all fields populated → valid
- `test_find_limit_request_invalid_solve_for` — solve_for="invalid" → accepted by schema (validated by router)
- `test_decompose_response_round_trip` — serialize → deserialize → identical

---

### 11.6 Frontend Type Safety

```bash
npx tsc --noEmit
```

**Must pass with zero errors.** This validates:
- All new types in `whatif.ts` are internally consistent
- All component imports resolve (no missing modules)
- API function signatures match response types
- WhatIfContext provides all required fields
- BehaviouralCompartment ↔ BehaviouralContext type compatibility
- ProductConfigForm ↔ constants.ts template field types match

---

### 11.7 Frontend Lint & Build

```bash
npm run lint          # ESLint — no new warnings
npm run build         # Vite production build — must succeed
```

Build failure = broken tree-shaking or import resolution.

---

### 11.8 End-to-End Smoke Tests (Manual)

These are sequential — each step depends on the previous.

#### Scenario A: Basic Add + Remove + Apply

| Step | Action | Expected result |
|------|--------|----------------|
| A1 | Start backend (`uvicorn`) + frontend (`npm run dev`) | Both running, no errors |
| A2 | Upload Unicaja ZIP balance file | Balance tree renders with groups |
| A3 | Run base calculation (Base + 6 scenarios) | ResultsCard shows EVE/NII per scenario |
| A4 | Click "What-If" button | WhatIfWorkbench modal opens with 4 tabs |
| A5 | Tab: Buy/Sell → Side: Asset → Family: Loans → Variant: Fixed Rate | Form progresses (Row 1 → Row 2 → Row 3) |
| A6 | Fill: Notional=10M, Rate=3.5%, Start=2026-01-15, Maturity=2031-01-15, Payment=Quarterly | All fields populated, "Add" button enabled |
| A7 | Click "Add to Modifications" | Badge appears: "Adds: 1" |
| A8 | Tab: Buy/Sell → Left panel → Expand "Deposits" group | Subcategories visible |
| A9 | Click "Remove All" on Sight Deposits | Badge appears: "Removes: 1" |
| A10 | Click "Apply to Analysis" | Modal closes, ResultsCard shows loading |
| A11 | Wait for calculation | 3-column table: Baseline / What-If Δ / Post What-If |
| A12 | Verify EVE delta is nonzero | Asset add + liability remove = measurable impact |
| A13 | Verify NII delta is nonzero | Interest income + expense changed |
| A14 | Check EVE chart | Base bars + what-if overlay visible per bucket |
| A15 | Check NII chart | Base line + what-if dashed line visible per month |

#### Scenario B: Find Limit

| Step | Action | Expected result |
|------|--------|----------------|
| B1 | (Continue from A3 — base calculation done) | |
| B2 | Open What-If Workbench → Tab: Find Limit | Left: constraint form, Right: product form |
| B3 | Left: Metric=EVE, Scenario=Base, Solve For=Notional | Notional field hidden from product form |
| B4 | Right: Side=Asset, Family=Loans, Fixed Rate, 5Y, 3.5% | All fields except notional filled |
| B5 | Left: Limit=50,000,000 (absolute) | Target set |
| B6 | Click "Find Limit" | Loading spinner, ~5-15 seconds |
| B7 | Result appears | "Found: €XX.XM notional, Achieved: €49.9M EVE delta" |
| B8 | Verify converged=true | No warning banner |
| B9 | Click "Add to Modifications" | Badge: "Adds: 1" with solved notional |

#### Scenario C: Behavioural Override

| Step | Action | Expected result |
|------|--------|----------------|
| C1 | Open What-If Workbench → Tab: Behavioural | Left: current assumptions, Right: override form |
| C2 | Left panel shows current NMD/Prepayment/TDRR values | Values from BehaviouralContext |
| C3 | Right: Family=NMD, Core Proportion=50% (was 60%) | Field populated |
| C4 | Click "Apply Override" | Badge: "Behavioural: 1" |
| C5 | Left panel: Core Proportion shows strikethrough 60% → 50% | Visual confirmation |
| C6 | Open standalone BehaviouralAssumptionsModal | Same NMD value (50%) reflected |
| C7 | Apply to Analysis → Check results | NII delta reflects changed deposit decay |

#### Scenario D: Pricing Compartment

| Step | Action | Expected result |
|------|--------|----------------|
| D1 | Open What-If Workbench → Tab: Pricing | Left: portfolio snapshot, Right: repricing form |
| D2 | Left panel shows volumes, avg rates, annual interest | Matches balance data |
| D3 | Right: Product=Mortgages, Scope=Entire, Rate Mode=Delta, +50bps | Impact preview |
| D4 | Preview: shows new rate, new annual interest, ΔNII | Computed correctly |
| D5 | Click "Add Override" | Badge: "Pricing: 1" |
| D6 | Left panel: Mortgages row shows strikethrough + new values | Visual confirmation |

#### Scenario E: Multi-Modification Apply

| Step | Action | Expected result |
|------|--------|----------------|
| E1 | Add 2 positions (1 fixed loan + 1 floating bond) | Adds: 2 |
| E2 | Remove 1 subcategory (term deposits) | Removes: 1 |
| E3 | Add behavioural override (lower TDRR) | Behavioural: 1 |
| E4 | Apply to Analysis | All 4 modifications sent to backend |
| E5 | Results show combined impact | EVE and NII deltas reflect ALL modifications |
| E6 | Edit the fixed loan (change rate 3.5% → 4.0%) | isApplied resets, results show "stale" |
| E7 | Re-apply to Analysis | New results with updated rate |

#### Scenario F: Clear and Reset

| Step | Action | Expected result |
|------|--------|----------------|
| F1 | (From Scenario E with applied results) | |
| F2 | Open workbench → Click "Clear All" | All badges clear |
| F3 | Results revert to base-only (no what-if column) | 3-column → single baseline column |
| F4 | Charts show base-only (no overlay) | Clean base case charts |

#### Scenario G: Edge Cases

| Step | Action | Expected result |
|------|--------|----------------|
| G1 | Add position with floor_rate=0.1% and cap_rate=5% | Badge appears |
| G2 | Apply → check EVE delta differs from no-floor/cap | Floor/cap affects cashflows |
| G3 | Add position with amortization=linear (not template default) | Badge with correct label |
| G4 | Apply → check EVE shows linear amort profile | Tenor distribution differs from bullet |
| G5 | Add variable-rate position without repricing freq | Should default to payment_freq |
| G6 | Remove individual contracts (not "all") | Specific contract_ids in payload |
| G7 | Apply with only removals (no adds) | Negative EVE/NII delta |
| G8 | Apply with only adds (no removals) | Positive/negative depending on side |

---

### 11.9 Regression Tests

Run the full existing test suite to verify no regressions:

```bash
# Backend: all 186+ existing tests
cd backend && .venv/bin/python -m pytest engine/tests/ -v --tb=short

# Frontend: TypeScript + build
npx tsc --noEmit && npm run build
```

**Specific regressions to watch for:**

| Area | What could break | How to detect |
|------|-----------------|---------------|
| Base /calculate endpoint | Schema changes in schemas.py | Existing test_calculate tests |
| Balance tree rendering | BalancePositionsCard prop changes | Manual: upload + verify tree |
| BehaviouralContext | New fields or changed interface | TypeScript compilation |
| ResultsCard baseline display | Changed props or state shape | Manual: run base calculation |
| V1 calculateWhatIf | Changed WhatIfModificationItem schema | Existing whatif tests |
| Import resolution | New engine/services/whatif/ package | Python import check + pytest |

---

### 11.10 Performance Baseline

Measure before and after integration to ensure no performance regression:

| Metric | Acceptable | How to measure |
|--------|-----------|----------------|
| Base EVE/NII calculation time | < 30s (6 scenarios) | ResultsCard timer |
| What-If V1 calculation time | < 15s (1 add + 1 remove) | Network tab |
| Find-limit solve time | < 30s (15 iterations) | Network tab |
| Decompose endpoint | < 1s | Network tab |
| Frontend bundle size increase | < 100KB gzipped | `npm run build` output |
| TypeScript compilation time | < 30s | `time npx tsc --noEmit` |

---

### 11.11 Known Approximations (Document in UI)

| Feature | V1 behavior | V2 (future) | UI indication |
|---------|------------|-------------|---------------|
| Grace periods | Ignored (amortization starts at start_date) | 3-position decomposition | Info tooltip on grace field |
| Mixed rates | Treated as fixed for full term | 3-5 position decomposition | Info tooltip on mixed variant |
| Scheduled amortization | Uses default amortization type | Custom schedule support | Variant disabled in form |
| IRS swaps | Treated as single-leg | Two-leg decomposition | Info banner on IRS template |
| Callable bonds | Maturity at stated date (no call exercise) | Call-truncated cashflows | Info tooltip on call date field |

---

## 12. Deferred Work

### 12.1 V2 decomposer as primary calculation path
- Migrate "Apply to Analysis" from V1 → V2 endpoint
- Decomposer handles grace, mixed rates, scheduled amortization
- Requires end-to-end validation against Banca Etica test cases

### 12.2 Exotic cashflow variability
- Irregular payment schedules
- Step-up/step-down coupons
- Callable/puttable exercise logic
- Multi-currency FX conversion

### 12.3 Visual edit representations
- Inline position cards showing individual modifications
- Drag-to-reorder modifications
- Modification grouping (by product family)

### 12.4 Persistent what-if scenarios
- Save/load modification sets to backend
- Named scenarios ("Scenario A: Add €50M mortgages")
- Compare multiple what-if scenarios side by side

### 12.5 Pricing compartment backend integration
- Repricing simulation currently frontend-only (delta NII = delta_rate × volume)
- Future: backend endpoint that recomputes NII with repriced positions
- Enables scenario-specific repricing impact (different curves → different impacts)

---

## 13. Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Motor row schema mismatch (decomposer produces incompatible rows) | High | Medium | Validate decomposer output against `REQUIRED_MOTOR_COLUMNS` list from engine |
| What-If branch components depend on shadcn UI components not installed on main | Medium | Low | Run `npx tsc --noEmit` after copy; install missing components via `npx shadcn-ui@latest add <name>` |
| BehaviouralContext API mismatch (compartment expects fields that don't exist) | Medium | Medium | Map compartment fields to context fields explicitly; add missing getters/setters to context |
| Find-limit solver doesn't converge for edge cases | Low | Medium | Return best estimate with `converged: false`; frontend shows warning |
| V1 approximations (grace/mixed ignored) produce misleading results | Medium | High | Show info banner in ResultsCard when modifications use grace/mixed: "Approximated — full accuracy coming in V2" |
| Large what-if scenarios (50+ modifications) cause slow backend response | Medium | Low | V1 processes each add/remove sequentially; consider batching if >20 modifications |

---

## 14. File Inventory

### New files to create

| File | Source | Lines | Phase |
|------|--------|-------|-------|
| `backend/engine/services/whatif/__init__.py` | What-If branch | ~7 | 1 |
| `backend/engine/services/whatif/decomposer.py` | What-If branch | ~338 | 1 |
| `backend/engine/services/whatif/find_limit.py` | What-If branch (fix imports) | ~157 | 1 |
| `backend/app/routers/whatif.py` | What-If branch (fix imports) | ~647 | 2 |
| `src/components/whatif/WhatIfWorkbench.tsx` | What-If branch | ~319 | 4 |
| `src/components/whatif/BuySellCompartment.tsx` | What-If branch | ~874 | 4 |
| `src/components/whatif/FindLimitCompartment.tsx` | What-If branch | ~588 | 4 |
| `src/components/whatif/BehaviouralCompartment.tsx` | What-If branch (bridge to main context) | ~662 | 4 |
| `src/components/whatif/PricingCompartment.tsx` | What-If branch | ~1096 | 4 |
| `src/components/whatif/CompartmentPlaceholder.tsx` | What-If branch | ~30 | 4 |
| `src/components/whatif/shared/ProductConfigForm.tsx` | What-If branch | ~1010 | 4 |
| `src/components/whatif/shared/constants.ts` | What-If branch | ~197 | 4 |

### Files to modify

| File | Changes | Phase |
|------|---------|-------|
| `backend/app/schemas.py` | Append ~100 lines (LoanSpecItem, DecomposedPosition, FindLimit schemas) | 2 |
| `backend/app/main.py` | Add 2 lines (import + include_router) | 2 |
| `backend/engine/services/whatif.py` | Add amortization/floor/cap passthrough to `create_synthetic_motor_row()` | 6 |
| `backend/engine/banks/unicaja/whatif.py` | Add amortization override logic to template mapping | 6 |
| `src/types/whatif.ts` | Expand WhatIfModification + add ~120 lines of new types | 3 |
| `src/lib/api.ts` | Append ~80 lines (findLimit, decomposePosition functions) | 3 |
| `src/components/whatif/WhatIfContext.tsx` | Add per-type counts, expand modification types | 5 |
| `src/components/BalancePositionsCard.tsx` | Replace WhatIfBuilder with WhatIfWorkbench | 5 |
| `src/pages/Index.tsx` | Thread `scenarios` prop to BalancePositionsCard | 5 |
| `src/components/ResultsCard.tsx` | Enrich request payload, add scenario selector, wire chart overlays | 6-7 |
| `src/index.css` | Append ~36 lines of workbench-specific CSS | 4 |

### Files NOT modified (remain as-is)

- `backend/engine/services/eve.py` — untouched
- `backend/engine/services/nii.py` — untouched
- `backend/engine/services/nii_projectors.py` — untouched
- `backend/engine/workers.py` — untouched
- `backend/app/routers/calculate.py` — untouched (V1 endpoint continues to work)
- `src/components/behavioural/BehaviouralContext.tsx` — untouched (compartment adapts to it)
- `src/components/behavioural/BehaviouralAssumptionsModal.tsx` — untouched

---

## Execution Order

```
Phase 1 ─── Backend engine layer (decomposer + find_limit)      ── ~1h
Phase 2 ─── Backend API layer (schemas + router + main.py)       ── ~1h
  └─ Run: pytest (existing 186 tests must pass)
Phase 3 ─── Frontend types + API client                          ── ~30min
Phase 4 ─── Frontend components (copy 8 new files + CSS)         ── ~1h
  └─ Run: npx tsc --noEmit (must compile clean)
Phase 5 ─── WhatIfContext upgrade + BalancePositionsCard wiring   ── ~2h
Phase 6 ─── ResultsCard enrichment (payload + summary table)      ── ~2h
Phase 7 ─── Chart overlays (EVE per-tenor + NII per-month)        ── ~3h
Phase 8 ─── BehaviouralCompartment ↔ BehaviouralContext bridge    ── ~1h
  └─ Run: npx tsc --noEmit + npm run build (must succeed)
Phase 9 ─── Meticulous testing                                    ── ~4h
  9.1  Decomposer unit tests (schema, 1-pos, 3-pos, 5-pos)       ── ~1h
  9.2  Find-limit solver unit tests (linear, binary, edge cases)  ── ~30min
  9.3  V1 enrichment tests (amortization, floor/cap)              ── ~30min
  9.4  API integration tests (decompose, find-limit, whatif)      ── ~30min
  9.5  Schema validation tests                                    ── ~15min
  9.6  Frontend tsc + lint + build                                ── ~15min
  9.7  E2E smoke tests (Scenarios A-G, 7 flows)                  ── ~1h
  9.8  Regression: full pytest + build                            ── ~15min
  9.9  Performance baseline                                       ── ~15min
                                                           TOTAL ── ~16h
```
