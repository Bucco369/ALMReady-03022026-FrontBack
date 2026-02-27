"""Backward-compat shim — all logic moved to app.services.balance_tree."""

from app.services.balance_tree import (  # noqa: F401
    _build_category_tree,
    _build_category_tree_df,
    _build_summary_tree,
    _build_summary_tree_df,
    _subcategory_sort_key,
    _weighted_avg_series,
)
