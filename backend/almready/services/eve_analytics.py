from __future__ import annotations

"""
Analytics de EVE para reporting y visualizacion.

Este modulo no sustituye el calculo EVE oficial:
- El PV sigue calculandose flujo a flujo (exacto).
- El bucketing se aplica solo para agrupar resultados en tablas/graficos.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from almready.config.eve_buckets import EVE_VIS_BUCKETS_OPTIMAL
from almready.core.daycount import normalizar_base_de_calculo, yearfrac
from almready.services._eve_utils import normalise_buckets as _normalise_buckets_shared
from almready.services.eve import EVEBucket, build_eve_cashflows
from almready.services.market import ForwardCurveSet


@dataclass(frozen=True)
class EVEScenarioPoint:
    """Punto de resumen de un escenario EVE respecto al base."""

    scenario: str
    eve_value: float
    delta_vs_base: float
    is_worst: bool


def _normalise_buckets(
    buckets: Sequence[EVEBucket | Mapping[str, Any]] | None,
) -> list[EVEBucket]:
    return _normalise_buckets_shared(buckets, default=EVE_VIS_BUCKETS_OPTIMAL)


def build_eve_scenario_summary(
    *,
    base_eve: float,
    scenario_eve: Mapping[str, float],
) -> pd.DataFrame:
    """
    Construye tabla de resumen por escenario con delta vs base y flag worst.
    """
    rows: list[dict[str, Any]] = [
        {
            "scenario": "base",
            "eve_value": float(base_eve),
            "delta_vs_base": 0.0,
            "is_worst": False,
        }
    ]
    for scenario_name, value in scenario_eve.items():
        rows.append(
            {
                "scenario": str(scenario_name),
                "eve_value": float(value),
                "delta_vs_base": float(value) - float(base_eve),
                "is_worst": False,
            }
        )

    out = pd.DataFrame(rows)
    non_base = out.loc[out["scenario"] != "base"]
    if not non_base.empty:
        worst_idx = non_base["delta_vs_base"].astype(float).idxmin()
        out.loc[worst_idx, "is_worst"] = True
    return out.reset_index(drop=True)


def worst_scenario_from_summary(summary: pd.DataFrame) -> str | None:
    """Devuelve el nombre del escenario marcado como worst en summary."""
    if summary.empty:
        return None
    required = {"scenario", "is_worst"}
    missing = sorted(required - set(summary.columns))
    if missing:
        raise ValueError(f"summary sin columnas requeridas: {missing}")
    worst = summary.loc[summary["is_worst"].astype(bool)]
    if worst.empty:
        return None
    return str(worst.iloc[0]["scenario"])


def _assign_bucket_name(t_years: float, buckets: list[EVEBucket]) -> str:
    t = max(0.0, float(t_years))
    for b in buckets:
        if b.contains(t):
            return b.name
    return buckets[-1].name


def _side_group(side_value: Any, total_amount: float) -> str:
    s = str(side_value).strip().upper()
    if s == "A":
        return "asset"
    if s == "L":
        return "liability"
    return "asset" if float(total_amount) >= 0.0 else "liability"


def _bucket_meta_table(buckets: list[EVEBucket]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for i, b in enumerate(buckets):
        rows.append(
            {
                "bucket_order": int(i),
                "bucket_name": str(b.name),
                "bucket_start_years": float(b.start_years),
                "bucket_end_years": None if b.end_years is None else float(b.end_years),
            }
        )
    return pd.DataFrame(rows)


def compute_eve_full(
    cashflows: pd.DataFrame,
    *,
    discount_curve_set: ForwardCurveSet,
    discount_index: str = "EUR_ESTR_OIS",
    include_buckets: bool = False,
    buckets: Sequence[EVEBucket | Mapping[str, Any]] | None = None,
) -> tuple[float, list[dict[str, Any]] | None]:
    """
    Compute scalar EVE and (optionally) per-bucket breakdown from pre-built cashflows.

    Returns (scalar_eve, bucket_list_or_None).
    bucket_list entries: {scenario, bucket_order, bucket_name, bucket_start_years,
    bucket_end_years, side_group, pv_interest, pv_principal, pv_total,
    cashflow_total, flow_count}.
    """
    if cashflows.empty:
        if not include_buckets:
            return 0.0, None
        norm_buckets = _normalise_buckets(buckets)
        empty_rows: list[dict[str, Any]] = []
        for i, b in enumerate(norm_buckets):
            for sg in ("asset", "liability", "net"):
                empty_rows.append({
                    "bucket_order": i,
                    "bucket_name": b.name,
                    "bucket_start_years": float(b.start_years),
                    "bucket_end_years": None if b.end_years is None else float(b.end_years),
                    "side_group": sg,
                    "pv_interest": 0.0, "pv_principal": 0.0, "pv_total": 0.0,
                    "cashflow_total": 0.0, "flow_count": 0,
                })
        return 0.0, empty_rows

    work = cashflows.copy()
    work["flow_date"] = pd.to_datetime(work["flow_date"], errors="coerce").dt.date

    # OPT-3: Cache discount factors by unique date (~2k unique vs ~76k total)
    unique_dates = work["flow_date"].unique()
    df_cache = {d: float(discount_curve_set.df_on_date(discount_index, d)) for d in unique_dates}
    work["discount_factor"] = work["flow_date"].map(df_cache)
    work["pv_total"] = work["total_amount"].astype(float) * work["discount_factor"]

    # Scalar EVE = sum of all PVs
    scalar_eve = float(work["pv_total"].sum())

    if not include_buckets:
        return scalar_eve, None

    # Bucket breakdown
    norm_buckets = _normalise_buckets(buckets)
    bucket_meta = _bucket_meta_table(norm_buckets)
    dc_base = normalizar_base_de_calculo(discount_curve_set.base)

    # OPT-3: Cache yearfrac by unique date
    tyears_cache = {d: max(0.0, float(yearfrac(discount_curve_set.analysis_date, d, dc_base))) for d in unique_dates}
    work["t_years"] = work["flow_date"].map(tyears_cache)

    # OPT-3: Vectorize bucket assignment with pd.cut instead of per-element apply
    bucket_boundaries = [float(b.start_years) for b in norm_buckets] + [float("inf")]
    bucket_labels = [b.name for b in norm_buckets]
    work["bucket_name"] = pd.cut(
        work["t_years"].astype(float), bins=bucket_boundaries, labels=bucket_labels, right=False,
    )
    work["side_group"] = [
        _side_group(side_value=s, total_amount=a)
        for s, a in zip(work["side"], work["total_amount"])
    ]
    work["pv_interest"] = work["interest_amount"].astype(float) * work["discount_factor"]
    work["pv_principal"] = work["principal_amount"].astype(float) * work["discount_factor"]

    grouped = (
        work.groupby(["bucket_name", "side_group"], as_index=False, observed=True)
        .agg(
            pv_interest=("pv_interest", "sum"),
            pv_principal=("pv_principal", "sum"),
            pv_total=("pv_total", "sum"),
            cashflow_total=("total_amount", "sum"),
            flow_count=("contract_id", "size"),
        )
    )
    grouped_idx = grouped.set_index(["bucket_name", "side_group"])

    full_rows: list[dict[str, Any]] = []
    for _, b in bucket_meta.iterrows():
        bname = str(b["bucket_name"])
        for sg in ("asset", "liability"):
            key = (bname, sg)
            if key in grouped_idx.index:
                g = grouped_idx.loc[key]
                full_rows.append({
                    "bucket_order": int(b["bucket_order"]),
                    "bucket_name": bname,
                    "bucket_start_years": float(b["bucket_start_years"]),
                    "bucket_end_years": None if pd.isna(b["bucket_end_years"]) else float(b["bucket_end_years"]),
                    "side_group": sg,
                    "pv_interest": float(g["pv_interest"]),
                    "pv_principal": float(g["pv_principal"]),
                    "pv_total": float(g["pv_total"]),
                    "cashflow_total": float(g["cashflow_total"]),
                    "flow_count": int(g["flow_count"]),
                })
            else:
                full_rows.append({
                    "bucket_order": int(b["bucket_order"]),
                    "bucket_name": bname,
                    "bucket_start_years": float(b["bucket_start_years"]),
                    "bucket_end_years": None if pd.isna(b["bucket_end_years"]) else float(b["bucket_end_years"]),
                    "side_group": sg,
                    "pv_interest": 0.0, "pv_principal": 0.0, "pv_total": 0.0,
                    "cashflow_total": 0.0, "flow_count": 0,
                })

    # Add net rows
    net_by_bucket: dict[str, dict[str, float]] = {}
    for r in full_rows:
        bname = r["bucket_name"]
        if bname not in net_by_bucket:
            net_by_bucket[bname] = {
                "pv_interest": 0.0, "pv_principal": 0.0, "pv_total": 0.0,
                "cashflow_total": 0.0, "flow_count": 0,
            }
        for k in ("pv_interest", "pv_principal", "pv_total", "cashflow_total", "flow_count"):
            net_by_bucket[bname][k] += r[k]

    for _, b in bucket_meta.iterrows():
        bname = str(b["bucket_name"])
        n = net_by_bucket.get(bname, {})
        full_rows.append({
            "bucket_order": int(b["bucket_order"]),
            "bucket_name": bname,
            "bucket_start_years": float(b["bucket_start_years"]),
            "bucket_end_years": None if pd.isna(b["bucket_end_years"]) else float(b["bucket_end_years"]),
            "side_group": "net",
            "pv_interest": n.get("pv_interest", 0.0),
            "pv_principal": n.get("pv_principal", 0.0),
            "pv_total": n.get("pv_total", 0.0),
            "cashflow_total": n.get("cashflow_total", 0.0),
            "flow_count": n.get("flow_count", 0),
        })

    return scalar_eve, full_rows


def build_eve_bucket_breakdown_exact(
    positions: pd.DataFrame,
    *,
    base_discount_curve_set: ForwardCurveSet,
    scenario_discount_curve_sets: Mapping[str, ForwardCurveSet],
    base_projection_curve_set: ForwardCurveSet | None = None,
    scenario_projection_curve_sets: Mapping[str, ForwardCurveSet] | None = None,
    scheduled_principal_flows: pd.DataFrame | None = None,
    discount_index: str = "EUR_ESTR_OIS",
    buckets: Sequence[EVEBucket | Mapping[str, Any]] | None = None,
) -> pd.DataFrame:
    """
    Descomposicion exacta por bucket temporal y por lado (asset/liability/net).

    Importante:
    - El PV se calcula flujo a flujo con DF exacto.
    - El bucket solo se usa para agrupar resultados visuales/reporting.

    Output principal:
    - scenario, bucket_order, bucket_name, side_group
    - pv_interest, pv_principal, pv_total
    - cashflow_total, flow_count
    """
    norm_buckets = _normalise_buckets(buckets)
    bucket_meta = _bucket_meta_table(norm_buckets)

    base_projection = base_discount_curve_set if base_projection_curve_set is None else base_projection_curve_set
    scenario_projection = (
        scenario_discount_curve_sets
        if scenario_projection_curve_sets is None
        else scenario_projection_curve_sets
    )

    scenario_items: list[tuple[str, ForwardCurveSet, ForwardCurveSet]] = [
        ("base", base_discount_curve_set, base_projection)
    ]
    for scenario_name, discount_set in scenario_discount_curve_sets.items():
        if scenario_name not in scenario_projection:
            raise KeyError(f"Falta projection curve set para escenario {scenario_name!r}.")
        scenario_items.append((str(scenario_name), discount_set, scenario_projection[scenario_name]))

    all_rows: list[pd.DataFrame] = []
    for scenario_name, discount_set, projection_set in scenario_items:
        cashflows = build_eve_cashflows(
            positions,
            analysis_date=discount_set.analysis_date,
            projection_curve_set=projection_set,
            scheduled_principal_flows=scheduled_principal_flows,
        )

        if cashflows.empty:
            scenario_rows: list[dict[str, Any]] = []
            for _, b in bucket_meta.iterrows():
                for side_group in ("asset", "liability", "net"):
                    scenario_rows.append(
                        {
                            "scenario": scenario_name,
                            "bucket_order": int(b["bucket_order"]),
                            "bucket_name": str(b["bucket_name"]),
                            "bucket_start_years": float(b["bucket_start_years"]),
                            "bucket_end_years": None if pd.isna(b["bucket_end_years"]) else float(b["bucket_end_years"]),
                            "side_group": side_group,
                            "pv_interest": 0.0,
                            "pv_principal": 0.0,
                            "pv_total": 0.0,
                            "cashflow_total": 0.0,
                            "flow_count": 0,
                        }
                    )
            all_rows.append(pd.DataFrame(scenario_rows))
            continue

        work = cashflows.copy()
        work["flow_date"] = pd.to_datetime(work["flow_date"], errors="coerce").dt.date
        if work["flow_date"].isna().any():
            rows = [int(i) + 2 for i in work.index[work["flow_date"].isna()][:10].tolist()]
            raise ValueError(f"Cashflows con flow_date invalida en filas {rows}")

        dc_base = normalizar_base_de_calculo(discount_set.base)
        work["t_years"] = work["flow_date"].apply(
            lambda d: max(0.0, float(yearfrac(discount_set.analysis_date, d, dc_base)))
        )
        work["bucket_name"] = work["t_years"].astype(float).apply(
            lambda t: _assign_bucket_name(t, norm_buckets)
        )
        work["side_group"] = [
            _side_group(side_value=s, total_amount=a)
            for s, a in zip(work["side"], work["total_amount"])
        ]
        work["discount_factor"] = work["flow_date"].apply(
            lambda d: float(discount_set.df_on_date(discount_index, d))
        )
        work["pv_interest"] = work["interest_amount"].astype(float) * work["discount_factor"].astype(float)
        work["pv_principal"] = work["principal_amount"].astype(float) * work["discount_factor"].astype(float)
        work["pv_total"] = work["total_amount"].astype(float) * work["discount_factor"].astype(float)

        grouped = (
            work.groupby(["bucket_name", "side_group"], as_index=False)
            .agg(
                pv_interest=("pv_interest", "sum"),
                pv_principal=("pv_principal", "sum"),
                pv_total=("pv_total", "sum"),
                cashflow_total=("total_amount", "sum"),
                flow_count=("contract_id", "size"),
            )
        )

        grouped = grouped.merge(bucket_meta, on="bucket_name", how="left")
        grouped["scenario"] = str(scenario_name)

        # Completar buckets x lado para consistencia de graficos.
        full_rows: list[dict[str, Any]] = []
        grouped_idx = grouped.set_index(["bucket_name", "side_group"])
        for _, b in bucket_meta.iterrows():
            bname = str(b["bucket_name"])
            for side_group in ("asset", "liability"):
                key = (bname, side_group)
                if key in grouped_idx.index:
                    g = grouped_idx.loc[key]
                    full_rows.append(
                        {
                            "scenario": scenario_name,
                            "bucket_order": int(b["bucket_order"]),
                            "bucket_name": bname,
                            "bucket_start_years": float(b["bucket_start_years"]),
                            "bucket_end_years": None if pd.isna(b["bucket_end_years"]) else float(b["bucket_end_years"]),
                            "side_group": side_group,
                            "pv_interest": float(g["pv_interest"]),
                            "pv_principal": float(g["pv_principal"]),
                            "pv_total": float(g["pv_total"]),
                            "cashflow_total": float(g["cashflow_total"]),
                            "flow_count": int(g["flow_count"]),
                        }
                    )
                else:
                    full_rows.append(
                        {
                            "scenario": scenario_name,
                            "bucket_order": int(b["bucket_order"]),
                            "bucket_name": bname,
                            "bucket_start_years": float(b["bucket_start_years"]),
                            "bucket_end_years": None if pd.isna(b["bucket_end_years"]) else float(b["bucket_end_years"]),
                            "side_group": side_group,
                            "pv_interest": 0.0,
                            "pv_principal": 0.0,
                            "pv_total": 0.0,
                            "cashflow_total": 0.0,
                            "flow_count": 0,
                        }
                    )

        full_df = pd.DataFrame(full_rows)
        net_df = (
            full_df.groupby(
                ["scenario", "bucket_order", "bucket_name", "bucket_start_years", "bucket_end_years"],
                as_index=False,
            )
            .agg(
                pv_interest=("pv_interest", "sum"),
                pv_principal=("pv_principal", "sum"),
                pv_total=("pv_total", "sum"),
                cashflow_total=("cashflow_total", "sum"),
                flow_count=("flow_count", "sum"),
            )
        )
        net_df["side_group"] = "net"
        scenario_df = pd.concat([full_df, net_df], ignore_index=True)
        all_rows.append(scenario_df)

    out = pd.concat(all_rows, ignore_index=True)
    side_order_map = {"asset": 0, "liability": 1, "net": 2}
    out["side_order"] = out["side_group"].map(side_order_map).fillna(99).astype(int)
    out = out.sort_values(
        ["scenario", "bucket_order", "side_order"],
        kind="stable",
    ).reset_index(drop=True)
    return out
