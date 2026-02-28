"""What-If analysis services.

This package contains the business logic for the What-If workbench:
- _v1: V1 synthetic row builder + unified EVE/NII computation
- decomposer: Converts high-level instrument specs into motor positions
- find_limit: Binary search solver for EVE/NII constraints
"""

# V1 re-exports (used by app/routers/calculate.py)
from ._v1 import (  # noqa: F401
    create_synthetic_motor_row,
    build_whatif_delta_dataframe,
    unified_whatif_map,
)

# V2 decomposer
from .decomposer import LoanSpec, decompose_loan  # noqa: F401
