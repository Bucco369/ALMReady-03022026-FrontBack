"""Filtering, faceting, and aggregation for balance details/contracts."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.schemas import (
    BalanceDetailsFacets,
    BalanceDetailsGroup,
    BalanceDetailsTotals,
    FacetOption,
)
from app.parsers.transforms import _to_float, _to_subcategory_id, _to_text


# ═══════════════════════════════════════════════════════════════════════════════
# Legacy list-of-dicts helpers (kept for backward compat with calculate.py)
# ═══════════════════════════════════════════════════════════════════════════════

def _split_csv_values(raw: str | None) -> set[str]:
    if raw is None:
        return set()
    values = []
    for token in raw.split(","):
        cleaned = token.strip()
        if cleaned:
            values.append(cleaned.lower())
    return set(values)


def _normalize_category_filter(raw: str | None) -> set[str]:
    values = _split_csv_values(raw)
    out: set[str] = set()
    for value in values:
        if value in {"assets", "asset"}:
            out.add("asset")
        elif value in {"liabilities", "liability"}:
            out.add("liability")
        elif value in {"equity"}:
            out.add("equity")
        elif value in {"derivatives", "derivative"}:
            out.add("derivative")
    return out


def _matches_multi(value: str | None, allowed: set[str]) -> bool:
    if not allowed:
        return True
    if value is None:
        return False
    return value.lower() in allowed


def _matches_subcategory(row: dict[str, Any], subcategoria_ui: str | None, subcategory_id: str | None) -> bool:
    if not subcategoria_ui and not subcategory_id:
        return True

    row_id = str(row.get("subcategory_id") or "").lower()
    row_label = str(row.get("subcategoria_ui") or "").lower()

    if subcategory_id and row_id != subcategory_id.strip().lower():
        return False

    if subcategoria_ui:
        wanted = subcategoria_ui.strip().lower()
        if row_label != wanted and row_id != _to_subcategory_id(subcategoria_ui, "").lower():
            return False

    return True


def _apply_filters(
    rows: list[dict[str, Any]],
    *,
    categoria_ui: str | None = None,
    subcategoria_ui: str | None = None,
    subcategory_id: str | None = None,
    group: str | None = None,
    currency: str | None = None,
    rate_type: str | None = None,
    counterparty: str | None = None,
    maturity: str | None = None,
    query_text: str | None = None,
) -> list[dict[str, Any]]:
    category_filter = _normalize_category_filter(categoria_ui)
    currency_filter = _split_csv_values(currency)
    rate_filter = _split_csv_values(rate_type)
    counterparty_filter = _split_csv_values(counterparty)
    maturity_filter = _split_csv_values(maturity)
    group_filter = _split_csv_values(group)

    query_norm = (query_text or "").strip().lower()

    filtered: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("include_in_balance_tree"):
            continue

        side = str(row.get("side") or "").lower()
        if category_filter and side not in category_filter:
            continue

        if not _matches_subcategory(row, subcategoria_ui, subcategory_id):
            continue

        row_group = _to_text(row.get("group"))
        if not _matches_multi(row_group, group_filter):
            continue

        row_currency = _to_text(row.get("currency"))
        if not _matches_multi(row_currency, currency_filter):
            continue

        row_rate_type = _to_text(row.get("rate_type"))
        if not _matches_multi(row_rate_type, rate_filter):
            continue

        row_counterparty = _to_text(row.get("counterparty"))
        if not _matches_multi(row_counterparty, counterparty_filter):
            continue

        row_maturity = _to_text(row.get("maturity_bucket"))
        if not _matches_multi(row_maturity, maturity_filter):
            continue

        if query_norm:
            contract_id = str(row.get("contract_id") or "").lower()
            sheet_name = str(row.get("sheet") or "").lower()
            group_name = str(row.get("group") or "").lower()
            if query_norm not in contract_id and query_norm not in sheet_name and query_norm not in group_name:
                continue

        filtered.append(row)

    return filtered


def _build_facets(rows: list[dict[str, Any]]) -> BalanceDetailsFacets:
    def count_values(field: str) -> list[FacetOption]:
        counts: dict[str, int] = {}
        for row in rows:
            value = _to_text(row.get(field))
            if value is None:
                continue
            counts[value] = counts.get(value, 0) + 1
        return [FacetOption(value=k, count=v) for k, v in sorted(counts.items(), key=lambda item: item[0].lower())]

    return BalanceDetailsFacets(
        currencies=count_values("currency"),
        rate_types=count_values("rate_type"),
        counterparties=count_values("counterparty"),
        maturities=count_values("maturity_bucket"),
    )


def _aggregate_groups(rows: list[dict[str, Any]]) -> list[BalanceDetailsGroup]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grp = _to_text(row.get("group")) or "Ungrouped"
        grouped.setdefault(grp, []).append(row)

    from app.parsers.transforms import _weighted_avg_maturity, _weighted_avg_rate

    items: list[BalanceDetailsGroup] = []
    for grp, group_rows in grouped.items():
        amount = float(sum((_to_float(r.get("amount")) or 0.0) for r in group_rows))
        items.append(
            BalanceDetailsGroup(
                group=grp,
                amount=amount,
                positions=len(group_rows),
                avg_rate=_weighted_avg_rate(group_rows),
                avg_maturity=_weighted_avg_maturity(group_rows),
            )
        )

    return sorted(items, key=lambda x: x.amount, reverse=True)


def _aggregate_totals(rows: list[dict[str, Any]]) -> BalanceDetailsTotals:
    from app.parsers.transforms import _weighted_avg_maturity, _weighted_avg_rate

    return BalanceDetailsTotals(
        amount=float(sum((_to_float(r.get("amount")) or 0.0) for r in rows)),
        positions=len(rows),
        avg_rate=_weighted_avg_rate(rows),
        avg_maturity=_weighted_avg_maturity(rows),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Vectorized DataFrame versions (Steps 2 + 4)
# ═══════════════════════════════════════════════════════════════════════════════


def _apply_filters_df(
    df: pd.DataFrame,
    *,
    categoria_ui: str | None = None,
    subcategoria_ui: str | None = None,
    subcategory_id: str | None = None,
    group: str | None = None,
    currency: str | None = None,
    rate_type: str | None = None,
    counterparty: str | None = None,
    maturity: str | None = None,
    query_text: str | None = None,
) -> pd.DataFrame:
    """Vectorized filtering — replaces per-row Python loop."""
    mask = df["include_in_balance_tree"].fillna(False).astype(bool)

    # Category (side) filter
    if categoria_ui:
        category_filter = _normalize_category_filter(categoria_ui)
        if category_filter:
            mask = mask & df["side"].fillna("").str.lower().isin(category_filter)

    # Subcategory ID filter
    if subcategory_id:
        sid_lower = subcategory_id.strip().lower()
        mask = mask & (df["subcategory_id"].fillna("").str.lower() == sid_lower)

    # Subcategoria UI filter (label match OR slug match)
    if subcategoria_ui:
        wanted = subcategoria_ui.strip().lower()
        slug = _to_subcategory_id(subcategoria_ui, "").lower()
        label_col = df["subcategoria_ui"].fillna("").str.lower()
        id_col = df["subcategory_id"].fillna("").str.lower()
        mask = mask & ((label_col == wanted) | (id_col == slug))

    # Group filter
    if group:
        group_filter = _split_csv_values(group)
        if group_filter:
            mask = mask & df["group"].fillna("").str.lower().isin(group_filter)

    # Currency filter
    if currency:
        currency_filter = _split_csv_values(currency)
        if currency_filter:
            mask = mask & df["currency"].fillna("").str.lower().isin(currency_filter)

    # Rate type filter
    if rate_type:
        rate_filter = _split_csv_values(rate_type)
        if rate_filter:
            mask = mask & df["rate_type"].fillna("").str.lower().isin(rate_filter)

    # Counterparty filter
    if counterparty:
        counterparty_filter = _split_csv_values(counterparty)
        if counterparty_filter:
            mask = mask & df["counterparty"].fillna("").str.lower().isin(counterparty_filter)

    # Maturity bucket filter
    if maturity:
        maturity_filter = _split_csv_values(maturity)
        if maturity_filter:
            mask = mask & df["maturity_bucket"].fillna("").str.lower().isin(maturity_filter)

    # Free-text search across contract_id, sheet, group
    if query_text:
        query_norm = query_text.strip().lower()
        if query_norm:
            text_match = (
                df["contract_id"].fillna("").str.lower().str.contains(query_norm, regex=False)
                | df["sheet"].fillna("").str.lower().str.contains(query_norm, regex=False)
                | df["group"].fillna("").str.lower().str.contains(query_norm, regex=False)
            )
            mask = mask & text_match

    return df.loc[mask]


def _build_facets_df(df: pd.DataFrame) -> BalanceDetailsFacets:
    """Vectorized facet counting using value_counts."""
    def count_values(col: str) -> list[FacetOption]:
        s = df[col].dropna()
        if s.empty:
            return []
        counts = s.value_counts()
        sorted_keys = sorted(counts.index, key=lambda x: str(x).lower())
        return [FacetOption(value=str(k), count=int(counts[k])) for k in sorted_keys]

    return BalanceDetailsFacets(
        currencies=count_values("currency"),
        rate_types=count_values("rate_type"),
        counterparties=count_values("counterparty"),
        maturities=count_values("maturity_bucket"),
    )


def _aggregate_groups_df(df: pd.DataFrame) -> list[BalanceDetailsGroup]:
    """Vectorized group aggregation using groupby."""
    if df.empty:
        return []

    grp_col = df["group"].fillna("Ungrouped")
    amounts = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    rates = pd.to_numeric(df["rate_display"], errors="coerce")
    maturities = pd.to_numeric(df["maturity_years"], errors="coerce")
    abs_amounts = amounts.abs()

    work = pd.DataFrame({
        "group": grp_col.values,
        "amount": amounts.values,
        "abs_amount": abs_amounts.values,
        "rate_x_weight": (rates * abs_amounts).values,
        "rate_valid": (rates.notna() & (amounts != 0)).values,
        "mat_x_weight": (maturities * abs_amounts).values,
        "mat_valid": (maturities.notna() & (amounts != 0)).values,
    })

    items: list[BalanceDetailsGroup] = []
    for grp_name, g in work.groupby("group", sort=False):
        total_amount = float(g["amount"].sum())
        n_positions = len(g)

        rate_mask = g["rate_valid"]
        w_rate = float(g.loc[rate_mask, "abs_amount"].sum())
        avg_rate = float(g.loc[rate_mask, "rate_x_weight"].sum() / w_rate) if w_rate > 0 else None

        mat_mask = g["mat_valid"]
        w_mat = float(g.loc[mat_mask, "abs_amount"].sum())
        avg_mat = float(g.loc[mat_mask, "mat_x_weight"].sum() / w_mat) if w_mat > 0 else None

        items.append(BalanceDetailsGroup(
            group=str(grp_name),
            amount=total_amount,
            positions=n_positions,
            avg_rate=avg_rate,
            avg_maturity=avg_mat,
        ))

    return sorted(items, key=lambda x: x.amount, reverse=True)


def _aggregate_totals_df(df: pd.DataFrame) -> BalanceDetailsTotals:
    """Vectorized total aggregation."""
    if df.empty:
        return BalanceDetailsTotals(amount=0.0, positions=0)

    amounts = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    rates = pd.to_numeric(df["rate_display"], errors="coerce")
    maturities = pd.to_numeric(df["maturity_years"], errors="coerce")
    abs_amounts = amounts.abs()

    total_amount = float(amounts.sum())
    n_positions = len(df)

    rate_mask = rates.notna() & (amounts != 0)
    w_rate = float(abs_amounts[rate_mask].sum())
    avg_rate = float((rates[rate_mask] * abs_amounts[rate_mask]).sum() / w_rate) if w_rate > 0 else None

    mat_mask = maturities.notna() & (amounts != 0)
    w_mat = float(abs_amounts[mat_mask].sum())
    avg_mat = float((maturities[mat_mask] * abs_amounts[mat_mask]).sum() / w_mat) if w_mat > 0 else None

    return BalanceDetailsTotals(
        amount=total_amount,
        positions=n_positions,
        avg_rate=avg_rate,
        avg_maturity=avg_mat,
    )
