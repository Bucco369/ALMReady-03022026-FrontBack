"""Parser contract tests — transforms, curves_parser, balance_parser pure functions.

Tests the public contracts of parser helpers without going through HTTP endpoints.
Covers: value normalization, tenor parsing, side/rate-type normalization,
maturity bucketing, canonicalization, tree building.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import pytest

from app.parsers.transforms import (
    _bucket_from_years,
    _maturity_years,
    _norm_key,
    _normalize_categoria_ui,
    _normalize_rate_type,
    _normalize_side,
    _safe_sheet_summary,
    _serialize_value_for_json,
    _slugify,
    _to_float,
    _to_iso_date,
    _to_subcategory_id,
    _to_text,
    _weighted_avg_maturity,
    _weighted_avg_rate,
)
from app.parsers.curves_parser import (
    _extract_currency_from_curve_id,
    _tenor_to_years,
)


# ── _to_text ──────────────────────────────────────────────────────────────────

class TestToText:
    def test_none(self) -> None:
        assert _to_text(None) is None

    def test_nan(self) -> None:
        assert _to_text(float("nan")) is None

    def test_empty_string(self) -> None:
        assert _to_text("") is None
        assert _to_text("   ") is None

    def test_normal_string(self) -> None:
        assert _to_text("  hello ") == "hello"

    def test_number_to_string(self) -> None:
        assert _to_text(42) == "42"
        assert _to_text(3.14) == "3.14"


# ── _to_float ────────────────────────────────────────────────────────────────

class TestToFloat:
    def test_none(self) -> None:
        assert _to_float(None) is None

    def test_nan(self) -> None:
        assert _to_float(float("nan")) is None

    def test_empty_string(self) -> None:
        assert _to_float("") is None
        assert _to_float("   ") is None

    def test_valid_float(self) -> None:
        assert _to_float(3.14) == 3.14
        assert _to_float("3.14") == 3.14
        assert _to_float(0) == 0.0

    def test_invalid_string(self) -> None:
        assert _to_float("abc") is None

    def test_numpy_nan(self) -> None:
        assert _to_float(np.nan) is None


# ── _to_iso_date ─────────────────────────────────────────────────────────────

class TestToIsoDate:
    def test_none(self) -> None:
        assert _to_iso_date(None) is None

    def test_date_object(self) -> None:
        assert _to_iso_date(date(2026, 1, 15)) == "2026-01-15"

    def test_datetime_object(self) -> None:
        assert _to_iso_date(datetime(2026, 3, 1, 12, 0)) == "2026-03-01"

    def test_pd_timestamp(self) -> None:
        assert _to_iso_date(pd.Timestamp("2026-06-15")) == "2026-06-15"

    def test_string_date(self) -> None:
        assert _to_iso_date("2026-01-01") == "2026-01-01"

    def test_invalid_string(self) -> None:
        assert _to_iso_date("not-a-date") is None


# ── _norm_key / _slugify ─────────────────────────────────────────────────────

class TestNormKey:
    def test_strips_and_lowercases(self) -> None:
        assert _norm_key("  Hello World  ") == "hello world"

    def test_number_key(self) -> None:
        assert _norm_key(42) == "42"


class TestSlugify:
    def test_basic(self) -> None:
        assert _slugify("Fixed Bullet") == "fixed-bullet"

    def test_accents(self) -> None:
        assert _slugify("Préstamo Fijo") == "prestamo-fijo"

    def test_empty(self) -> None:
        assert _slugify("") == "unknown"

    def test_special_chars(self) -> None:
        assert _slugify("A_B / C") == "a-b-c"


# ── _normalize_side ──────────────────────────────────────────────────────────

class TestNormalizeSide:
    def test_explicit_asset(self) -> None:
        assert _normalize_side("Asset", "X_sheet") == "asset"
        assert _normalize_side("ASSET", "X_sheet") == "asset"

    def test_explicit_liability(self) -> None:
        assert _normalize_side("Liability", "X_sheet") == "liability"

    def test_explicit_equity(self) -> None:
        assert _normalize_side("Equity", "X_sheet") == "equity"

    def test_explicit_derivative(self) -> None:
        assert _normalize_side("Derivative", "X_sheet") == "derivative"

    def test_fallback_to_sheet_prefix(self) -> None:
        assert _normalize_side(None, "A_bonds") == "asset"
        assert _normalize_side(None, "L_deposits") == "liability"
        assert _normalize_side(None, "E_retained") == "equity"
        assert _normalize_side(None, "D_swaps") == "derivative"

    def test_default_is_asset(self) -> None:
        assert _normalize_side(None, "unknown_sheet") == "asset"
        assert _normalize_side("", "unknown_sheet") == "asset"


# ── _normalize_rate_type ─────────────────────────────────────────────────────

class TestNormalizeRateType:
    def test_fixed_variants(self) -> None:
        assert _normalize_rate_type("fixed") == "Fixed"
        assert _normalize_rate_type("fijo") == "Fixed"
        assert _normalize_rate_type("FIXED") == "Fixed"

    def test_floating_variants(self) -> None:
        assert _normalize_rate_type("variable") == "Floating"
        assert _normalize_rate_type("floating") == "Floating"
        assert _normalize_rate_type("float") == "Floating"
        assert _normalize_rate_type("nonrate") == "Floating"

    def test_unknown(self) -> None:
        assert _normalize_rate_type(None) is None
        assert _normalize_rate_type("other") is None
        assert _normalize_rate_type("") is None


# ── _normalize_categoria_ui ──────────────────────────────────────────────────

class TestNormalizeCategoriaUI:
    def test_explicit_value_preserved(self) -> None:
        assert _normalize_categoria_ui("Custom Category", "asset") == "Custom Category"

    def test_fallback_from_side(self) -> None:
        assert _normalize_categoria_ui(None, "asset") == "Assets"
        assert _normalize_categoria_ui(None, "liability") == "Liabilities"
        assert _normalize_categoria_ui(None, "equity") == "Equity"
        assert _normalize_categoria_ui(None, "derivative") == "Derivatives"

    def test_empty_string_fallback(self) -> None:
        assert _normalize_categoria_ui("", "liability") == "Liabilities"


# ── _bucket_from_years ───────────────────────────────────────────────────────

class TestBucketFromYears:
    def test_none(self) -> None:
        assert _bucket_from_years(None) is None

    def test_buckets(self) -> None:
        assert _bucket_from_years(0.5) == "<1Y"
        assert _bucket_from_years(2.0) == "1-5Y"
        assert _bucket_from_years(7.0) == "5-10Y"
        assert _bucket_from_years(15.0) == "10-20Y"
        assert _bucket_from_years(25.0) == ">20Y"

    def test_boundary_values(self) -> None:
        assert _bucket_from_years(0.999) == "<1Y"
        assert _bucket_from_years(1.0) == "1-5Y"
        assert _bucket_from_years(4.999) == "1-5Y"
        assert _bucket_from_years(5.0) == "5-10Y"
        assert _bucket_from_years(10.0) == "10-20Y"
        assert _bucket_from_years(20.0) == ">20Y"


# ── _serialize_value_for_json ────────────────────────────────────────────────

class TestSerializeValueForJson:
    def test_none(self) -> None:
        assert _serialize_value_for_json(None) is None

    def test_nan_float(self) -> None:
        assert _serialize_value_for_json(float("nan")) is None

    def test_numpy_int(self) -> None:
        assert _serialize_value_for_json(np.int64(42)) == 42

    def test_numpy_nan(self) -> None:
        assert _serialize_value_for_json(np.float64("nan")) is None

    def test_date(self) -> None:
        assert _serialize_value_for_json(date(2026, 1, 1)) == "2026-01-01"

    def test_pd_timestamp(self) -> None:
        assert _serialize_value_for_json(pd.Timestamp("2026-06-15")) == "2026-06-15"

    def test_empty_string(self) -> None:
        assert _serialize_value_for_json("") is None
        assert _serialize_value_for_json("   ") is None

    def test_normal_string(self) -> None:
        assert _serialize_value_for_json("hello") == "hello"


# ── _weighted_avg_rate / _weighted_avg_maturity ──────────────────────────────

class TestWeightedAverages:
    def test_weighted_avg_rate_basic(self) -> None:
        rows = [
            {"amount": 100.0, "rate_display": 0.05},
            {"amount": 200.0, "rate_display": 0.03},
        ]
        result = _weighted_avg_rate(rows)
        expected = (100 * 0.05 + 200 * 0.03) / 300
        assert result is not None
        assert abs(result - expected) < 1e-12

    def test_weighted_avg_rate_no_amounts(self) -> None:
        rows = [{"amount": 0.0, "rate_display": 0.05}]
        assert _weighted_avg_rate(rows) is None

    def test_weighted_avg_rate_empty(self) -> None:
        assert _weighted_avg_rate([]) is None

    def test_weighted_avg_maturity_basic(self) -> None:
        rows = [
            {"amount": 100.0, "maturity_years": 5.0},
            {"amount": 300.0, "maturity_years": 10.0},
        ]
        result = _weighted_avg_maturity(rows)
        expected = (100 * 5 + 300 * 10) / 400
        assert result is not None
        assert abs(result - expected) < 1e-12

    def test_weighted_avg_maturity_none_values(self) -> None:
        rows = [{"amount": 100.0, "maturity_years": None}]
        assert _weighted_avg_maturity(rows) is None


# ── _safe_sheet_summary ──────────────────────────────────────────────────────

class TestSafeSheetSummary:
    def test_basic_summary(self) -> None:
        df = pd.DataFrame({
            "Saldo_Ini": [100.0, 200.0, 300.0],
            "other_col": ["a", "b", "c"],
        })
        summary = _safe_sheet_summary("A_bonds", df)
        assert summary.sheet == "A_bonds"
        assert summary.rows == 3
        assert summary.total_saldo_ini == 600.0
        assert "Saldo_Ini" in summary.columns

    def test_missing_saldo_col(self) -> None:
        df = pd.DataFrame({"col_a": [1, 2]})
        summary = _safe_sheet_summary("test", df)
        assert summary.total_saldo_ini is None


# ── Tenor parsing (curves_parser) ────────────────────────────────────────────

class TestTenorToYears:
    def test_overnight(self) -> None:
        result = _tenor_to_years("ON")
        assert result is not None
        assert abs(result - 1.0 / 365.0) < 1e-10

    def test_days(self) -> None:
        result = _tenor_to_years("30D")
        assert result is not None
        assert abs(result - 30 / 365.0) < 1e-10

    def test_weeks(self) -> None:
        result = _tenor_to_years("2W")
        assert result is not None
        assert abs(result - 14 / 365.0) < 1e-10

    def test_months(self) -> None:
        result = _tenor_to_years("3M")
        assert result is not None
        assert abs(result - 3.0 / 12.0) < 1e-10

    def test_years(self) -> None:
        assert _tenor_to_years("1Y") == 1.0
        assert _tenor_to_years("30Y") == 30.0

    def test_none_and_empty(self) -> None:
        assert _tenor_to_years(None) is None
        assert _tenor_to_years("") is None

    def test_invalid(self) -> None:
        assert _tenor_to_years("XYZ") is None

    def test_case_insensitive(self) -> None:
        assert _tenor_to_years("3m") is not None
        assert _tenor_to_years("1y") == 1.0


# ── Currency extraction (curves_parser) ──────────────────────────────────────

class TestExtractCurrency:
    def test_eur_curve(self) -> None:
        assert _extract_currency_from_curve_id("EUR_ESTR_OIS") == "EUR"

    def test_usd_curve(self) -> None:
        assert _extract_currency_from_curve_id("USD_SOFR") == "USD"

    def test_no_underscore(self) -> None:
        assert _extract_currency_from_curve_id("ESTR") is None

    def test_non_alpha_prefix(self) -> None:
        assert _extract_currency_from_curve_id("123_CURVE") is None


# ── _to_subcategory_id ───────────────────────────────────────────────────────

class TestToSubcategoryId:
    def test_slugifies_label(self) -> None:
        result = _to_subcategory_id("Government Bonds", "A_bonds")
        assert isinstance(result, str)
        assert " " not in result

    def test_fallback_to_sheet(self) -> None:
        result = _to_subcategory_id(None, "A_some_sheet")
        assert isinstance(result, str)
        assert result != ""

    def test_empty_label_uses_sheet(self) -> None:
        result = _to_subcategory_id("", "L_deposits")
        assert isinstance(result, str)
        assert result != ""


# ── _maturity_years ──────────────────────────────────────────────────────────

class TestMaturityYears:
    def test_with_future_date(self) -> None:
        # A date far in the future should give positive years
        result = _maturity_years("2036-01-01", None)
        assert result is not None
        assert result > 5.0

    def test_with_past_date(self) -> None:
        # Past date returns None (negative years)
        result = _maturity_years("2020-01-01", None)
        assert result is None

    def test_with_fallback(self) -> None:
        result = _maturity_years(None, 3.5)
        assert result == 3.5

    def test_none_both(self) -> None:
        assert _maturity_years(None, None) is None

    def test_invalid_date_uses_fallback(self) -> None:
        result = _maturity_years("not-a-date", 2.0)
        assert result == 2.0
