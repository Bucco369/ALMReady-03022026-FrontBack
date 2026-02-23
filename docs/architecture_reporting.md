# Reporting Architecture (NII and EVE)

This file summarizes how the new reporting pieces connect to the existing
calculation engine, so the behavior is easy to understand when reading code.

## Design principle

- Calculation remains exact in the core engine.
- Buckets/charts are reporting layers on top of exact outputs.

## NII flow

1. `services/nii_projectors.py`
   - Instrument-level exact NII logic.
   - Optional `horizon_months` keeps default behavior (`12`) unchanged.
2. `services/nii.py`
   - `run_nii_12m_*` orchestration.
   - `build_nii_monthly_profile` derives monthly bars from the same exact engine.
3. `services/nii_charts.py`
   - Renders monthly chart (income, expense, net) per scenario.
4. `services/nii_pipeline.py`
   - End-to-end entry point from files/specs to outputs + chart.

## EVE flow

1. `services/eve.py`
   - Exact run-off cashflows and EVE valuation.
2. `services/eve_analytics.py`
   - Scenario summary (`delta vs base`, `worst`).
   - Exact bucket breakdown by side (`asset`, `liability`, `net`).
3. `services/eve_charts.py`
   - Scenario deltas chart.
   - Base vs worst by bucket chart.
   - Worst delta by bucket (+ cumulative) chart.
4. `services/eve_pipeline.py`
   - End-to-end execution from file inputs.
   - Optional chart and CSV exports.

## Buckets

- Config lives in `config/eve_buckets.py`.
- `EVE_VIS_BUCKETS_OPTIMAL` is the default grid for EVE visualization.
- Changing bucket config does not alter exact valuation logic.

## Outputs

- NII:
  - 12M base/scenario values.
  - Monthly profile DataFrame.
  - Optional monthly PNG chart.
- EVE:
  - Base/scenario values.
  - Scenario summary table.
  - Bucket breakdown table.
  - Optional PNG charts and CSV exports.

