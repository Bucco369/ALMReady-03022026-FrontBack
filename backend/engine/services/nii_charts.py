from __future__ import annotations

"""
Graficos de NII orientados a seguimiento mensual.

Usa el perfil mensual calculado por el motor NII para representar:
- ingresos (activo),
- gastos (pasivo),
- neto NII.
"""

from pathlib import Path
from typing import Sequence

import pandas as pd


def plot_nii_monthly_profile(
    monthly_profile: pd.DataFrame,
    *,
    output_path: str | Path,
    scenarios: Sequence[str] = ("base", "parallel-up", "parallel-down"),
    title_prefix: str = "NII mensual",
) -> Path:
    """
    Grafico mensual NII:
    - barras ingresos (positivo)
    - barras gastos (negativo)
    - linea neto NII
    """
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Falta dependencia 'matplotlib'. Instalala para poder graficar: "
            "pip install matplotlib"
        ) from exc

    required = {
        "scenario",
        "month_index",
        "month_label",
        "interest_income",
        "interest_expense",
        "net_nii",
    }
    missing = sorted(required - set(monthly_profile.columns))
    if missing:
        raise ValueError(f"monthly_profile sin columnas requeridas: {missing}")

    if monthly_profile.empty:
        raise ValueError("monthly_profile vacio: no hay datos para graficar.")

    selected = [str(s) for s in scenarios]
    n = len(selected)
    if n <= 0:
        raise ValueError("Se requiere al menos un escenario para graficar.")

    fig, axes = plt.subplots(
        nrows=n,
        ncols=1,
        figsize=(12, max(3.8, 3.2 * n)),
        sharex=True,
    )
    if n == 1:
        axes = [axes]

    for i, scenario_name in enumerate(selected):
        ax = axes[i]
        sub = monthly_profile.loc[monthly_profile["scenario"].astype(str) == scenario_name].copy()
        if sub.empty:
            raise ValueError(f"No hay filas en monthly_profile para escenario {scenario_name!r}")
        sub = sub.sort_values("month_index", kind="stable")

        x = sub["month_index"].astype(int).tolist()
        labels = sub["month_label"].astype(str).tolist()
        income = sub["interest_income"].astype(float).tolist()
        expense = sub["interest_expense"].astype(float).tolist()
        net = sub["net_nii"].astype(float).tolist()

        ax.bar(x, income, width=0.65, color="#2ca02c", alpha=0.8, label="Ingresos (A)")
        ax.bar(x, expense, width=0.65, color="#d62728", alpha=0.8, label="Gastos (L)")
        ax.plot(x, net, color="#1f77b4", marker="o", linewidth=2.0, label="NII neto")
        ax.axhline(0.0, color="black", linewidth=1.0, alpha=0.8)
        ax.set_ylabel("Importe")
        ax.set_title(f"{title_prefix} - {scenario_name}")
        ax.grid(True, axis="y", alpha=0.25)
        if i == 0:
            ax.legend(loc="best")

        ax.set_xticks(x)
        ax.set_xticklabels(labels)

    axes[-1].set_xlabel("Mes horizonte")
    fig.tight_layout()

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_nii_base_vs_worst_by_month(
    monthly_profile: pd.DataFrame,
    *,
    worst_scenario: str,
    output_path: str | Path,
    title: str = "NII por mes: Base vs Worst",
) -> Path:
    """
    Variante comparativa estilo EVE (base vs worst) sobre buckets mensuales.
    - barras de ingresos/gastos para base y worst (en paralelo por mes)
    - linea de neto para ambos escenarios
    """
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Falta dependencia 'matplotlib'. Instalala para poder graficar: "
            "pip install matplotlib"
        ) from exc

    required = {
        "scenario",
        "month_index",
        "month_label",
        "interest_income",
        "interest_expense",
        "net_nii",
    }
    missing = sorted(required - set(monthly_profile.columns))
    if missing:
        raise ValueError(f"monthly_profile sin columnas requeridas: {missing}")
    if monthly_profile.empty:
        raise ValueError("monthly_profile vacio: no hay datos para graficar.")

    work = monthly_profile.copy()
    work["scenario"] = work["scenario"].astype(str)
    selected = work.loc[work["scenario"].isin(["base", str(worst_scenario)])].copy()
    if selected.empty:
        raise ValueError("monthly_profile sin datos para escenarios base/worst.")

    pivot = selected.pivot_table(
        index=["month_index", "month_label"],
        columns="scenario",
        values=["interest_income", "interest_expense", "net_nii"],
        aggfunc="sum",
        fill_value=0.0,
    ).sort_index()

    month_labels = [str(k[1]) for k in pivot.index.tolist()]
    x = list(range(len(month_labels)))
    width = 0.38

    def _series(metric: str, scenario: str) -> list[float]:
        col = (metric, str(scenario))
        if col not in pivot.columns:
            return [0.0] * len(pivot.index)
        return pivot[col].astype(float).tolist()

    base_income = _series("interest_income", "base")
    base_expense = _series("interest_expense", "base")
    base_net = _series("net_nii", "base")
    worst_income = _series("interest_income", str(worst_scenario))
    worst_expense = _series("interest_expense", str(worst_scenario))
    worst_net = _series("net_nii", str(worst_scenario))

    fig, ax = plt.subplots(figsize=(14.5, 6.0))
    x_base = [v - (width / 2.0) for v in x]
    x_worst = [v + (width / 2.0) for v in x]

    ax.bar(x_base, base_income, width=width, color="#98df8a", alpha=0.85, label="Base ingresos (+)")
    ax.bar(x_base, base_expense, width=width, color="#ff9896", alpha=0.85, label="Base gastos (-)")
    ax.bar(x_worst, worst_income, width=width, color="#2ca02c", alpha=0.85, label=f"{worst_scenario} ingresos (+)")
    ax.bar(x_worst, worst_expense, width=width, color="#d62728", alpha=0.85, label=f"{worst_scenario} gastos (-)")

    ax.plot(x_base, base_net, color="#1f77b4", linewidth=1.8, marker="o", markersize=3.5, label="Base neto")
    ax.plot(x_worst, worst_net, color="#9467bd", linewidth=1.8, marker="o", markersize=3.5, label=f"{worst_scenario} neto")

    ax.axhline(0.0, color="black", linewidth=1.0, alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(month_labels, rotation=0)
    ax.set_ylabel("Importe mensual")
    ax.set_xlabel("Mes horizonte")
    ax.set_title(title)
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(loc="best", ncol=3, fontsize=8)

    fig.tight_layout()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out
