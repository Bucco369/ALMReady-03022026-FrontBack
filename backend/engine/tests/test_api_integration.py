"""API integration tests — full workflow via FastAPI TestClient.

Tests the complete lifecycle:
  POST /api/sessions → create session
  POST /api/sessions/{id}/balance/zip → upload synthetic balance
  GET  /api/sessions/{id}/balance/summary → verify tree
  POST /api/sessions/{id}/curves → upload curves Excel
  GET  /api/sessions/{id}/curves/summary → verify curve catalog
  POST /api/sessions/{id}/calculate → run EVE+NII
  GET  /api/sessions/{id}/results → verify results
  GET  /api/sessions/{id}/results/chart-data → verify charts
  GET  /api/health → health check

All data is synthetic and created in-memory.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from engine.tests.conftest import make_synthetic_curves_excel, make_synthetic_zip


# ── Health check ───────────────────────────────────────────────────────────

class TestHealthCheck:
    def test_health_returns_ok(self, test_client: TestClient) -> None:
        resp = test_client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ── Session management ─────────────────────────────────────────────────────

class TestSessionManagement:
    def test_create_session(self, test_client: TestClient) -> None:
        resp = test_client.post("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["status"] == "active"
        assert data["schema_version"] == "v1"
        assert data["has_balance"] is False
        assert data["has_curves"] is False

    def test_get_session(self, test_client: TestClient, session_id: str) -> None:
        resp = test_client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert data["status"] == "active"

    def test_get_nonexistent_session_returns_404(self, test_client: TestClient) -> None:
        resp = test_client.get("/api/sessions/nonexistent-uuid")
        assert resp.status_code == 404


# ── Balance upload (ZIP) ───────────────────────────────────────────────────

class TestBalanceUpload:
    def test_upload_zip_returns_summary(self, test_client: TestClient, session_id: str) -> None:
        zip_buf = make_synthetic_zip()
        resp = test_client.post(
            f"/api/sessions/{session_id}/balance/zip",
            files={"file": ("balance.zip", zip_buf, "application/zip")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert data["filename"] == "balance.zip"
        assert len(data["sheets"]) > 0
        tree = data["summary_tree"]
        assert tree["assets"] is not None or tree["liabilities"] is not None

    def test_upload_non_zip_returns_400(self, test_client: TestClient, session_id: str) -> None:
        resp = test_client.post(
            f"/api/sessions/{session_id}/balance/zip",
            files={"file": ("balance.txt", b"not a zip", "text/plain")},
        )
        assert resp.status_code == 400

    def test_balance_summary_after_upload(self, test_client: TestClient, session_id: str) -> None:
        zip_buf = make_synthetic_zip()
        upload_resp = test_client.post(
            f"/api/sessions/{session_id}/balance/zip",
            files={"file": ("balance.zip", zip_buf, "application/zip")},
        )
        assert upload_resp.status_code == 200

        summary_resp = test_client.get(f"/api/sessions/{session_id}/balance/summary")
        assert summary_resp.status_code == 200
        data = summary_resp.json()
        assert data["session_id"] == session_id
        assert len(data["sheets"]) > 0

    def test_balance_summary_without_upload_returns_404(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        resp = test_client.get(f"/api/sessions/{session_id}/balance/summary")
        assert resp.status_code == 404

    def test_balance_details_after_upload(self, test_client: TestClient, session_id: str) -> None:
        zip_buf = make_synthetic_zip()
        test_client.post(
            f"/api/sessions/{session_id}/balance/zip",
            files={"file": ("balance.zip", zip_buf, "application/zip")},
        )

        resp = test_client.get(f"/api/sessions/{session_id}/balance/details")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert "totals" in data
        assert data["totals"]["positions"] > 0

    def test_balance_contracts_pagination(self, test_client: TestClient, session_id: str) -> None:
        zip_buf = make_synthetic_zip()
        test_client.post(
            f"/api/sessions/{session_id}/balance/zip",
            files={"file": ("balance.zip", zip_buf, "application/zip")},
        )

        resp = test_client.get(
            f"/api/sessions/{session_id}/balance/contracts",
            params={"page": 1, "page_size": 10},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert data["total"] > 0
        assert len(data["contracts"]) <= 10

    def test_delete_balance(self, test_client: TestClient, session_id: str) -> None:
        zip_buf = make_synthetic_zip()
        test_client.post(
            f"/api/sessions/{session_id}/balance/zip",
            files={"file": ("balance.zip", zip_buf, "application/zip")},
        )

        resp = test_client.delete(f"/api/sessions/{session_id}/balance")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        summary_resp = test_client.get(f"/api/sessions/{session_id}/balance/summary")
        assert summary_resp.status_code == 404

    def test_session_shows_has_balance_after_upload(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        zip_buf = make_synthetic_zip()
        test_client.post(
            f"/api/sessions/{session_id}/balance/zip",
            files={"file": ("balance.zip", zip_buf, "application/zip")},
        )

        resp = test_client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 200
        assert resp.json()["has_balance"] is True


# ── Curves upload ──────────────────────────────────────────────────────────

class TestCurvesUpload:
    def test_upload_curves_returns_summary(self, test_client: TestClient, session_id: str) -> None:
        curves_buf = make_synthetic_curves_excel()
        resp = test_client.post(
            f"/api/sessions/{session_id}/curves",
            files={"file": ("curves.xlsx", curves_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert len(data["curves"]) == 2
        curve_ids = {c["curve_id"] for c in data["curves"]}
        assert "EUR_ESTR_OIS" in curve_ids
        assert "EUR_EURIBOR_3M" in curve_ids

    def test_curves_summary_after_upload(self, test_client: TestClient, session_id: str) -> None:
        curves_buf = make_synthetic_curves_excel()
        test_client.post(
            f"/api/sessions/{session_id}/curves",
            files={"file": ("curves.xlsx", curves_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

        resp = test_client.get(f"/api/sessions/{session_id}/curves/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert data["default_discount_curve_id"] == "EUR_ESTR_OIS"

    def test_get_curve_points(self, test_client: TestClient, session_id: str) -> None:
        curves_buf = make_synthetic_curves_excel()
        test_client.post(
            f"/api/sessions/{session_id}/curves",
            files={"file": ("curves.xlsx", curves_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

        resp = test_client.get(f"/api/sessions/{session_id}/curves/EUR_ESTR_OIS")
        assert resp.status_code == 200
        data = resp.json()
        assert data["curve_id"] == "EUR_ESTR_OIS"
        assert len(data["points"]) == 9  # ON, 1M, 3M, 6M, 1Y, 2Y, 5Y, 10Y, 30Y

    def test_get_nonexistent_curve_returns_404(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        curves_buf = make_synthetic_curves_excel()
        test_client.post(
            f"/api/sessions/{session_id}/curves",
            files={"file": ("curves.xlsx", curves_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

        resp = test_client.get(f"/api/sessions/{session_id}/curves/NONEXISTENT")
        assert resp.status_code == 404

    def test_delete_curves(self, test_client: TestClient, session_id: str) -> None:
        curves_buf = make_synthetic_curves_excel()
        test_client.post(
            f"/api/sessions/{session_id}/curves",
            files={"file": ("curves.xlsx", curves_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

        resp = test_client.delete(f"/api/sessions/{session_id}/curves")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_session_shows_has_curves_after_upload(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        curves_buf = make_synthetic_curves_excel()
        test_client.post(
            f"/api/sessions/{session_id}/curves",
            files={"file": ("curves.xlsx", curves_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

        resp = test_client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 200
        assert resp.json()["has_curves"] is True


# ── Full calculation workflow ──────────────────────────────────────────────

class TestCalculation:
    @pytest.fixture()
    def ready_session(self, test_client: TestClient, session_id: str) -> str:
        """Session with balance + curves uploaded, ready for calculation."""
        zip_buf = make_synthetic_zip()
        resp = test_client.post(
            f"/api/sessions/{session_id}/balance/zip",
            files={"file": ("balance.zip", zip_buf, "application/zip")},
        )
        assert resp.status_code == 200

        curves_buf = make_synthetic_curves_excel()
        resp = test_client.post(
            f"/api/sessions/{session_id}/curves",
            files={"file": ("curves.xlsx", curves_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 200
        return session_id

    def test_calculate_returns_results(
        self, test_client: TestClient, ready_session: str,
    ) -> None:
        resp = test_client.post(
            f"/api/sessions/{ready_session}/calculate",
            json={
                "discount_curve_id": "EUR_ESTR_OIS",
                "scenarios": ["parallel-up", "parallel-down"],
                "analysis_date": "2026-01-01",
                "currency": "EUR",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == ready_session
        assert isinstance(data["base_eve"], (int, float))
        assert isinstance(data["base_nii"], (int, float))
        assert data["worst_case_scenario"] in ("parallel-up", "parallel-down")
        assert len(data["scenario_results"]) == 2

        for sr in data["scenario_results"]:
            assert "scenario_id" in sr
            assert "eve" in sr
            assert "nii" in sr
            assert "delta_eve" in sr
            assert "delta_nii" in sr

    def test_results_endpoint_after_calculate(
        self, test_client: TestClient, ready_session: str,
    ) -> None:
        test_client.post(
            f"/api/sessions/{ready_session}/calculate",
            json={
                "discount_curve_id": "EUR_ESTR_OIS",
                "scenarios": ["parallel-up", "parallel-down"],
                "analysis_date": "2026-01-01",
                "currency": "EUR",
            },
        )

        resp = test_client.get(f"/api/sessions/{ready_session}/results")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == ready_session
        assert "base_eve" in data
        assert "calculated_at" in data

    def test_chart_data_after_calculate(
        self, test_client: TestClient, ready_session: str,
    ) -> None:
        test_client.post(
            f"/api/sessions/{ready_session}/calculate",
            json={
                "discount_curve_id": "EUR_ESTR_OIS",
                "scenarios": ["parallel-up", "parallel-down"],
                "analysis_date": "2026-01-01",
                "currency": "EUR",
            },
        )

        resp = test_client.get(f"/api/sessions/{ready_session}/results/chart-data")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == ready_session
        assert "eve_buckets" in data
        assert "nii_monthly" in data
        assert len(data["eve_buckets"]) > 0
        assert len(data["nii_monthly"]) > 0

    def test_results_without_calculate_returns_404(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        resp = test_client.get(f"/api/sessions/{session_id}/results")
        assert resp.status_code == 404

    def test_chart_data_without_calculate_returns_404(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        resp = test_client.get(f"/api/sessions/{session_id}/results/chart-data")
        assert resp.status_code == 404

    def test_calculate_without_balance_returns_error(
        self, test_client: TestClient, session_id: str,
    ) -> None:
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

    def test_scenario_eve_deltas_are_consistent(
        self, test_client: TestClient, ready_session: str,
    ) -> None:
        """delta_eve = scenario_eve - base_eve for each scenario."""
        resp = test_client.post(
            f"/api/sessions/{ready_session}/calculate",
            json={
                "discount_curve_id": "EUR_ESTR_OIS",
                "scenarios": ["parallel-up", "parallel-down"],
                "analysis_date": "2026-01-01",
                "currency": "EUR",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        base_eve = data["base_eve"]

        for sr in data["scenario_results"]:
            expected_delta = sr["eve"] - base_eve
            assert abs(sr["delta_eve"] - expected_delta) < 1e-6, (
                f"Scenario {sr['scenario_id']}: delta_eve mismatch"
            )

    def test_worst_case_uses_min_delta_eve(
        self, test_client: TestClient, ready_session: str,
    ) -> None:
        """Worst case scenario should have the minimum delta_eve."""
        resp = test_client.post(
            f"/api/sessions/{ready_session}/calculate",
            json={
                "discount_curve_id": "EUR_ESTR_OIS",
                "scenarios": ["parallel-up", "parallel-down"],
                "analysis_date": "2026-01-01",
                "currency": "EUR",
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        min_delta = min(sr["delta_eve"] for sr in data["scenario_results"])
        assert abs(data["worst_case_delta_eve"] - min_delta) < 1e-6


# ── Upload progress ────────────────────────────────────────────────────────

class TestProgressEndpoints:
    def test_upload_progress_idle(self, test_client: TestClient, session_id: str) -> None:
        resp = test_client.get(f"/api/sessions/{session_id}/upload-progress")
        assert resp.status_code == 200
        data = resp.json()
        assert data["phase"] == "idle"

    def test_calc_progress_idle(self, test_client: TestClient, session_id: str) -> None:
        resp = test_client.get(f"/api/sessions/{session_id}/calc-progress")
        assert resp.status_code == 200
        data = resp.json()
        assert data["phase"] == "idle"
