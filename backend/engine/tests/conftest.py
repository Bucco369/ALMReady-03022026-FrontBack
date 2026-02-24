"""Shared pytest fixtures for engine and API integration tests.

Provides:
- test_client: session-scoped FastAPI TestClient with lifespan handling
- session_id: per-test session with automatic cleanup
- make_synthetic_zip: builds in-memory ZIP from synthetic CSVs
- make_synthetic_curves_excel: builds in-memory Excel with forward curves
- SYNTHETIC_*: pre-built CSV/Excel content constants
"""

from __future__ import annotations

import io
import shutil
import zipfile
from typing import Any

import pandas as pd
import pytest
from starlette.testclient import TestClient

import app.state as state
from app.main import app


# ── TestClient ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def test_client():
    """Session-scoped TestClient; triggers app lifespan (ProcessPoolExecutor)."""
    with TestClient(app) as client:
        yield client


# ── Session management ─────────────────────────────────────────────────────

@pytest.fixture()
def session_id(test_client: TestClient):
    """Create a fresh API session, yield its id, clean up on teardown."""
    resp = test_client.post("/api/sessions")
    assert resp.status_code == 200
    sid = resp.json()["session_id"]
    yield sid
    session_dir = state.SESSIONS_DIR / sid
    if session_dir.exists():
        shutil.rmtree(session_dir)


# ── Synthetic CSV data (Unicaja format) ────────────────────────────────────
#
# Columns match bank_mapping_unicaja.BANK_COLUMNS_MAP.
# The header row contains "Identifier" which triggers header_token detection.
# Rates are in percentage points (scaled by 0.01 via NUMERIC_SCALE_MAP).
# Amounts use comma as decimal separator (European locale via cp1252).

SYNTHETIC_FIXED_BULLET_CSV = """\
File type;Contracts
Charset;ISO-8859-1
Contract type;Fixed bullet
Reference day;01/01/2026
;Identifier;Start date;Maturity date;Position;Outstanding principal;Day count convention;Last adjusted rate;Payment period
contract;FB_001;01/01/2025;01/01/2028;Long;100000,0;Actual/360;5,00;12M
contract;FB_002;01/06/2025;01/06/2027;Short;50000,0;Actual/360;3,00;12M
"""

SYNTHETIC_FIXED_ANNUITY_CSV = """\
File type;Contracts
Charset;ISO-8859-1
Contract type;Fixed annuity
Reference day;01/01/2026
Identifier;Start date;Maturity date;Position;Outstanding principal;Day count convention;Last adjusted rate;Payment period
FA_001;01/01/2025;01/01/2029;Long;200000,0;Actual/360;4,50;12M
"""

SYNTHETIC_VARIABLE_BULLET_CSV = """\
File type;Contracts
Charset;ISO-8859-1
Contract type;Variable bullet
Reference day;01/01/2026
;Identifier;Start date;Maturity date;Position;Outstanding principal;Tipo tasa;Day count convention;Indexed curve;Interest spread;Reset period;Payment period
contract;VB_001;01/01/2025;01/01/2028;Long;150000,0;VAR;Actual/360;EUR_EURIBOR_3M;1,50;3M;3M
"""


# ── Synthetic curves (Excel) ──────────────────────────────────────────────
#
# First column = curve_id, remaining columns = tenor labels.
# Values are rates as decimals (e.g. 0.035 = 3.5%).

SYNTHETIC_CURVES_DATA: dict[str, list[dict[str, Any]]] = {
    "EUR_ESTR_OIS": [
        {"ON": 0.030, "1M": 0.031, "3M": 0.032, "6M": 0.033,
         "1Y": 0.035, "2Y": 0.037, "5Y": 0.039, "10Y": 0.040, "30Y": 0.042},
    ],
    "EUR_EURIBOR_3M": [
        {"ON": 0.035, "1M": 0.036, "3M": 0.037, "6M": 0.038,
         "1Y": 0.040, "2Y": 0.042, "5Y": 0.044, "10Y": 0.045, "30Y": 0.047},
    ],
}


# ── Helper functions ───────────────────────────────────────────────────────

def make_synthetic_zip(
    csv_files: dict[str, str] | None = None,
) -> io.BytesIO:
    """Build an in-memory ZIP of CSV files in Unicaja format.

    Parameters
    ----------
    csv_files : dict mapping filename -> CSV text content.
        If None, uses a minimal default set (fixed_bullet + fixed_annuity).
    """
    if csv_files is None:
        csv_files = {
            "Fixed bullet.csv": SYNTHETIC_FIXED_BULLET_CSV,
            "Fixed annuity.csv": SYNTHETIC_FIXED_ANNUITY_CSV,
            "Variable bullet.csv": SYNTHETIC_VARIABLE_BULLET_CSV,
        }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in csv_files.items():
            zf.writestr(name, content.encode("cp1252"))
    buf.seek(0)
    return buf


def make_synthetic_curves_excel(
    curves_data: dict[str, list[dict[str, Any]]] | None = None,
) -> io.BytesIO:
    """Build an in-memory Excel workbook with forward curve data.

    Parameters
    ----------
    curves_data : dict mapping curve_id -> list of dicts with tenor columns.
        If None, uses SYNTHETIC_CURVES_DATA.
    """
    if curves_data is None:
        curves_data = SYNTHETIC_CURVES_DATA

    rows: list[dict[str, Any]] = []
    for curve_id, rate_rows in curves_data.items():
        for rate_row in rate_rows:
            rows.append({"CurveID": curve_id, **rate_row})

    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="ForwardCurves", index=False)
    buf.seek(0)
    return buf
