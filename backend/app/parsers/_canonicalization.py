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
    if subcategory_id == "deposits":
        maturity_years_val = 0.0

    maturity_bucket = _to_text(get("bucket_vencimiento")) or _bucket_from_years(maturity_years_val)
    if subcategory_id == "deposits":
        maturity_bucket = "<1Y"
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
        "amount": amount,
        "book_value": book_value,
        "rate_type": rate_type,
        "rate_display": rate_display_val,
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

    maturity_bucket = _bucket_from_years(mat_years)
    if is_non_maturity:
        maturity_bucket = "<1Y"

    return {
        "contract_id": contract_id,
        "sheet": source_contract_type,
        "side": side,
        "categoria_ui": categoria_ui,
        "subcategoria_ui": subcategoria_ui,
        "subcategory_id": subcategory_id,
        "group": subcategoria_ui,
        "currency": "EUR",
        "counterparty": None,
        "amount": amount,
        "book_value": None,
        "rate_type": rate_type,
        "rate_display": rate_display_val,
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
    """Vectorised balance classification: iterates over *rules* not *rows*."""
    n = len(motor_df)

    # Resolve side from apartado, fallback to motor side
    apartado = motor_df["balance_section"].fillna("").str.strip().str.upper() if "balance_section" in motor_df.columns else pd.Series("", index=motor_df.index)
    motor_side_raw = motor_df["side"].fillna("A").astype(str).str.upper()

    side_from_apart = apartado.map(_APARTADO_SIDE)
    side_from_motor = motor_side_raw.map({"A": "asset", "L": "liability"}).fillna("asset")
    side = side_from_apart.where(side_from_apart.notna(), side_from_motor)

    # Prepare producto for keyword matching
    producto = motor_df["balance_product"].fillna("").astype(str).str.upper() if "balance_product" in motor_df.columns else pd.Series("", index=motor_df.index)

    # Default subcategory_id per side
    subcategory_id = pd.Series(ASSET_DEFAULT, index=motor_df.index, dtype="object")
    subcategory_id = subcategory_id.where(side == "asset", LIABILITY_DEFAULT)
    subcategory_id = subcategory_id.where(side != "derivative", "derivatives")

    # Match rules: iterate over rules (~70), not rows (~1.5M)
    matched = pd.Series(False, index=motor_df.index)

    all_rule_sets: list[tuple[str, Sequence[tuple[str, str]]]] = [
        ("asset", client_rules.get("asset_rules", ())),
        ("liability", client_rules.get("liability_rules", ())),
        ("derivative", client_rules.get("derivative_rules", ())),
    ]

    for target_side, rules in all_rule_sets:
        for keyword, sub_id in rules:
            rule_match = (side == target_side) & ~matched & producto.str.contains(keyword.upper(), na=False, regex=False)
            subcategory_id = subcategory_id.where(~rule_match, sub_id)
            matched = matched | rule_match

    # Log classification coverage
    n_unmatched = int((~matched).sum())
    if n_unmatched > 0:
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
    """
    n = len(motor_df)

    # Classification
    cls = _classify_motor_df(motor_df, client_rules)

    # Build canonical DataFrame with vectorised ops
    sct = motor_df["source_contract_type"].fillna("unknown").astype(str) if "source_contract_type" in motor_df.columns else pd.Series("unknown", index=motor_df.index)
    is_non_maturity = sct.str.contains("non_maturity", na=False, regex=False)

    # Contract ID
    idx_series = pd.Series(range(1, n + 1), index=motor_df.index, dtype="int64")
    contract_id = motor_df["contract_id"].fillna("motor-" + idx_series.astype(str)).astype(str) if "contract_id" in motor_df.columns else ("motor-" + idx_series.astype(str))

    # Amounts
    notional = pd.to_numeric(motor_df["notional"], errors="coerce").fillna(0.0) if "notional" in motor_df.columns else pd.Series(0.0, index=motor_df.index)

    # Rate type
    rate_type_raw = motor_df["rate_type"].fillna("").astype(str) if "rate_type" in motor_df.columns else pd.Series("", index=motor_df.index)
    rate_type = rate_type_raw.map({"fixed": "Fixed", "float": "Floating"})

    # Dates → ISO strings
    now = datetime.now(timezone.utc).date()

    def _col_to_iso(col_name: str) -> pd.Series:
        if col_name not in motor_df.columns:
            return pd.Series(None, index=motor_df.index, dtype="object")
        col = motor_df[col_name]
        dt = pd.to_datetime(col, errors="coerce")
        return dt.dt.strftime("%Y-%m-%d").where(dt.notna(), other=None)

    fecha_inicio = _col_to_iso("start_date")
    fecha_vencimiento = _col_to_iso("maturity_date")
    fecha_prox_reprecio = _col_to_iso("next_reprice_date")

    # Maturity years (vectorised)
    if "maturity_date" in motor_df.columns:
        mat_dt = pd.to_datetime(motor_df["maturity_date"], errors="coerce")
        mat_years = (mat_dt - pd.Timestamp(now)).dt.days / 365.25
        mat_years = mat_years.where(mat_years >= 0, other=np.nan)
        mat_years = mat_years.where(mat_dt.notna(), other=np.nan)
    else:
        mat_years = pd.Series(np.nan, index=motor_df.index)
    mat_years = mat_years.where(~is_non_maturity, 0.0)

    # Maturity bucket (vectorised)
    maturity_bucket = pd.cut(
        mat_years,
        bins=[-np.inf, 1, 5, 10, 20, np.inf],
        labels=["<1Y", "1-5Y", "5-10Y", "10-20Y", ">20Y"],
        right=False,
    ).astype("object")
    maturity_bucket = maturity_bucket.where(mat_years.notna(), other=None)
    maturity_bucket = maturity_bucket.where(~is_non_maturity, "<1Y")

    # Float columns
    def _float_col(name: str) -> pd.Series:
        if name not in motor_df.columns:
            return pd.Series(None, index=motor_df.index, dtype="object")
        return pd.to_numeric(motor_df[name], errors="coerce").where(
            pd.to_numeric(motor_df[name], errors="coerce").notna(), other=None
        )

    fixed_rate = _float_col("fixed_rate")
    spread_val = _float_col("spread")
    floor_rate = _float_col("floor_rate")
    cap_rate = _float_col("cap_rate")

    # Text columns
    def _text_col(name: str) -> pd.Series:
        if name not in motor_df.columns:
            return pd.Series(None, index=motor_df.index, dtype="object")
        s = motor_df[name].astype(str).str.strip()
        return s.where((motor_df[name].notna()) & s.ne("") & s.ne("nan") & s.ne("None") & s.ne("<NA>"), other=None)

    categoria_ui = cls["cls_side"].map(_BC_SIDE_UI).fillna("Assets")

    canonical_df = pd.DataFrame({
        "contract_id": contract_id,
        "sheet": sct,
        "side": cls["cls_side"],
        "categoria_ui": categoria_ui,
        "subcategoria_ui": cls["cls_subcategory_label"],
        "subcategory_id": cls["cls_subcategory_id"],
        "group": cls["cls_subcategory_label"],
        "currency": "EUR",
        "counterparty": None,
        "amount": notional,
        "book_value": None,
        "rate_type": rate_type,
        "rate_display": fixed_rate,
        "tipo_tasa_raw": rate_type_raw,
        "tasa_fija": fixed_rate,
        "spread": spread_val,
        "indice_ref": _text_col("index_name"),
        "tenor_indice": None,
        "fecha_inicio": fecha_inicio,
        "fecha_vencimiento": fecha_vencimiento,
        "fecha_prox_reprecio": fecha_prox_reprecio,
        "maturity_years": mat_years.where(mat_years.notna(), other=None),
        "maturity_bucket": maturity_bucket,
        "repricing_bucket": None,
        "include_in_balance_tree": cls["cls_side"].isin({"asset", "liability"}),
        "source_contract_type": sct,
        "daycount_base": _text_col("daycount_base"),
        "notional": notional,
        "repricing_freq": _text_col("repricing_freq"),
        "payment_freq": _text_col("payment_freq"),
        "floor_rate": floor_rate,
        "cap_rate": cap_rate,
        "balance_product": _text_col("balance_product"),
        "balance_section": _text_col("balance_section"),
        "balance_epigrafe": _text_col("balance_epigrafe"),
    }, index=motor_df.index)

    # Convert NaN/NaT to None for clean Parquet/JSON serialization
    canonical_df = canonical_df.astype(object).where(canonical_df.notna(), other=None)

    return canonical_df


# ── Parquet serialization ────────────────────────────────────────────────────

def _serialize_motor_df_to_parquet(motor_df: pd.DataFrame, path: Path) -> None:
    """Write motor DataFrame to Parquet (10-50x smaller/faster than JSON)."""
    motor_df.to_parquet(path, engine="pyarrow", index=False)
