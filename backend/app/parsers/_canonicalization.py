"""Position canonicalization: Excel rows, motor rows, and vectorised motor DataFrames."""

from __future__ import annotations

import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Sequence

import numpy as np
import pandas as pd

from app.config import _BC_SIDE_UI, _bc_classify
from engine.balance_config.classifier import _APARTADO_SIDE
from engine.balance_config.schema import (
    ASSET_DEFAULT,
    LIABILITY_DEFAULT,
    SUBCATEGORY_LABELS,
)
from app.parsers.transforms import (
    _bucket_from_years,
    _maturity_years,
    _norm_key,
    _normalize_categoria_ui,
    _normalize_rate_type,
    _normalize_side,
    _slugify,
    _to_float,
    _to_iso_date,
    _to_subcategory_id,
    _to_text,
)

_log = logging.getLogger(__name__)


# ── Remuneration bucketing ────────────────────────────────────────────────────

def _remuneration_bucket(rate: float | None) -> str:
    """Bucket a display rate (already in percentage points, e.g. 3.5 = 3.5%) into ranges."""
    if rate is None:
        return "-"
    try:
        import math
        if math.isnan(rate):
            return "-"
    except (TypeError, ValueError):
        return "-"
    r = abs(rate)
    if r == 0:
        return "0%"
    if r <= 1:
        return "0-1%"
    if r <= 2:
        return "1-2%"
    if r <= 3:
        return "2-3%"
    if r <= 4:
        return "3-4%"
    if r <= 5:
        return "4-5%"
    return "5%+"


# ── Excel position canonicalization ──────────────────────────────────────────

def _canonicalize_position_row(sheet_name: str, record: dict[str, Any], idx: int) -> dict[str, Any]:
    lookup = {_norm_key(k): k for k in record.keys()}

    def get(col: str) -> Any:
        key = lookup.get(col)
        if key is None:
            return None
        return record.get(key)

    contract_id = _to_text(get("num_sec_ac")) or f"{_slugify(sheet_name)}-{idx + 1}"
    side = _normalize_side(_to_text(get("lado_balance")), sheet_name)

    categoria_ui = _normalize_categoria_ui(_to_text(get("categoria_ui")), side)
    subcategoria_ui = _to_text(get("subcategoria_ui")) or sheet_name
    subcategory_id = _to_subcategory_id(subcategoria_ui, sheet_name)

    amount = _to_float(get("saldo_ini"))
    if amount is None:
        amount = 0.0

    book_value = _to_float(get("book_value"))
    tasa_fija = _to_float(get("tasa_fija"))

    tipo_tasa = _to_text(get("tipo_tasa"))
    rate_type = _normalize_rate_type(tipo_tasa)
    rate_display_val = tasa_fija

    fecha_inicio = _to_iso_date(get("fecha_inicio"))
    fecha_vencimiento = _to_iso_date(get("fecha_vencimiento"))
    fecha_prox_reprecio = _to_iso_date(get("fecha_prox_reprecio"))

    core_avg_maturity = _to_float(get("core_avg_maturity_y"))
    maturity_years_val = _maturity_years(fecha_vencimiento, core_avg_maturity)

    explicit_bucket = _to_text(get("bucket_vencimiento"))
    if explicit_bucket:
        maturity_bucket = explicit_bucket
    elif maturity_years_val is None:
        maturity_bucket = "-"
    else:
        maturity_bucket = _bucket_from_years(maturity_years_val)
    repricing_bucket = _to_text(get("bucket_reprecio"))

    return {
        "contract_id": contract_id,
        "sheet": sheet_name,
        "side": side,
        "categoria_ui": categoria_ui,
        "subcategoria_ui": subcategoria_ui,
        "subcategory_id": subcategory_id,
        "group": _to_text(get("grupo")),
        "currency": _to_text(get("moneda")),
        "counterparty": _to_text(get("contraparte")),
        "business_segment": _to_text(get("segmento_negocio")),
        "strategic_segment": _to_text(get("segmento_estrategico")),
        "book_value_def": _to_text(get("book_value_def")),
        "amount": amount,
        "book_value": book_value,
        "rate_type": rate_type,
        "rate_display": rate_display_val,
        "remuneration_bucket": _remuneration_bucket(rate_display_val),
        "tipo_tasa_raw": tipo_tasa,
        "tasa_fija": tasa_fija,
        "spread": _to_float(get("spread")),
        "indice_ref": _to_text(get("indice_ref")),
        "tenor_indice": _to_text(get("tenor_indice")),
        "fecha_inicio": fecha_inicio,
        "fecha_vencimiento": fecha_vencimiento,
        "fecha_prox_reprecio": fecha_prox_reprecio,
        "maturity_years": maturity_years_val,
        "maturity_bucket": maturity_bucket,
        "repricing_bucket": repricing_bucket,
        "include_in_balance_tree": side in {"asset", "liability"},
    }


# ── Motor row canonicalization (single-row, used as fallback) ────────────────

def _canonicalize_motor_row(
    record: dict[str, Any],
    idx: int,
    client_rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract_id = str(record.get("contract_id") or f"motor-{idx + 1}")
    source_contract_type = str(record.get("source_contract_type") or "unknown")
    raw_side = str(record.get("side") or "A").upper()

    rules = client_rules or {}
    cls = _bc_classify(
        apartado=_to_text(record.get("balance_section")),
        producto=_to_text(record.get("balance_product")),
        motor_side=raw_side,
        **rules,
    )
    side = cls.side
    categoria_ui = _BC_SIDE_UI.get(side, "Assets")
    subcategoria_ui = cls.subcategory_label
    subcategory_id = cls.subcategory_id

    amount = _to_float(record.get("notional")) or 0.0

    rate_type_raw = str(record.get("rate_type") or "")
    rate_type = (
        "Fixed" if rate_type_raw == "fixed"
        else "Floating" if rate_type_raw == "float"
        else None
    )
    fixed_rate = _to_float(record.get("fixed_rate"))
    spread_val = _to_float(record.get("spread"))
    rate_display_val = fixed_rate

    fecha_inicio = _to_iso_date(record.get("start_date"))
    fecha_vencimiento = _to_iso_date(record.get("maturity_date"))
    fecha_prox_reprecio = _to_iso_date(record.get("next_reprice_date"))

    mat_years = _maturity_years(fecha_vencimiento, None)
    is_non_maturity = "non_maturity" in source_contract_type
    if is_non_maturity:
        mat_years = 0.0

    if is_non_maturity:
        maturity_bucket = "-"
    else:
        maturity_bucket = _bucket_from_years(mat_years)

    return {
        "contract_id": contract_id,
        "sheet": source_contract_type,
        "side": side,
        "categoria_ui": categoria_ui,
        "subcategoria_ui": subcategoria_ui,
        "subcategory_id": subcategory_id,
        "group": subcategoria_ui,
        "currency": _to_text(record.get("original_currency")) or "EUR",
        "counterparty": None,
        "business_segment": _to_text(record.get("business_segment")),
        "strategic_segment": _to_text(record.get("strategic_segment")),
        "book_value_def": _to_text(record.get("book_value_def")),
        "amount": amount,
        "book_value": None,
        "rate_type": rate_type,
        "rate_display": rate_display_val,
        "remuneration_bucket": _remuneration_bucket(rate_display_val),
        "tipo_tasa_raw": rate_type_raw,
        "tasa_fija": fixed_rate,
        "spread": spread_val,
        "indice_ref": _to_text(record.get("index_name")),
        "tenor_indice": None,
        "fecha_inicio": fecha_inicio,
        "fecha_vencimiento": fecha_vencimiento,
        "fecha_prox_reprecio": fecha_prox_reprecio,
        "maturity_years": mat_years,
        "maturity_bucket": maturity_bucket,
        "repricing_bucket": None,
        "include_in_balance_tree": side in {"asset", "liability"},
        "source_contract_type": source_contract_type,
        "daycount_base": _to_text(record.get("daycount_base")),
        "notional": amount,
        "repricing_freq": _to_text(record.get("repricing_freq")),
        "payment_freq": _to_text(record.get("payment_freq")),
        "floor_rate": _to_float(record.get("floor_rate")),
        "cap_rate": _to_float(record.get("cap_rate")),
        "balance_product": _to_text(record.get("balance_product")),
        "balance_section": _to_text(record.get("balance_section")),
        "balance_epigrafe": _to_text(record.get("balance_epigrafe")),
    }


# ── Vectorised motor classification ──────────────────────────────────────────

def _classify_motor_df(
    motor_df: pd.DataFrame,
    client_rules: dict[str, Any],
) -> pd.DataFrame:
    """Vectorised balance classification using deduplicated (side, product) pairs.

    Instead of running ~70 rules against ~1.5M rows (= ~100M string scans),
    deduplicates to ~5K unique (side, product) pairs first, classifies those,
    then maps back.  This is ~300x fewer string comparisons.
    """
    n = len(motor_df)

    # Resolve side from apartado, fallback to motor side
    apartado = motor_df["balance_section"].fillna("").str.strip().str.upper() if "balance_section" in motor_df.columns else pd.Series("", index=motor_df.index)
    motor_side_raw = motor_df["side"].fillna("A").astype(str).str.upper()

    side_from_apart = apartado.map(_APARTADO_SIDE)
    side_from_motor = motor_side_raw.map({"A": "asset", "L": "liability"}).fillna("asset")
    side = side_from_apart.where(side_from_apart.notna(), side_from_motor)

    # Prepare producto for keyword matching
    producto = motor_df["balance_product"].fillna("").astype(str).str.upper() if "balance_product" in motor_df.columns else pd.Series("", index=motor_df.index)

    # ── Deduplicated classification ──────────────────────────────────────
    # Build a small DataFrame of unique (side, producto) combinations (~5K rows
    # vs ~1.5M), run rules against those, then map results back to all rows.
    combo = pd.DataFrame({"side": side.values, "producto": producto.values})
    unique_combos = combo.drop_duplicates()

    # Classify unique combos with first-match-wins semantics
    u_side = unique_combos["side"]
    u_prod = unique_combos["producto"]

    # Default subcategory per side
    defaults = {"asset": ASSET_DEFAULT, "liability": LIABILITY_DEFAULT, "derivative": "derivatives"}
    u_subcat = u_side.map(defaults).fillna(ASSET_DEFAULT)
    u_matched = pd.Series(False, index=unique_combos.index)

    all_rule_sets: list[tuple[str, Sequence[tuple[str, str]]]] = [
        ("asset", client_rules.get("asset_rules", ())),
        ("liability", client_rules.get("liability_rules", ())),
        ("derivative", client_rules.get("derivative_rules", ())),
    ]

    for target_side, rules in all_rule_sets:
        side_mask = u_side == target_side
        for keyword, sub_id in rules:
            rule_match = side_mask & ~u_matched & u_prod.str.contains(keyword.upper(), na=False, regex=False)
            u_subcat = u_subcat.where(~rule_match, sub_id)
            u_matched = u_matched | rule_match

    # Build lookup: (side, producto) → subcategory_id
    unique_combos = unique_combos.copy()
    unique_combos["_subcat"] = u_subcat.values
    # Create a composite key for fast mapping
    combo_key = side + "|" + producto
    unique_key = unique_combos["side"] + "|" + unique_combos["producto"]
    subcat_map = dict(zip(unique_key, unique_combos["_subcat"]))
    subcategory_id = combo_key.map(subcat_map)

    # Log classification coverage
    n_unmatched_unique = int((~u_matched).sum())
    if n_unmatched_unique > 0:
        n_unmatched = int(subcategory_id.isin({ASSET_DEFAULT, LIABILITY_DEFAULT}).sum())
        _log.warning(
            "Classification: %d/%d positions fell through to defaults (%.1f%%)",
            n_unmatched, n, n_unmatched / n * 100 if n > 0 else 0,
        )

    subcategory_label = subcategory_id.map(SUBCATEGORY_LABELS).fillna(
        subcategory_id.str.replace("-", " ").str.title()
    )

    return pd.DataFrame({
        "cls_side": side,
        "cls_subcategory_id": subcategory_id,
        "cls_subcategory_label": subcategory_label,
    }, index=motor_df.index)


# ── Vectorised motor canonicalization ────────────────────────────────────────

def _canonicalize_motor_df(
    motor_df: pd.DataFrame,
    client_rules: dict[str, Any],
) -> pd.DataFrame:
    """Vectorised version of _canonicalize_motor_row operating on the entire DataFrame.

    Returns a canonical DataFrame (not list-of-dicts) so downstream consumers
    (tree builder, persistence, sheet summaries) can use vectorized pandas ops
    instead of Python-level row iteration.

    Performance: exploits the fact that motor_df columns are already typed
    (dates as datetime64, numerics as float64) from the engine reader, avoiding
    redundant pd.to_datetime / pd.to_numeric calls.
    """
    n = len(motor_df)

    # Classification (uses deduplicated product matching)
    cls = _classify_motor_df(motor_df, client_rules)

    # ── Source contract type ──────────────────────────────────────────────
    sct = motor_df.get("source_contract_type")
    if sct is None:
        sct = pd.Series("unknown", index=motor_df.index)
    else:
        sct = sct.fillna("unknown")

    # ── Non-maturity mask ────────────────────────────────────────────────
    is_non_maturity = sct.str.contains("non_maturity", na=False, regex=False)

    # ── Contract ID (already string[python] from engine reader) ─────────
    if "contract_id" in motor_df.columns:
        cid = motor_df["contract_id"]
        needs_fill = cid.isna()
        if needs_fill.any():
            fill_ids = "motor-" + pd.RangeIndex(1, n + 1).astype(str)
            cid = cid.where(~needs_fill, pd.Series(fill_ids, index=motor_df.index))
    else:
        cid = "motor-" + pd.RangeIndex(1, n + 1).astype(str)

    # ── Amounts (already float64 from engine reader) ───────────────────
    notional = motor_df["notional"].fillna(0.0) if "notional" in motor_df.columns else pd.Series(0.0, index=motor_df.index)

    # ── Rate type ──────────────────────────────────────────────────────
    rate_type_raw = motor_df.get("rate_type", pd.Series("", index=motor_df.index))
    rate_type_raw = rate_type_raw.fillna("")
    rate_type = rate_type_raw.map({"fixed": "Fixed", "float": "Floating"})

    # ── Dates (already datetime64 from engine reader — NO re-parse) ────
    now = datetime.now(timezone.utc).date()

    def _get_dt(col: str) -> pd.Series:
        if col in motor_df.columns:
            s = motor_df[col]
            # If already datetime, use directly; otherwise parse (legacy path)
            if pd.api.types.is_datetime64_any_dtype(s):
                return s
            return pd.to_datetime(s, errors="coerce")
        return pd.Series(pd.NaT, index=motor_df.index)

    dt_start = _get_dt("start_date")
    dt_maturity = _get_dt("maturity_date")
    dt_reprice = _get_dt("next_reprice_date")

    # ── Maturity years (vectorised) ────────────────────────────────────
    mat_years = (dt_maturity - pd.Timestamp(now)).dt.days / 365.25
    mat_years = mat_years.where(mat_years >= 0, other=np.nan)
    mat_years = mat_years.where(dt_maturity.notna(), other=np.nan)
    mat_years = mat_years.where(~is_non_maturity, 0.0)

    # ── Maturity bucket (vectorised) ──────────────────────────────────
    maturity_bucket = pd.cut(
        mat_years,
        bins=[-np.inf, 1, 5, 10, 20, np.inf],
        labels=["<1Y", "1-5Y", "5-10Y", "10-20Y", ">20Y"],
        right=False,
    ).astype("object")
    maturity_bucket = maturity_bucket.where(mat_years.notna(), other=None)
    maturity_bucket = maturity_bucket.where(~is_non_maturity, "-")

    # ── Float columns (already float64 — skip pd.to_numeric) ──────────
    def _float_col(name: str) -> pd.Series:
        if name not in motor_df.columns:
            return pd.Series(np.nan, index=motor_df.index)
        s = motor_df[name]
        if pd.api.types.is_float_dtype(s):
            return s
        return pd.to_numeric(s, errors="coerce")

    # ── Text columns (single null-mask, no redundant astype) ──────────
    def _text_col(name: str) -> pd.Series:
        if name not in motor_df.columns:
            return pd.Series(None, index=motor_df.index, dtype="object")
        s = motor_df[name]
        null_mask = s.isna()
        # For object columns that are already strings, avoid .astype(str)
        if s.dtype == "object":
            str_s = s.str.strip()
        else:
            str_s = s.astype(str).str.strip()
        blank = null_mask | str_s.isin({"", "nan", "None", "<NA>"})
        return str_s.where(~blank, other=None)

    categoria_ui = cls["cls_side"].map(_BC_SIDE_UI).fillna("Assets")

    # ── Build canonical DataFrame ─────────────────────────────────────
    # Keep dates as datetime64 — Parquet serializes natively.
    # Only convert to ISO strings at JSON read time (_read_positions_file).
    # ── Remuneration bucket (vectorised) ──────────────────────────────
    rate_display = _float_col("fixed_rate")
    # Vectorised bucketing: map rate_display → bucket label
    # rate_display is in decimal form (0.035 = 3.5%) due to NUMERIC_SCALE_MAP,
    # so convert to percentage points before bucketing.
    abs_rate = rate_display.abs() * 100
    remuneration_bucket = pd.Series("-", index=motor_df.index, dtype="object")
    remuneration_bucket = remuneration_bucket.where(rate_display.isna(), "5%+")
    remuneration_bucket = remuneration_bucket.where(rate_display.isna() | (abs_rate > 5), "4-5%")
    remuneration_bucket = remuneration_bucket.where(rate_display.isna() | (abs_rate > 4), "3-4%")
    remuneration_bucket = remuneration_bucket.where(rate_display.isna() | (abs_rate > 3), "2-3%")
    remuneration_bucket = remuneration_bucket.where(rate_display.isna() | (abs_rate > 2), "1-2%")
    remuneration_bucket = remuneration_bucket.where(rate_display.isna() | (abs_rate > 1), "0-1%")
    remuneration_bucket = remuneration_bucket.where(rate_display.isna() | (abs_rate > 0), "0%")

    canonical_df = pd.DataFrame({
        "contract_id": cid,
        "sheet": sct,
        "side": cls["cls_side"],
        "categoria_ui": categoria_ui,
        "subcategoria_ui": cls["cls_subcategory_label"],
        "subcategory_id": cls["cls_subcategory_id"],
        "group": cls["cls_subcategory_label"],
        "currency": _text_col("original_currency").fillna("EUR"),
        "counterparty": None,
        "business_segment": _text_col("business_segment"),
        "strategic_segment": _text_col("strategic_segment"),
        "book_value_def": _text_col("book_value_def"),
        "amount": notional,
        "book_value": None,
        "rate_type": rate_type,
        "rate_display": rate_display,
        "remuneration_bucket": remuneration_bucket,
        "tipo_tasa_raw": rate_type_raw,
        "tasa_fija": _float_col("fixed_rate"),
        "spread": _float_col("spread"),
        "indice_ref": _text_col("index_name"),
        "tenor_indice": None,
        "fecha_inicio": dt_start,
        "fecha_vencimiento": dt_maturity,
        "fecha_prox_reprecio": dt_reprice,
        "maturity_years": mat_years,
        "maturity_bucket": maturity_bucket,
        "repricing_bucket": None,
        "include_in_balance_tree": cls["cls_side"].isin({"asset", "liability"}),
        "source_contract_type": sct,
        "daycount_base": _text_col("daycount_base"),
        "notional": notional,
        "repricing_freq": _text_col("repricing_freq"),
        "payment_freq": _text_col("payment_freq"),
        "floor_rate": _float_col("floor_rate"),
        "cap_rate": _float_col("cap_rate"),
        "balance_product": _text_col("balance_product"),
        "balance_section": _text_col("balance_section"),
        "balance_epigrafe": _text_col("balance_epigrafe"),
    }, index=motor_df.index)

    return canonical_df


# ── Parquet serialization ────────────────────────────────────────────────────

def _serialize_motor_df_to_parquet(motor_df: pd.DataFrame, path: Path) -> None:
    """Write motor DataFrame to Parquet (10-50x smaller/faster than JSON)."""
    motor_df.to_parquet(path, engine="pyarrow", index=False)
