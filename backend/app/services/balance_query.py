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

    # Build segment tree
    segment_tree: dict[str, list[FacetOption]] = {}
    tree_counts: dict[str, dict[str, int]] = {}
    for row in rows:
        parent = _to_text(row.get("business_segment"))
        child = _to_text(row.get("strategic_segment"))
        if parent:
            if parent not in tree_counts:
                tree_counts[parent] = {}
            if child:
                tree_counts[parent][child] = tree_counts[parent].get(child, 0) + 1
    for parent, children in sorted(tree_counts.items()):
        segment_tree[parent] = [
            FacetOption(value=k, count=v) for k, v in sorted(children.items(), key=lambda x: x[0].lower())
        ]

    return BalanceDetailsFacets(
        currencies=count_values("currency"),
        rate_types=count_values("rate_type"),
        segments=count_values("business_segment"),
        strategic_segments=count_values("strategic_segment"),
        segment_tree=segment_tree,
        maturities=count_values("maturity_bucket"),
        remunerations=count_values("remuneration_bucket"),
        book_values=count_values("book_value_def"),
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
    segment: str | None = None,
    strategic_segment: str | None = None,
    maturity: str | None = None,
    remuneration: str | None = None,
    book_value: str | None = None,
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

    # Counterparty filter (legacy — kept for backward compat)
    if counterparty:
        counterparty_filter = _split_csv_values(counterparty)
        if counterparty_filter:
            mask = mask & df["counterparty"].fillna("").str.lower().isin(counterparty_filter)

    # Business segment filter
    if segment and "business_segment" in df.columns:
        segment_filter = _split_csv_values(segment)
        if segment_filter:
            mask = mask & df["business_segment"].fillna("").str.lower().isin(segment_filter)

    # Strategic segment filter
    if strategic_segment and "strategic_segment" in df.columns:
        strategic_filter = _split_csv_values(strategic_segment)
        if strategic_filter:
            mask = mask & df["strategic_segment"].fillna("").str.lower().isin(strategic_filter)

    # Maturity bucket filter
    if maturity:
        maturity_filter = _split_csv_values(maturity)
        if maturity_filter:
            mask = mask & df["maturity_bucket"].fillna("").str.lower().isin(maturity_filter)

    # Remuneration bucket filter
    if remuneration and "remuneration_bucket" in df.columns:
        remuneration_filter = _split_csv_values(remuneration)
        if remuneration_filter:
            mask = mask & df["remuneration_bucket"].fillna("").str.lower().isin(remuneration_filter)

    # Book value definition filter
    if book_value and "book_value_def" in df.columns:
        book_value_filter = _split_csv_values(book_value)
        if book_value_filter:
            mask = mask & df["book_value_def"].fillna("").str.lower().isin(book_value_filter)

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
        if col not in df.columns:
            return []
        s = df[col].dropna()
        if s.empty:
            return []
        counts = s.value_counts()
        sorted_keys = sorted(counts.index, key=lambda x: str(x).lower())
        return [FacetOption(value=str(k), count=int(counts[k])) for k in sorted_keys]

    # Build segment tree: business_segment → list of strategic_segment facets
    segment_tree: dict[str, list[FacetOption]] = {}
    if "business_segment" in df.columns and "strategic_segment" in df.columns:
        valid = df[["business_segment", "strategic_segment"]].dropna(subset=["business_segment"])
        if not valid.empty:
            for parent, group in valid.groupby("business_segment"):
                child_counts = group["strategic_segment"].dropna().value_counts()
                sorted_keys = sorted(child_counts.index, key=lambda x: str(x).lower())
                segment_tree[str(parent)] = [
                    FacetOption(value=str(k), count=int(child_counts[k])) for k in sorted_keys
                ]

    return BalanceDetailsFacets(
        currencies=count_values("currency"),
        rate_types=count_values("rate_type"),
        segments=count_values("business_segment"),
        strategic_segments=count_values("strategic_segment"),
        segment_tree=segment_tree,
        maturities=count_values("maturity_bucket"),
        remunerations=count_values("remuneration_bucket"),
        book_values=count_values("book_value_def"),
    )


def _build_cross_filtered_facets_df(
    context_df: pd.DataFrame,
    *,
    currency: str | None = None,
    rate_type: str | None = None,
    segment: str | None = None,
    strategic_segment: str | None = None,
    maturity: str | None = None,
    remuneration: str | None = None,
    book_value: str | None = None,
) -> BalanceDetailsFacets:
    """Cross-filtered facets: each dimension's counts reflect all OTHER active filters.

    For example, when the user selects "EUR" in Currency and "<1Y" in Maturity:
    - Currency facets show counts filtered by maturity=<1Y only (not by currency)
    - Maturity facets show counts filtered by currency=EUR only (not by maturity)
    - Segment facets show counts filtered by currency=EUR AND maturity=<1Y

    This lets the user multi-select within any dimension while seeing accurate
    counts that reflect how the other active filters narrow the data.
    """

    # ── Precompute boolean mask per dimension (each ~5ms on 1.5M rows) ───
    _DIMS: list[tuple[str, str | None, str]] = [
        # (mask_key, filter_value, df_column)
        ("currency", currency, "currency"),
        ("rate_type", rate_type, "rate_type"),
        ("segment", segment, "business_segment"),
        ("strategic_segment", strategic_segment, "strategic_segment"),
        ("maturity", maturity, "maturity_bucket"),
        ("remuneration", remuneration, "remuneration_bucket"),
        ("book_value", book_value, "book_value_def"),
    ]

    masks: dict[str, pd.Series] = {}
    for key, filt_val, col in _DIMS:
        if filt_val and col in context_df.columns:
            filt_set = _split_csv_values(filt_val)
            if filt_set:
                masks[key] = context_df[col].fillna("").str.lower().isin(filt_set)

    def _combined_mask_excluding(*exclude_keys: str) -> pd.Series | None:
        """AND all masks EXCEPT the given keys."""
        parts = [m for k, m in masks.items() if k not in exclude_keys]
        if not parts:
            return None
        result = parts[0]
        for p in parts[1:]:
            result = result & p
        return result

    def _count_for(col: str, *exclude_keys: str) -> list[FacetOption]:
        if col not in context_df.columns:
            return []
        mask = _combined_mask_excluding(*exclude_keys)
        s = context_df.loc[mask, col].dropna() if mask is not None else context_df[col].dropna()
        if s.empty:
            return []
        counts = s.value_counts()
        sorted_keys = sorted(counts.index, key=lambda x: str(x).lower())
        return [FacetOption(value=str(k), count=int(counts[k])) for k in sorted_keys]

    # Build segment tree with cross-filtering (exclude both segment dims)
    segment_tree: dict[str, list[FacetOption]] = {}
    if "business_segment" in context_df.columns and "strategic_segment" in context_df.columns:
        mask = _combined_mask_excluding("segment", "strategic_segment")
        subset = context_df if mask is None else context_df.loc[mask]
        valid = subset[["business_segment", "strategic_segment"]].dropna(subset=["business_segment"])
        if not valid.empty:
            for parent, group in valid.groupby("business_segment"):
                child_counts = group["strategic_segment"].dropna().value_counts()
                sorted_keys = sorted(child_counts.index, key=lambda x: str(x).lower())
                segment_tree[str(parent)] = [
                    FacetOption(value=str(k), count=int(child_counts[k])) for k in sorted_keys
                ]

    return BalanceDetailsFacets(
        currencies=_count_for("currency", "currency"),
        rate_types=_count_for("rate_type", "rate_type"),
        segments=_count_for("business_segment", "segment", "strategic_segment"),
        strategic_segments=_count_for("strategic_segment", "segment", "strategic_segment"),
        segment_tree=segment_tree,
        maturities=_count_for("maturity_bucket", "maturity"),
        remunerations=_count_for("remuneration_bucket", "remuneration"),
        book_values=_count_for("book_value_def", "book_value"),
    )


def _aggregate_groups_df(df: pd.DataFrame, group_by: list[str] | None = None) -> list[BalanceDetailsGroup]:
    """Vectorized group aggregation using groupby.

    When group_by is provided, groups by those columns instead of the default
    "group" column.  Multiple columns produce composite "A | B" labels.
    """
    if df.empty:
        return []

    if not group_by:
        group_by = ["group"]

    valid_cols = [c for c in group_by if c in df.columns]
    if not valid_cols:
        valid_cols = ["group"]

    if len(valid_cols) == 1:
        grp_col = df[valid_cols[0]].fillna("Ungrouped")
    else:
        grp_col = df[valid_cols].fillna("—").apply(
            lambda row: " | ".join(str(v) for v in row), axis=1
        )
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
