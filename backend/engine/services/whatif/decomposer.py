"""
Loan Decomposer — converts a high-level loan specification into
one or more motor-compatible position rows.

A user thinks in terms of ONE instrument ("100M loan, 13Y, carencia 2Y,
mixed 4Y fixed then variable"). The EVE/NII engine thinks in terms of
simple building blocks (fixed_bullet, fixed_linear, variable_linear, ...).

This module bridges the gap.

Examples:
    # Simple fixed bullet
    spec = LoanSpec(notional=10_000_000, term_years=5, rate_type="fixed",
                    fixed_rate=0.03, amortization="bullet")
    rows = decompose_loan(spec)  # → 1 position

    # Fixed linear with 2Y grace period
    spec = LoanSpec(notional=100_000_000, term_years=13, rate_type="fixed",
                    fixed_rate=0.024, amortization="linear", grace_years=2)
    rows = decompose_loan(spec)  # → 3 positions (grace + amort + offset)

    # Mixed with grace
    spec = LoanSpec(notional=100_000_000, term_years=13, rate_type="mixed",
                    fixed_rate=0.024, mixed_fixed_years=4,
                    variable_index="EUR_EURIBOR_12M", spread_bps=17.5,
                    amortization="linear", grace_years=2)
    rows = decompose_loan(spec)  # → 5 positions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal
import pandas as pd


# ──────────────────────────────────────────────────────────────────────
# Public types
# ──────────────────────────────────────────────────────────────────────

@dataclass
class LoanSpec:
    """High-level description of a loan/instrument.

    This is what the frontend sends. The decomposer converts it
    into N motor positions.
    """
    # Core
    notional: float
    term_years: float
    side: Literal["A", "L"] = "A"
    currency: str = "EUR"

    # Rate
    rate_type: Literal["fixed", "variable", "mixed"] = "fixed"
    fixed_rate: float | None = None
    variable_index: str | None = None
    spread_bps: float = 0.0

    # Mixed-specific
    mixed_fixed_years: float | None = None

    # Amortization
    amortization: Literal["bullet", "linear", "annuity"] = "bullet"
    grace_years: float = 0.0

    # Schedule
    daycount: str = "30/360"
    payment_freq: str = "12M"
    repricing_freq: str | None = None  # defaults to payment_freq for variable

    # Dates (optional; derived from term_years if not given)
    start_date: date | None = None
    analysis_date: date | None = None

    # Floor / Cap
    floor_rate: float | None = None
    cap_rate: float | None = None

    # Identifier prefix for generated positions
    id_prefix: str = "whatif"


# ──────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────

def _motor_row(
    contract_id: str,
    side: str,
    sct: str,
    notional: float,
    fixed_rate: float | None,
    spread: float,
    start: date,
    mat: date,
    daycount: str,
    payment_freq: str,
    currency: str,
    index_name: str | None = None,
    reprice_date: date | None = None,
    reprice_freq: str | None = None,
    rate_type: str = "fixed",
    floor_rate: float | None = None,
    cap_rate: float | None = None,
) -> dict:
    """Build a single motor-compatible row dict."""
    return {
        "contract_id": contract_id,
        "side": side,
        "source_contract_type": sct,
        "notional": notional,
        "fixed_rate": fixed_rate if fixed_rate is not None else 0.0,
        "spread": spread,
        "start_date": start,
        "maturity_date": mat,
        "index_name": index_name,
        "next_reprice_date": reprice_date,
        "daycount_base": daycount,
        "payment_freq": payment_freq,
        "repricing_freq": reprice_freq,
        "currency": currency,
        "floor_rate": floor_rate,
        "cap_rate": cap_rate,
        "rate_type": rate_type,
    }


def _resolve_dates(spec: LoanSpec) -> tuple[date, date, date]:
    """Return (start, grace_end, maturity)."""
    start = spec.start_date or spec.analysis_date or date.today()
    grace_end = start + timedelta(days=round(spec.grace_years * 365.25)) if spec.grace_years > 0 else start
    maturity = start + timedelta(days=round(spec.term_years * 365.25))
    return start, grace_end, maturity


def _sct(rate_prefix: str, amort: str) -> str:
    """Build source_contract_type string, e.g. 'fixed_linear'."""
    return f"{rate_prefix}_{amort}"


# ──────────────────────────────────────────────────────────────────────
# Core decomposition logic
# ──────────────────────────────────────────────────────────────────────

def _decompose_simple(
    spec: LoanSpec,
    rate_prefix: str,
    start: date,
    grace_end: date,
    maturity: date,
) -> list[dict]:
    """Decompose a fixed or variable loan (not mixed)."""
    spread = spec.spread_bps / 10_000 if rate_prefix == "variable" else 0.0
    fixed_rate = spec.fixed_rate if rate_prefix == "fixed" else None
    index = spec.variable_index if rate_prefix == "variable" else None
    reprice_freq = spec.repricing_freq or spec.payment_freq
    rate_type_str = "float" if rate_prefix == "variable" else "fixed"
    pid = spec.id_prefix

    has_grace = spec.grace_years > 0 and spec.amortization != "bullet"

    if not has_grace:
        # Single position — no grace period or bullet (where grace is irrelevant)
        sct = _sct(rate_prefix, spec.amortization)
        return [_motor_row(
            f"{pid}_main", spec.side, sct, spec.notional,
            fixed_rate, spread, start, maturity,
            spec.daycount, spec.payment_freq, spec.currency,
            index, start if index else None,
            reprice_freq if index else None, rate_type_str,
            spec.floor_rate, spec.cap_rate,
        )]

    # Grace period + amortization → 3 positions
    rows = []

    # 1) Grace leg: interest-only (bullet) during grace period
    grace_sct = _sct(rate_prefix, "bullet")
    rows.append(_motor_row(
        f"{pid}_grace", spec.side, grace_sct, spec.notional,
        fixed_rate, spread, start, grace_end,
        spec.daycount, spec.payment_freq, spec.currency,
        index, start if index else None,
        reprice_freq if index else None, rate_type_str,
        spec.floor_rate, spec.cap_rate,
    ))

    # 2) Amortization leg: starts at grace_end
    amort_sct = _sct(rate_prefix, spec.amortization)
    rows.append(_motor_row(
        f"{pid}_amort", spec.side, amort_sct, spec.notional,
        fixed_rate, spread, grace_end, maturity,
        spec.daycount, spec.payment_freq, spec.currency,
        index, grace_end if index else None,
        reprice_freq if index else None, rate_type_str,
        spec.floor_rate, spec.cap_rate,
    ))

    # 3) Offset: cancel the bullet principal from the grace leg
    rows.append(_motor_row(
        f"{pid}_offset", "L" if spec.side == "A" else "A",
        "fixed_bullet", spec.notional,
        0.0, 0.0, grace_end - timedelta(days=1), grace_end,
        spec.daycount, spec.payment_freq, spec.currency,
    ))

    return rows


def _decompose_mixed(
    spec: LoanSpec,
    start: date,
    grace_end: date,
    maturity: date,
) -> list[dict]:
    """Decompose a mixed-rate loan (fixed period then variable).

    Strategy for mixed + amortization:
    1. Grace period (if any): interest-only at fixed rate
    2. Full amortization at fixed rate (from grace_end to maturity)
    3. Cancel fixed interest post-switch (liability fixed_linear)
    4. Add variable interest post-switch (variable_linear)
    5. Offset to cancel grace bullet (if grace)

    Positions 3+4 have equal/opposite principal, so they cancel for
    principal while swapping the interest from fixed to variable.
    """
    if spec.mixed_fixed_years is None:
        raise ValueError("mixed_fixed_years required for rate_type='mixed'")

    switch = start + timedelta(days=round(spec.mixed_fixed_years * 365.25))
    spread = spec.spread_bps / 10_000
    reprice_freq = spec.repricing_freq or spec.payment_freq
    pid = spec.id_prefix
    has_grace = spec.grace_years > 0 and spec.amortization != "bullet"
    amort_start = grace_end if has_grace else start

    # For bullet amortization, mixed is simpler: 2 bullets + 1 offset
    if spec.amortization == "bullet":
        rows = [
            _motor_row(
                f"{pid}_fixed", spec.side, "fixed_bullet", spec.notional,
                spec.fixed_rate, 0.0, start, switch,
                spec.daycount, spec.payment_freq, spec.currency,
            ),
            _motor_row(
                f"{pid}_var", spec.side, "variable_bullet", spec.notional,
                None, spread, switch, maturity,
                spec.daycount, spec.payment_freq, spec.currency,
                spec.variable_index, switch, reprice_freq, "float",
                spec.floor_rate, spec.cap_rate,
            ),
            _motor_row(
                f"{pid}_offset", "L" if spec.side == "A" else "A",
                "fixed_bullet", spec.notional,
                0.0, 0.0, switch - timedelta(days=1), switch,
                spec.daycount, spec.payment_freq, spec.currency,
            ),
        ]
        return rows

    # Amortization (linear or annuity) + mixed rate
    # Compute notional outstanding at switch under linear decay
    total_amort_days = (maturity - amort_start).days
    remaining_at_switch = (maturity - switch).days
    notional_at_switch = spec.notional * remaining_at_switch / total_amort_days if total_amort_days > 0 else 0.0

    amort_type = spec.amortization  # "linear" or "annuity"
    rows = []

    # 1) Grace period (if applicable)
    if has_grace:
        rows.append(_motor_row(
            f"{pid}_grace", spec.side, "fixed_bullet", spec.notional,
            spec.fixed_rate, 0.0, start, grace_end,
            spec.daycount, spec.payment_freq, spec.currency,
        ))

    # 2) Full amortization at fixed rate
    rows.append(_motor_row(
        f"{pid}_amort", spec.side, _sct("fixed", amort_type), spec.notional,
        spec.fixed_rate, 0.0, amort_start, maturity,
        spec.daycount, spec.payment_freq, spec.currency,
    ))

    # 3) Cancel fixed interest post-switch (liability)
    cancel_side = "L" if spec.side == "A" else "A"
    rows.append(_motor_row(
        f"{pid}_cancel", cancel_side, _sct("fixed", amort_type), notional_at_switch,
        spec.fixed_rate, 0.0, switch, maturity,
        spec.daycount, spec.payment_freq, spec.currency,
    ))

    # 4) Add variable interest post-switch
    rows.append(_motor_row(
        f"{pid}_var", spec.side, _sct("variable", amort_type), notional_at_switch,
        None, spread, switch, maturity,
        spec.daycount, spec.payment_freq, spec.currency,
        spec.variable_index, switch, reprice_freq, "float",
        spec.floor_rate, spec.cap_rate,
    ))

    # 5) Grace offset (cancel bullet principal)
    if has_grace:
        rows.append(_motor_row(
            f"{pid}_goffset", cancel_side, "fixed_bullet", spec.notional,
            0.0, 0.0, grace_end - timedelta(days=1), grace_end,
            spec.daycount, spec.payment_freq, spec.currency,
        ))

    return rows


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def decompose_loan(spec: LoanSpec) -> pd.DataFrame:
    """Convert a LoanSpec into a DataFrame of motor-compatible position rows.

    This is the single entry point. It dispatches to the appropriate
    internal function based on rate_type, amortization, and grace period.

    Returns a DataFrame with the same schema as the motor expects
    (contract_id, side, source_contract_type, notional, ...).
    """
    start, grace_end, maturity = _resolve_dates(spec)

    if spec.rate_type == "mixed":
        rows = _decompose_mixed(spec, start, grace_end, maturity)
    elif spec.rate_type == "variable":
        rows = _decompose_simple(spec, "variable", start, grace_end, maturity)
    else:
        rows = _decompose_simple(spec, "fixed", start, grace_end, maturity)

    return pd.DataFrame(rows)
