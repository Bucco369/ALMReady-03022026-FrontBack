"""
Balance position classifier.

Maps raw bank data (Apartado, Producto, etc.) to canonical balance
subcategories defined in schema.py.

Classification logic:
  1. Determine side from ``apartado`` (A/P/AFB/PFB), fallback to motor side.
  2. Match ``producto`` against keyword rules (first match wins).
  3. Fallback to default subcategory if no rule matches.

Each client provides rules via balance_config/clients/<client>.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from engine.balance_config.schema import (
    ASSET_DEFAULT,
    LIABILITY_DEFAULT,
    SUBCATEGORY_LABELS,
)


@dataclass(frozen=True)
class ClassificationResult:
    """Output of classify_position()."""
    side: str               # "asset" | "liability" | "derivative"
    subcategory_id: str     # e.g. "mortgages", "deposits"
    subcategory_label: str  # e.g. "Mortgages", "Deposits"


# ── Side resolution ───────────────────────────────────────────────────────

_APARTADO_SIDE = {
    "A": "asset",
    "P": "liability",
    "AFB": "derivative",
    "PFB": "derivative",
}


def _side_from_apartado(apartado: str | None) -> str | None:
    """Map Apartado column (A/P/AFB/PFB) to canonical side."""
    if not apartado:
        return None
    return _APARTADO_SIDE.get(apartado.strip().upper())


def _side_from_motor(raw_side: str | None) -> str:
    """Map motor side (A/L) to canonical side. Fallback = asset."""
    if not raw_side:
        return "asset"
    return "liability" if raw_side.strip().upper() == "L" else "asset"


# ── Keyword matching ──────────────────────────────────────────────────────

def _match_rules(
    producto_upper: str,
    rules: Sequence[tuple[str, str]],
) -> str | None:
    """Return the subcategory_id of the first matching rule, or None."""
    for keyword, subcategory_id in rules:
        if keyword.upper() in producto_upper:
            return subcategory_id
    return None


# ── Public API ────────────────────────────────────────────────────────────

def classify_position(
    *,
    apartado: str | None = None,
    producto: str | None = None,
    motor_side: str | None = None,
    asset_rules: Sequence[tuple[str, str]] = (),
    liability_rules: Sequence[tuple[str, str]] = (),
    derivative_rules: Sequence[tuple[str, str]] = (),
) -> ClassificationResult:
    """
    Classify a single position into the balance tree.

    Parameters
    ----------
    apartado : str | None
        Value of the bank's ``Apartado`` column (A/P/AFB/PFB).
    producto : str | None
        Value of the bank's ``Producto`` column (free-text product name).
    motor_side : str | None
        Motor canonical side ("A" or "L"). Used as fallback when apartado
        is not available.
    asset_rules / liability_rules / derivative_rules
        Keyword rules from the client config.  Each is a sequence of
        ``(keyword, subcategory_id)`` tuples evaluated in order.

    Returns
    -------
    ClassificationResult with side, subcategory_id, subcategory_label.
    """
    # 1. Determine side
    side = _side_from_apartado(apartado) or _side_from_motor(motor_side)

    # 2. Match producto against rules for the resolved side
    subcategory_id: str | None = None
    if producto:
        prod_upper = producto.strip().upper()
        if side == "asset":
            subcategory_id = _match_rules(prod_upper, asset_rules)
        elif side == "liability":
            subcategory_id = _match_rules(prod_upper, liability_rules)
        elif side == "derivative":
            subcategory_id = _match_rules(prod_upper, derivative_rules)

    # 3. Fallback
    if subcategory_id is None:
        if side == "derivative":
            subcategory_id = "derivatives"
        elif side == "liability":
            subcategory_id = LIABILITY_DEFAULT
        else:
            subcategory_id = ASSET_DEFAULT

    # 4. Resolve label
    label = SUBCATEGORY_LABELS.get(
        subcategory_id,
        subcategory_id.replace("-", " ").title(),
    )

    return ClassificationResult(
        side=side,
        subcategory_id=subcategory_id,
        subcategory_label=label,
    )
