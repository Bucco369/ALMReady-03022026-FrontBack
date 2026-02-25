"""Error path tests — bad uploads, missing data, invalid parameters.

Verifies the API returns proper HTTP error codes for invalid inputs,
missing prerequisites, and malformed data.
"""

from __future__ import annotations

import io
import zipfile

import pandas as pd
import pytest
from starlette.testclient import TestClient

from engine.tests.conftest import make_synthetic_curves_excel, make_synthetic_zip


# ── Session errors ───────────────────────────────────────────────────────────

class TestSessionErrors:
    def test_get_nonexistent_session(self, test_client: TestClient) -> None:
        resp = test_client.get("/api/sessions/does-not-exist-12345")
        assert resp.status_code == 404

    def test_balance_on_nonexistent_session(self, test_client: TestClient) -> None:
        resp = test_client.get("/api/sessions/does-not-exist/balance/summary")
        assert resp.status_code == 404

    def test_curves_on_nonexistent_session(self, test_client: TestClient) -> None:
        resp = test_client.get("/api/sessions/does-not-exist/curves/summary")
        assert resp.status_code == 404

    def test_calculate_on_nonexistent_session(self, test_client: TestClient) -> None:
        resp = test_client.post(
            "/api/sessions/does-not-exist/calculate",
            json={
                "discount_curve_id": "EUR_ESTR_OIS",
                "scenarios": ["parallel-up"],
                "analysis_date": "2026-01-01",
                "currency": "EUR",
            },
        )
        assert resp.status_code == 404

    def test_results_on_nonexistent_session(self, test_client: TestClient) -> None:
        resp = test_client.get("/api/sessions/does-not-exist/results")
        assert resp.status_code == 404

    def test_chart_data_on_nonexistent_session(self, test_client: TestClient) -> None:
        resp = test_client.get("/api/sessions/does-not-exist/results/chart-data")
        assert resp.status_code == 404


# ── Balance upload errors ────────────────────────────────────────────────────

class TestBalanceUploadErrors:
    def test_upload_non_zip_file(self, test_client: TestClient, session_id: str) -> None:
        resp = test_client.post(
            f"/api/sessions/{session_id}/balance/zip",
            files={"file": ("balance.txt", b"just plain text", "text/plain")},
        )
        assert resp.status_code == 400

    def test_upload_corrupt_zip(self, test_client: TestClient, session_id: str) -> None:
        resp = test_client.post(
            f"/api/sessions/{session_id}/balance/zip",
            files={"file": ("balance.zip", b"PK\x03\x04corrupt", "application/zip")},
        )
        assert resp.status_code == 400

    def test_upload_empty_zip(self, test_client: TestClient, session_id: str) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w"):
            pass  # empty ZIP
        buf.seek(0)
        resp = test_client.post(
            f"/api/sessions/{session_id}/balance/zip",
            files={"file": ("balance.zip", buf, "application/zip")},
        )
        # Empty ZIP has no CSVs → should fail with 400
        assert resp.status_code == 400

    def test_balance_summary_before_upload(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        resp = test_client.get(f"/api/sessions/{session_id}/balance/summary")
        assert resp.status_code == 404

    def test_balance_details_before_upload(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        resp = test_client.get(f"/api/sessions/{session_id}/balance/details")
        assert resp.status_code == 404

    def test_balance_contracts_before_upload(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        resp = test_client.get(f"/api/sessions/{session_id}/balance/contracts")
        assert resp.status_code == 404

    def test_delete_balance_before_upload(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        # Deleting when nothing exists should still be idempotent (200 ok)
        resp = test_client.delete(f"/api/sessions/{session_id}/balance")
        assert resp.status_code == 200


# ── Curves upload errors ─────────────────────────────────────────────────────

class TestCurvesUploadErrors:
    def test_upload_non_excel_file(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        resp = test_client.post(
            f"/api/sessions/{session_id}/curves",
            files={"file": ("curves.csv", b"col1,col2\n1,2", "text/csv")},
        )
        assert resp.status_code == 400

    def test_upload_excel_without_tenors(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        # Excel with no recognisable tenor columns
        df = pd.DataFrame({"CurveID": ["X"], "NotATenor": [0.05]})
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False)
        buf.seek(0)
        resp = test_client.post(
            f"/api/sessions/{session_id}/curves",
            files={"file": ("curves.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 400

    def test_curves_summary_before_upload(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        resp = test_client.get(f"/api/sessions/{session_id}/curves/summary")
        assert resp.status_code == 404

    def test_get_curve_points_before_upload(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        resp = test_client.get(f"/api/sessions/{session_id}/curves/EUR_ESTR_OIS")
        assert resp.status_code == 404

    def test_delete_curves_before_upload(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        resp = test_client.delete(f"/api/sessions/{session_id}/curves")
        assert resp.status_code == 200


# ── Calculation errors ───────────────────────────────────────────────────────

class TestCalculationErrors:
    def test_calculate_without_balance(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        # Upload curves only
        curves_buf = make_synthetic_curves_excel()
        test_client.post(
            f"/api/sessions/{session_id}/curves",
            files={"file": ("curves.xlsx", curves_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

        resp = test_client.post(
            f"/api/sessions/{session_id}/calculate",
            json={
                "discount_curve_id": "EUR_ESTR_OIS",
                "scenarios": ["parallel-up"],
                "analysis_date": "2026-01-01",
                "currency": "EUR",
            },
        )
        assert resp.status_code in (400, 404)

    def test_calculate_without_curves(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        # Upload balance only
        zip_buf = make_synthetic_zip()
        test_client.post(
            f"/api/sessions/{session_id}/balance/zip",
            files={"file": ("balance.zip", zip_buf, "application/zip")},
        )

        resp = test_client.post(
            f"/api/sessions/{session_id}/calculate",
            json={
                "discount_curve_id": "EUR_ESTR_OIS",
                "scenarios": ["parallel-up"],
                "analysis_date": "2026-01-01",
                "currency": "EUR",
            },
        )
        assert resp.status_code in (400, 404)

    def test_calculate_with_invalid_discount_curve(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        zip_buf = make_synthetic_zip()
        test_client.post(
            f"/api/sessions/{session_id}/balance/zip",
            files={"file": ("balance.zip", zip_buf, "application/zip")},
        )
        curves_buf = make_synthetic_curves_excel()
        test_client.post(
            f"/api/sessions/{session_id}/curves",
            files={"file": ("curves.xlsx", curves_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

        resp = test_client.post(
            f"/api/sessions/{session_id}/calculate",
            json={
                "discount_curve_id": "NONEXISTENT_CURVE",
                "scenarios": ["parallel-up"],
                "analysis_date": "2026-01-01",
                "currency": "EUR",
            },
        )
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"].lower()

    def test_calculate_with_invalid_analysis_date(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        zip_buf = make_synthetic_zip()
        test_client.post(
            f"/api/sessions/{session_id}/balance/zip",
            files={"file": ("balance.zip", zip_buf, "application/zip")},
        )
        curves_buf = make_synthetic_curves_excel()
        test_client.post(
            f"/api/sessions/{session_id}/curves",
            files={"file": ("curves.xlsx", curves_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

        resp = test_client.post(
            f"/api/sessions/{session_id}/calculate",
            json={
                "discount_curve_id": "EUR_ESTR_OIS",
                "scenarios": ["parallel-up"],
                "analysis_date": "not-a-date",
                "currency": "EUR",
            },
        )
        assert resp.status_code == 400

    def test_results_before_calculate(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        resp = test_client.get(f"/api/sessions/{session_id}/results")
        assert resp.status_code == 404

    def test_chart_data_before_calculate(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        resp = test_client.get(f"/api/sessions/{session_id}/results/chart-data")
        assert resp.status_code == 404


# ── Malformed request bodies ─────────────────────────────────────────────────

class TestMalformedRequests:
    def test_calculate_empty_body_without_data(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        # CalculateRequest fields have defaults; error comes from missing balance data
        resp = test_client.post(
            f"/api/sessions/{session_id}/calculate",
            json={},
        )
        assert resp.status_code in (400, 404, 422)

    def test_calculate_invalid_json(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        resp = test_client.post(
            f"/api/sessions/{session_id}/calculate",
            content=b"not json at all",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    def test_whatif_missing_modifications_field(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        resp = test_client.post(
            f"/api/sessions/{session_id}/calculate/whatif",
            json={},
        )
        assert resp.status_code == 422
