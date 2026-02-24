from __future__ import annotations

"""
Graficos de EVE para reporting.

Depende de tablas de analytics (summary y breakdown por bucket) y genera
figuras listas para comite/diagnostico.
"""

from pathlib import Path

import pandas as pd

from engine.services.eve_analytics import worst_scenario_from_summary


def plot_eve_scenario_deltas(
    scenario_summary: pd.DataFrame,
    *,
    output_path: str | Path,
    title: str = "EVE: delta vs base por escenario",
) -> Path:
    """
    Grafico de barras con delta EVE por escenario frente al base.
    """
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Falta dependencia 'matplotlib'. Instalala para poder graficar: "
            "pip install matplotlib"
        ) from exc

    required = {"scenario", "delta_vs_base", "is_worst"}
    missing = sorted(required - set(scenario_summary.columns))
    if missing:
        raise ValueError(f"scenario_summary sin columnas requeridas: {missing}")

    plot_df = scenario_summary.loc[scenario_summary["scenario"] != "base"].copy()
    if plot_df.empty:
        raise ValueError("scenario_summary no contiene escenarios distintos de base.")

    plot_df = plot_df.sort_values("delta_vs_base", kind="stable").reset_index(drop=True)
    xs = plot_df["scenario"].astype(str).tolist()
    ys = plot_df["delta_vs_base"].astype(float).tolist()
    worst_flags = plot_df["is_worst"].astype(bool).tolist()

    colors = []
    for y, is_worst in zip(ys, worst_flags):
        if is_worst:
            colors.append("#d62728")
        elif y >= 0.0:
            colors.append("#2ca02c")
        else:
            colors.append("#1f77b4")

    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    bars = ax.bar(xs, ys, color=colors, alpha=0.85)
    ax.axhline(0.0, color="black", linewidth=1.0, alpha=0.8)
    ax.set_title(title)
    ax.set_ylabel("Delta EVE (scenario - base)")
    ax.grid(True, axis="y", alpha=0.25)

    for bar, y in zip(bars, ys):
        ax.text(
            bar.get_x() + (bar.get_width() / 2.0),
            y,
            f"{y:,.0f}",
            ha="center",
            va="bottom" if y >= 0 else "top",
            fontsize=8,
        )

    fig.tight_layout()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_eve_base_vs_worst_by_bucket(
    bucket_breakdown: pd.DataFrame,
    *,
    scenario_summary: pd.DataFrame,
    output_path: str | Path,
    title: str = "EVE por bucket: Base vs Worst",
) -> Path:
    """
    Grafico por bucket comparando Base vs Worst:
    - barras de activo/pasivo para ambos escenarios
    - linea de neto para ambos escenarios
    """
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Falta dependencia 'matplotlib'. Instalala para poder graficar: "
            "pip install matplotlib"
        ) from exc

    required = {"scenario", "bucket_order", "bucket_name", "side_group", "pv_total"}
    missing = sorted(required - set(bucket_breakdown.columns))
    if missing:
        raise ValueError(f"bucket_breakdown sin columnas requeridas: {missing}")

    worst = worst_scenario_from_summary(scenario_summary)
    if worst is None:
        raise ValueError("No se pudo identificar worst scenario en scenario_summary.")

    bb = bucket_breakdown.copy()
    bb = bb.loc[bb["scenario"].isin(["base", worst])].copy()
    if bb.empty:
        raise ValueError("bucket_breakdown vacio para escenarios base/worst.")

    sides = bb.loc[bb["side_group"].isin(["asset", "liability", "net"])].copy()
    sides = sides.sort_values(["bucket_order", "scenario", "side_group"], kind="stable")

    pivot = sides.pivot_table(
        index=["bucket_order", "bucket_name"],
        columns=["scenario", "side_group"],
        values="pv_total",
        aggfunc="sum",
        fill_value=0.0,
    )
    pivot = pivot.sort_index()

    bucket_names = [str(k[1]) for k in pivot.index.tolist()]
    x = list(range(len(bucket_names)))
    width = 0.38

    def _col(scenario: str, side: str) -> list[float]:
        if (scenario, side) not in pivot.columns:
            return [0.0] * len(pivot.index)
        return pivot[(scenario, side)].astype(float).tolist()

    base_asset = _col("base", "asset")
    base_liab = _col("base", "liability")
    base_net = _col("base", "net")

    worst_asset = _col(worst, "asset")
    worst_liab = _col(worst, "liability")
    worst_net = _col(worst, "net")

    fig, ax = plt.subplots(figsize=(14.5, 6.0))
    x_base = [v - (width / 2.0) for v in x]
    x_worst = [v + (width / 2.0) for v in x]

    ax.bar(x_base, base_asset, width=width, color="#98df8a", alpha=0.85, label="Base activo (+)")
    ax.bar(x_base, base_liab, width=width, color="#ff9896", alpha=0.85, label="Base pasivo (-)")
    ax.bar(x_worst, worst_asset, width=width, color="#2ca02c", alpha=0.85, label=f"{worst} activo (+)")
    ax.bar(x_worst, worst_liab, width=width, color="#d62728", alpha=0.85, label=f"{worst} pasivo (-)")

    ax.plot(x_base, base_net, color="#1f77b4", linewidth=1.8, marker="o", markersize=3.5, label="Base neto")
    ax.plot(x_worst, worst_net, color="#9467bd", linewidth=1.8, marker="o", markersize=3.5, label=f"{worst} neto")

    ax.axhline(0.0, color="black", linewidth=1.0, alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(bucket_names, rotation=45, ha="right")
    ax.set_ylabel("PV por bucket")
    ax.set_title(title)
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(loc="best", ncol=3, fontsize=8)

    fig.tight_layout()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_eve_worst_delta_by_bucket(
    bucket_breakdown: pd.DataFrame,
    *,
    scenario_summary: pd.DataFrame,
    output_path: str | Path,
    title: str = "Worst EVE: delta por bucket (neto y acumulado)",
) -> Path:
    """
    Grafico del escenario worst:
    - barras: delta neto por bucket (worst - base)
    - linea: delta acumulado por bucket
    """
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Falta dependencia 'matplotlib'. Instalala para poder graficar: "
            "pip install matplotlib"
        ) from exc

    required = {"scenario", "bucket_order", "bucket_name", "side_group", "pv_total"}
    missing = sorted(required - set(bucket_breakdown.columns))
    if missing:
        raise ValueError(f"bucket_breakdown sin columnas requeridas: {missing}")

    worst = worst_scenario_from_summary(scenario_summary)
    if worst is None:
        raise ValueError("No se pudo identificar worst scenario en scenario_summary.")

    bb = bucket_breakdown.loc[bucket_breakdown["side_group"] == "net"].copy()
    base = bb.loc[bb["scenario"] == "base", ["bucket_order", "bucket_name", "pv_total"]].rename(
        columns={"pv_total": "pv_base"}
    )
    worst_df = bb.loc[bb["scenario"] == worst, ["bucket_order", "bucket_name", "pv_total"]].rename(
        columns={"pv_total": "pv_worst"}
    )
    merged = base.merge(worst_df, on=["bucket_order", "bucket_name"], how="outer").fillna(0.0)
    merged = merged.sort_values("bucket_order", kind="stable").reset_index(drop=True)
    if merged.empty:
        raise ValueError("Sin datos netos por bucket para base/worst.")

    merged["delta"] = merged["pv_worst"].astype(float) - merged["pv_base"].astype(float)
    merged["delta_cum"] = merged["delta"].astype(float).cumsum()

    x = list(range(len(merged)))
    labels = merged["bucket_name"].astype(str).tolist()
    delta = merged["delta"].astype(float).tolist()
    delta_cum = merged["delta_cum"].astype(float).tolist()

    bar_colors = ["#2ca02c" if v >= 0.0 else "#d62728" for v in delta]

    fig, ax = plt.subplots(figsize=(14.5, 6.0))
    ax.bar(x, delta, color=bar_colors, alpha=0.85, label=f"Delta neto ({worst} - base)")
    ax.plot(x, delta_cum, color="#1f77b4", linewidth=2.0, marker="o", markersize=3.5, label="Delta acumulado")
    ax.axhline(0.0, color="black", linewidth=1.0, alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel("Delta PV")
    ax.set_title(title)
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(loc="best")

    fig.tight_layout()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out
