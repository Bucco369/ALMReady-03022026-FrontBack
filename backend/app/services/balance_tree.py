"""Balance summary tree construction from canonical position rows.

Supports both DataFrame (ZIP path, vectorized) and list-of-dicts (Excel path, legacy).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.config import ASSET_SUBCATEGORY_ORDER, LIABILITY_SUBCATEGORY_ORDER
from app.schemas import (
    BalanceSummaryTree,
    BalanceTreeCategory,
    BalanceTreeNode,
)
from app.parsers.transforms import (
    _to_float,
    _weighted_avg_maturity,
    _weighted_avg_rate,
)


# ── Subcategory sorting ─────────────────────────────────────────────────────

def _subcategory_sort_key(side: str, subcategory_id: str, label: str, amount: float) -> tuple[int, float, str]:
    """Sort key: schema-defined order for assets/liabilities, by-amount fallback."""
    if side == "asset" and subcategory_id in ASSET_SUBCATEGORY_ORDER:
        return (0, ASSET_SUBCATEGORY_ORDER.index(subcategory_id), label)
    if side == "liability" and subcategory_id in LIABILITY_SUBCATEGORY_ORDER:
        return (0, LIABILITY_SUBCATEGORY_ORDER.index(subcategory_id), label)
    # Equity, derivatives, and unrecognized subcategories: sort by amount desc
    return (1, -amount, label)


# ── Vectorized weighted average helper ────────────────────────────────────────

def _weighted_avg_series(
    values: pd.Series, weights: pd.Series,
) -> float | None:
    """Weighted average from pandas Series, using abs(weight)."""
    mask = values.notna() & weights.notna() & (weights != 0)
    if not mask.any():
        return None
    v = values[mask].astype(float)
    w = weights[mask].astype(float).abs()
    total_w = w.sum()
    if total_w == 0:
        return None
    return float((v * w).sum() / total_w)


# ── DataFrame-based tree building (ZIP path) ─────────────────────────────────

def _build_category_tree_df(
    df: pd.DataFrame, side: str, label: str, cat_id: str,
) -> BalanceTreeCategory | None:
    """Build a category subtree for one side using vectorized groupby."""
    # Scope to this side
    side_mask = df["side"] == side
    include_mask = df["include_in_balance_tree"].astype(bool)

    scoped = df.loc[side_mask & include_mask]
    if scoped.empty and side in {"equity", "derivative"}:
        scoped = df.loc[side_mask]
    if scoped.empty:
        return None

    # Ensure numeric types for aggregation
    amounts = pd.to_numeric(scoped["amount"], errors="coerce").fillna(0.0)
    rates = pd.to_numeric(scoped["rate_display"], errors="coerce")
    maturities = pd.to_numeric(scoped["maturity_years"], errors="coerce")
    abs_amounts = amounts.abs()

    # Build a working frame for groupby
    work = pd.DataFrame({
        "subcategory_id": scoped["subcategory_id"].fillna("unknown").astype(str),
        "subcategoria_ui": scoped["subcategoria_ui"].fillna("unknown").astype(str),
        "amount": amounts,
        "abs_amount": abs_amounts,
        "rate_x_weight": rates * abs_amounts,
        "rate_valid": rates.notna() & (amounts != 0),
        "mat_x_weight": maturities * abs_amounts,
        "mat_valid": maturities.notna() & (amounts != 0),
    }, index=scoped.index)

    grouped = work.groupby("subcategory_id", sort=False)

    subcategories: list[BalanceTreeNode] = []
    for sid, grp in grouped:
        total_amount = float(grp["amount"].sum())
        n_positions = len(grp)
        sub_label = grp["subcategoria_ui"].iloc[0]

        # Weighted average rate
        rate_mask = grp["rate_valid"]
        w_rate = grp.loc[rate_mask, "abs_amount"].sum()
        avg_rate = float(grp.loc[rate_mask, "rate_x_weight"].sum() / w_rate) if w_rate > 0 else None

        # Weighted average maturity
        mat_mask = grp["mat_valid"]
        w_mat = grp.loc[mat_mask, "abs_amount"].sum()
        avg_mat = float(grp.loc[mat_mask, "mat_x_weight"].sum() / w_mat) if w_mat > 0 else None

        subcategories.append(BalanceTreeNode(
            id=str(sid),
            label=sub_label,
            amount=total_amount,
            positions=n_positions,
            avg_rate=avg_rate,
            avg_maturity=avg_mat,
        ))

    subcategories.sort(
        key=lambda node: _subcategory_sort_key(side, node.id, node.label, node.amount),
    )

    cat_amount = float(sum(n.amount for n in subcategories))
    cat_positions = int(sum(n.positions for n in subcategories))

    # Category-level weighted averages
    cat_avg_rate = _weighted_avg_series(rates, amounts)
    cat_avg_mat = _weighted_avg_series(maturities, amounts)

    return BalanceTreeCategory(
        id=cat_id,
        label=label,
        amount=cat_amount,
        positions=cat_positions,
        avg_rate=cat_avg_rate,
        avg_maturity=cat_avg_mat,
        subcategories=subcategories,
    )


def _build_summary_tree_df(canonical_df: pd.DataFrame) -> BalanceSummaryTree:
    """Build the full summary tree from a canonical DataFrame (one groupby pass)."""
    return BalanceSummaryTree(
        assets=_build_category_tree_df(canonical_df, side="asset", label="Assets", cat_id="assets"),
        liabilities=_build_category_tree_df(canonical_df, side="liability", label="Liabilities", cat_id="liabilities"),
        equity=_build_category_tree_df(canonical_df, side="equity", label="Equity", cat_id="equity"),
        derivatives=_build_category_tree_df(canonical_df, side="derivative", label="Derivatives", cat_id="derivatives"),
    )


# ── Dict-based tree building (Excel path, backward compat) ───────────────────

def _build_category_tree(
    rows: list[dict[str, Any]], side: str, label: str, cat_id: str,
) -> BalanceTreeCategory | None:
    """Build a category subtree for one side (asset/liability/equity/derivative)."""
    scoped = [r for r in rows if r.get("side") == side and r.get("include_in_balance_tree")]
    if not scoped:
        # For equity/derivatives, also try without include_in_balance_tree filter
        if side in {"equity", "derivative"}:
            scoped = [r for r in rows if r.get("side") == side]
        if not scoped:
            return None

    grouped: dict[str, list[dict[str, Any]]] = {}
    labels: dict[str, str] = {}

    for row in scoped:
        sid = str(row.get("subcategory_id") or "unknown")
        grouped.setdefault(sid, []).append(row)
        labels[sid] = str(row.get("subcategoria_ui") or sid)

    subcategories: list[BalanceTreeNode] = []
    for sid, sub_rows in grouped.items():
        amount = float(sum((_to_float(r.get("amount")) or 0.0) for r in sub_rows))
        subcategories.append(
            BalanceTreeNode(
                id=sid,
                label=labels.get(sid, sid),
                amount=amount,
                positions=len(sub_rows),
                avg_rate=_weighted_avg_rate(sub_rows),
                avg_maturity=_weighted_avg_maturity(sub_rows),
            )
        )

    subcategories = sorted(
        subcategories,
        key=lambda node: _subcategory_sort_key(side, node.id, node.label, node.amount),
    )

    amount = float(sum(node.amount for node in subcategories))
    positions = int(sum(node.positions for node in subcategories))

    return BalanceTreeCategory(
        id=cat_id,
        label=label,
        amount=amount,
        positions=positions,
        avg_rate=_weighted_avg_rate(scoped),
        avg_maturity=_weighted_avg_maturity(scoped),
        subcategories=subcategories,
    )


def _build_summary_tree(rows: list[dict[str, Any]]) -> BalanceSummaryTree:
    """Build summary tree from list-of-dicts (Excel path / lazy rebuild)."""
    return BalanceSummaryTree(
        assets=_build_category_tree(rows, side="asset", label="Assets", cat_id="assets"),
        liabilities=_build_category_tree(rows, side="liability", label="Liabilities", cat_id="liabilities"),
        equity=_build_category_tree(rows, side="equity", label="Equity", cat_id="equity"),
        derivatives=_build_category_tree(rows, side="derivative", label="Derivatives", cat_id="derivatives"),
    )
