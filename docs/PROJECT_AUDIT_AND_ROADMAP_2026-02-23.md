# ALMReady — Project Audit & Improvement Roadmap

**Date**: 2026-02-23
**Context**: Post main.py decomposition session. This document captures the full audit findings and all open improvement proposals so they survive across sessions.

---

## Table of Contents

1. [Completed Work: main.py Decomposition](#1-completed-work-mainpy-decomposition)
2. [Project Structure Audit](#2-project-structure-audit)
3. [Test Infrastructure Audit](#3-test-infrastructure-audit)
4. [Open Proposals (Prioritized)](#4-open-proposals-prioritized)
5. [Existing Planning Documents](#5-existing-planning-documents)

---

## 1. Completed Work: main.py Decomposition

**Status**: DONE — needs git commit.

The monolithic `backend/app/main.py` (3,196 lines) was decomposed into 14 modular files with zero functional changes. All 19 API endpoints verified working (23 total including FastAPI built-ins).

### New Architecture

```
backend/app/                          Lines
├── __init__.py                         0
├── main.py              (was 3,196)   57   ← lifespan, app, CORS, router includes, /health
├── state.py                           28   ← _executor, _SESSIONS, progress dicts, SESSIONS_DIR
├── schemas.py                        273   ← 28 Pydantic models
├── config.py                          95   ← domain constants, balance_config re-exports, What-If maps
├── session.py                        132   ← 12 path helpers + 4 session persistence funcs
├── filters.py                        184   ← filtering, faceting, aggregation (8 functions)
├── parsers/
│   ├── __init__.py                     0
│   ├── transforms.py                 285   ← 15+ value normalization helpers
│   ├── balance_parser.py             658   ← canonicalize, tree, parse Excel/ZIP, persist, motor DF
│   └── curves_parser.py             253   ← tenor parsing, curves workbook, forward curves, persist
└── routers/
    ├── __init__.py                     0
    ├── sessions.py                    43   ← POST /api/sessions, GET /api/sessions/{id}
    ├── balance.py                    287   ← 7 balance endpoints (upload, zip, summary, details, etc.)
    ├── curves.py                      80   ← 4 curves endpoints (upload, summary, points, delete)
    └── calculate.py                  693   ← 5 calc endpoints + What-If helpers
                                    ─────
                              TOTAL  3,068
```

### Import DAG (no cycles)

```
Layer 0: state, schemas, config           (no app.* imports)
Layer 1: session                          (← state, schemas)
Layer 2: parsers/transforms               (← schemas, config)
Layer 3: parsers/balance_parser           (← schemas, config, state, session, transforms)
         parsers/curves_parser            (← schemas, session, transforms)
Layer 4: filters                          (← schemas, transforms)
Layer 5: routers/*                        (← schemas, state, session, parsers/*, filters)
Layer 6: main                             (← state, routers/*)
```

### Critical Implementation Detail

`_executor` is rebound (`None` → `ProcessPoolExecutor`) in lifespan. All modules access it as `state._executor` (attribute on module object), NOT via `from app.state import _executor` (which would capture the initial `None`).

### Router-to-Endpoint Mapping

| Router | Endpoints |
|--------|-----------|
| `sessions.py` | `POST /api/sessions`, `GET /api/sessions/{id}` |
| `balance.py` | `POST .../balance`, `POST .../balance/zip`, `GET .../upload-progress`, `GET .../balance/summary`, `GET .../balance/details`, `GET .../balance/contracts`, `DELETE .../balance` |
| `curves.py` | `POST .../curves`, `GET .../curves/summary`, `GET .../curves/{curve_id}`, `DELETE .../curves` |
| `calculate.py` | `POST .../calculate`, `POST .../calculate/whatif`, `GET .../results`, `GET .../results/chart-data`, `GET .../calc-progress` |

---

## 2. Project Structure Audit

### 2.1 What's Good

- `.gitignore` is well-configured (covers `backend/data/`, `tests/out/`, `.DS_Store`, `__pycache__`, `.venv`)
- Backend runtime data (`backend/data/`, 769 MB) is properly gitignored
- Test output artifacts (`tests/out/`) are properly gitignored
- Fixture ZIPs are gitignored (`fixtures/positions/*.zip`)
- The decomposed module structure is clean and follows standard FastAPI patterns
- The calculation engine (`backend/almready/`) is well-separated from the API layer (`backend/app/`)

### 2.2 Issues Found

| Issue | Severity | Details |
|-------|----------|---------|
| **README.md is Lovable placeholder** | Medium | Contains `REPLACE_WITH_PROJECT_ID`, generic instructions. A banking ALM tool should have a proper README. |
| **12 `.DS_Store` files in repo** | Low | Already gitignored but some were committed earlier. Need `git rm --cached` to remove from tracking. |
| **`lovable-tagger` npm dependency** | Low | In `package.json` — may be unused dead weight from the Lovable scaffold. |
| **Spanish docs are stale** | Low | `docs/analisis-tecnico-2026-02-17.md` (153 KB) and `docs/analisis-tecnico-motor-calculo-2026-02-17.md` (61 KB) — dated Feb 17, pre-date many changes. Not harmful but not current. |
| **`backend/data/` grows unbounded** | Medium | Session uploads accumulate with no cleanup. Currently 769 MB. |
| **No `requirements.txt` lock** | Low | Only `requirements.txt` exists, no pinned lock file. |

### 2.3 Fixture Data in the Application (User-Flagged Critical)

**Location**: `backend/almready/tests/fixtures/positions/unicaja/`
**Size**: 3.2 MB (11 CSV files)
**Contents**: Real (though possibly anonymized) Unicaja bank position data

```
Fixed annuity.csv       Fixed bullet.csv        Fixed linear.csv
Fixed scheduled.csv     Non-maturity.csv        Static_position.csv
Variable annuity.csv    Variable bullet.csv     Variable linear.csv
Variable non-maturity.csv  Variable scheduled.csv
```

Also: `tests/fixtures/curves/` contains forward curve Excel file (~0.1 MB).

**Problems**:
1. Real client data should NEVER be in a git repository
2. 3.2 MB of fixtures is excessive — tests should use minimal synthetic data
3. Smoke tests (`smoke_eve_unicaja.py`, `smoke_nii_unicaja.py`) hardcode paths to `inputs/positions/unicaja/` which was already deleted during project restructuring

**Recommendation**: Replace with tiny synthetic fixtures (5-10 rows per instrument type) that exercise every code path without shipping real banking data.

---

## 3. Test Infrastructure Audit

### 3.1 Current Test Inventory

**19 unit tests** (`test_*.py`):

| Test File | What It Tests |
|-----------|---------------|
| `test_eve_engine.py` | EVE cashflow generation + PV |
| `test_eve_analytics.py` | EVE bucket breakdown |
| `test_nii_fixed_annuity.py` | NII for fixed annuity instruments |
| `test_nii_fixed_bullet.py` | NII for fixed bullet instruments |
| `test_nii_fixed_linear.py` | NII for fixed linear instruments |
| `test_nii_fixed_scheduled.py` | NII for fixed scheduled instruments |
| `test_nii_variable_annuity.py` | NII for variable annuity instruments |
| `test_nii_variable_bullet.py` | NII for variable bullet instruments |
| `test_nii_variable_linear.py` | NII for variable linear instruments |
| `test_nii_variable_scheduled.py` | NII for variable scheduled instruments |
| `test_nii_monthly_profile.py` | NII monthly profile builder |
| `test_curve_interpolation.py` | Curve interpolation logic |
| `test_regulatory_curves.py` | Regulatory curve application |
| `test_market_loader.py` | Market data loading |
| `test_margin_engine.py` | Margin calculations |
| `test_positions_pipeline.py` | Position data pipeline |
| `test_scheduled_reader.py` | Scheduled cashflow reader |

**4 smoke tests** (`smoke_*.py`):

| Test File | What It Tests |
|-----------|---------------|
| `smoke_eve_unicaja.py` | End-to-end EVE with Unicaja data |
| `smoke_nii_unicaja.py` | End-to-end NII with Unicaja data |
| `smoke_market_plot.py` | Market data visualization |
| `smoke_market_view.py` | Market data view |

### 3.2 What's Missing

| Gap | Impact |
|-----|--------|
| **Zero API integration tests** | The 19 endpoints we just refactored have no automated test coverage. If an import breaks, we find out at runtime. |
| **No test runner config** | No `pytest.ini`, `pyproject.toml [tool.pytest]`, or `conftest.py` at project root |
| **Smoke tests are broken** | Reference `inputs/positions/unicaja/` which was deleted during restructuring |
| **No CI/CD pipeline** | Tests aren't run automatically on push |

### 3.3 Recommended Test Strategy

**Phase 1 — Quick wins**:
- Add a `conftest.py` with synthetic fixtures (tiny inline DataFrames, 5-10 rows each)
- Add API integration tests using FastAPI's `TestClient` — at minimum: create session → upload balance → upload curves → calculate → get results
- Fix or remove broken smoke tests

**Phase 2 — Proper coverage**:
- Contract tests for each parser (balance, curves, transforms)
- What-If scenario tests
- Error path tests (bad uploads, missing data, invalid parameters)

**Phase 3 — CI**:
- GitHub Actions workflow: lint + unit tests + integration tests on push

---

## 4. Open Proposals (Prioritized)

### Tier 1: Do Now (high value, low effort)

| # | Proposal | Effort | Details |
|---|----------|--------|---------|
| 1 | **Commit the main.py decomposition** | 5 min | 14 new files + modified main.py are untracked/unstaged |
| 2 | **Project hygiene** | 15 min | Remove `.DS_Store` from tracking, rewrite README.md, audit `lovable-tagger` dep |
| 3 | **Session auto-cleanup** | ~15 lines | On startup, purge sessions older than N days from `backend/data/sessions/`. Add to lifespan in `main.py`. |

### Tier 2: Do Soon (high value, medium effort)

| # | Proposal | Effort | Details |
|---|----------|--------|---------|
| 4 | **Replace test fixtures with synthetic data** | 1-2 hours | Remove real Unicaja CSVs, create minimal synthetic fixtures, fix broken smoke tests |
| 5 | **API integration tests** | 2-3 hours | TestClient-based tests for the full workflow: session → upload → calculate → results |
| 6 | **ZIP Upload Parsing Optimization** | Half day | 4 phases documented in `docs/ZIP_UPLOAD_PARSING_OPTIMIZATION_PLAN.md`: fix double file read, vectorize parsing, vectorize canonicalization, switch to Parquet |

### Tier 3: Do When Ready (medium value, medium-high effort)

| # | Proposal | Effort | Details |
|---|----------|--------|---------|
| 7 | **OPT-3: Cache discount factors/yearfrac** | Small | In `compute_eve_full()` — see `docs/PERFORMANCE_OPTIMIZATION_PLAN.md` |
| 8 | **OPT-6: Vectorize pre-maturity NII** | Medium | Numpy vectorization of NII projection — see `docs/PERFORMANCE_OPTIMIZATION_PLAN.md` |
| 9 | **What-If parallelization** | Medium | Run EVE + NII scenarios in parallel for What-If calculations |

### Tier 4: Strategic / Large

| # | Proposal | Effort | Details |
|---|----------|--------|---------|
| 10 | **Unified Cashflow Engine** | Large | Merge EVE and NII into single cashflow generation pass — see `docs/UNIFIED_CASHFLOW_REFACTORING_PLAN.md` (Phases 0-2.5 done, Phase 3 partial) |
| 11 | **CI/CD pipeline** | Medium | GitHub Actions: lint, test, build on push |

---

## 5. Existing Planning Documents

| Document | Status | Contents |
|----------|--------|----------|
| `docs/PERFORMANCE_OPTIMIZATION_PLAN.md` | Partially done | OPT-1,2,5 done. OPT-3,4,6 pending. |
| `docs/UNIFIED_CASHFLOW_REFACTORING_PLAN.md` | Partially done | Phases 0-2.5 done. Phase 3 in progress. |
| `docs/ZIP_UPLOAD_PARSING_OPTIMIZATION_PLAN.md` | Not started | All 4 phases pending. |
| `docs/analisis-tecnico-2026-02-17.md` | Reference | Original Spanish technical analysis (153 KB) |
| `docs/analisis-tecnico-motor-calculo-2026-02-17.md` | Reference | Calculation engine analysis (61 KB) |
| `docs/architecture_reporting.md` | Reference | Reporting architecture notes |
| `docs/prompt-integracion-almready.md` | Reference | Integration prompt documentation |

---

## Fixed Bugs (Do Not Reintroduce)

These bugs were found and fixed in previous sessions. Documenting here to prevent regression:

1. **Worst-case EVE scenario**: Must use `min(delta_eve)`, NOT `min(absolute_eve)`
2. **What-If redundant calculations**: Eliminated duplicate `run_eve_scenarios`/`run_nii_12m_scenarios` calls
3. **Mixed dict key types in `_eve_bucket_map`**: Separated metadata from data dict to avoid string/int key collisions
4. **Chart pre-computation hang**: Computing chart data inline in `/calculate` caused 95% endpoint hang. Reverted to lazy computation on `GET /results/chart-data`
5. **ZIP upload __MACOSX**: macOS ZIP archives contain `__MACOSX/` directories with `._` prefixed files that broke the CSV parser. Fixed by filtering these out during extraction.
6. **Frontend polling ERR_INSUFFICIENT_RESOURCES**: Aggressive polling with no cleanup caused browser resource exhaustion. Fixed with proper interval cleanup.

---

*This document should be updated as proposals are completed or new ones are identified.*
