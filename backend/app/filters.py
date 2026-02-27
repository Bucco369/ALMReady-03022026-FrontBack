"""Backward-compat shim — all logic moved to app.services.balance_query."""

from app.services.balance_query import (  # noqa: F401
    _aggregate_groups,
    _aggregate_groups_df,
    _aggregate_totals,
    _aggregate_totals_df,
    _apply_filters,
    _apply_filters_df,
    _build_facets,
    _build_facets_df,
    _matches_multi,
    _matches_subcategory,
    _normalize_category_filter,
    _split_csv_values,
)
