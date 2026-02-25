"""What-If scenario tests — POST /calculate/whatif endpoint.

Tests require a fully calculated session (balance + curves + /calculate).
Verifies add, remove, and no-op modifications produce correct response shapes
and directionally sensible deltas.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from engine.tests.conftest import make_synthetic_curves_excel, make_synthetic_zip


@pytest.fixture()
def calculated_session(test_client: TestClient, session_id: str) -> str:
    """Session with balance + curves uploaded AND calculation done."""
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

    resp = test_client.post(
        f"/api/sessions/{session_id}/calculate",
        json={
            "discount_curve_id": "EUR_ESTR_OIS",
            "scenarios": ["parallel-up", "parallel-down"],
            "analysis_date": "2026-01-01",
            "currency": "EUR",
        },
    )
    assert resp.status_code == 200
    return session_id


class TestWhatIfAdd:
    """Adding a new position should produce non-zero deltas."""

    def test_add_fixed_loan_produces_eve_delta(
        self, test_client: TestClient, calculated_session: str,
    ) -> None:
        resp = test_client.post(
            f"/api/sessions/{calculated_session}/calculate/whatif",
            json={
                "modifications": [
                    {
                        "id": "wi-add-1",
                        "type": "add",
                        "label": "New fixed loan",
                        "notional": 500_000.0,
                        "category": "asset",
                        "productTemplateId": "fixed-loan",
                        "rate": 0.045,
                        "maturity": 5.0,
                        "startDate": "2026-01-01",
                        "currency": "EUR",
                        "paymentFreq": "annual",
                    }
                ]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == calculated_session
        assert "base_eve_delta" in data
        assert "base_nii_delta" in data
        assert "calculated_at" in data
        # Adding an asset should produce a non-zero EVE delta
        assert data["base_eve_delta"] != 0.0

    def test_add_term_deposit_produces_liability_delta(
        self, test_client: TestClient, calculated_session: str,
    ) -> None:
        resp = test_client.post(
            f"/api/sessions/{calculated_session}/calculate/whatif",
            json={
                "modifications": [
                    {
                        "id": "wi-add-dep",
                        "type": "add",
                        "label": "New term deposit",
                        "notional": 200_000.0,
                        "category": "liability",
                        "productTemplateId": "term-deposit",
                        "rate": 0.02,
                        "maturity": 2.0,
                        "startDate": "2026-01-01",
                        "currency": "EUR",
                        "paymentFreq": "annual",
                    }
                ]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["base_eve_delta"] != 0.0

    def test_add_floating_loan_produces_deltas(
        self, test_client: TestClient, calculated_session: str,
    ) -> None:
        resp = test_client.post(
            f"/api/sessions/{calculated_session}/calculate/whatif",
            json={
                "modifications": [
                    {
                        "id": "wi-add-float",
                        "type": "add",
                        "label": "New floating loan",
                        "notional": 300_000.0,
                        "category": "asset",
                        "productTemplateId": "floating-loan",
                        "spread": 150,
                        "maturity": 3.0,
                        "startDate": "2026-01-01",
                        "currency": "EUR",
                        "paymentFreq": "quarterly",
                        "repricingFreq": "quarterly",
                        "refIndex": "EURIBOR 3M",
                    }
                ]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["base_eve_delta"] != 0.0
        assert data["base_nii_delta"] != 0.0

    def test_add_has_scenario_deltas(
        self, test_client: TestClient, calculated_session: str,
    ) -> None:
        resp = test_client.post(
            f"/api/sessions/{calculated_session}/calculate/whatif",
            json={
                "modifications": [
                    {
                        "id": "wi-add-sc",
                        "type": "add",
                        "label": "Bond for scenario check",
                        "notional": 1_000_000.0,
                        "category": "asset",
                        "productTemplateId": "bond-portfolio",
                        "rate": 0.04,
                        "maturity": 10.0,
                        "startDate": "2026-01-01",
                        "currency": "EUR",
                        "paymentFreq": "annual",
                    }
                ]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # Scenario-level deltas should exist
        assert "scenario_eve_deltas" in data
        assert "parallel-up" in data["scenario_eve_deltas"]
        assert "parallel-down" in data["scenario_eve_deltas"]
        # For a fixed-rate asset, parallel-up vs parallel-down should differ
        assert data["scenario_eve_deltas"]["parallel-up"] != data["scenario_eve_deltas"]["parallel-down"]

    def test_add_has_bucket_and_month_deltas(
        self, test_client: TestClient, calculated_session: str,
    ) -> None:
        resp = test_client.post(
            f"/api/sessions/{calculated_session}/calculate/whatif",
            json={
                "modifications": [
                    {
                        "id": "wi-add-det",
                        "type": "add",
                        "label": "Detail check",
                        "notional": 100_000.0,
                        "category": "asset",
                        "productTemplateId": "fixed-loan",
                        "rate": 0.05,
                        "maturity": 3.0,
                        "startDate": "2026-01-01",
                        "currency": "EUR",
                        "paymentFreq": "annual",
                    }
                ]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["eve_bucket_deltas"]) > 0
        assert len(data["nii_month_deltas"]) > 0

        # Verify bucket delta structure
        bucket = data["eve_bucket_deltas"][0]
        assert "scenario" in bucket
        assert "bucket_name" in bucket
        assert "asset_pv_delta" in bucket
        assert "liability_pv_delta" in bucket

        # Verify month delta structure
        month = data["nii_month_deltas"][0]
        assert "scenario" in month
        assert "month_index" in month
        assert "month_label" in month
        assert "income_delta" in month
        assert "expense_delta" in month


class TestWhatIfRemove:
    """Removing positions should produce opposite-sign deltas."""

    def test_remove_by_contract_id(
        self, test_client: TestClient, calculated_session: str,
    ) -> None:
        # Get a contract_id from the balance
        contracts_resp = test_client.get(
            f"/api/sessions/{calculated_session}/balance/contracts",
            params={"page": 1, "page_size": 1},
        )
        assert contracts_resp.status_code == 200
        contracts = contracts_resp.json()["contracts"]
        if not contracts:
            pytest.skip("No contracts in synthetic balance")

        cid = contracts[0]["contract_id"]

        resp = test_client.post(
            f"/api/sessions/{calculated_session}/calculate/whatif",
            json={
                "modifications": [
                    {
                        "id": "wi-rem-1",
                        "type": "remove",
                        "label": "Remove one contract",
                        "removeMode": "contracts",
                        "contractIds": [cid],
                    }
                ]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # Removing a position should produce a non-zero EVE delta
        assert data["base_eve_delta"] != 0.0


class TestWhatIfNoOp:
    """Empty modifications should return zero deltas."""

    def test_empty_modifications_list(
        self, test_client: TestClient, calculated_session: str,
    ) -> None:
        resp = test_client.post(
            f"/api/sessions/{calculated_session}/calculate/whatif",
            json={"modifications": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["base_eve_delta"] == 0.0
        assert data["base_nii_delta"] == 0.0
        assert data["worst_eve_delta"] == 0.0
        assert data["worst_nii_delta"] == 0.0


class TestWhatIfErrors:
    """What-If error paths."""

    def test_whatif_without_calculate_returns_404(
        self, test_client: TestClient, session_id: str,
    ) -> None:
        resp = test_client.post(
            f"/api/sessions/{session_id}/calculate/whatif",
            json={
                "modifications": [
                    {
                        "id": "wi-err-1",
                        "type": "add",
                        "label": "Should fail",
                        "notional": 100_000.0,
                        "productTemplateId": "fixed-loan",
                        "rate": 0.05,
                        "maturity": 3.0,
                    }
                ]
            },
        )
        assert resp.status_code == 404

    def test_whatif_on_nonexistent_session(
        self, test_client: TestClient,
    ) -> None:
        resp = test_client.post(
            "/api/sessions/nonexistent-uuid/calculate/whatif",
            json={"modifications": []},
        )
        assert resp.status_code == 404
