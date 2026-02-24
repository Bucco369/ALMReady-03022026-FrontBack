from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.services.market import ForwardCurveSet, load_forward_curve_set

_DEFAULT_CURVE_FILE = _PROJECT_ROOT / "Inputs" / "Curve tenors_input.xlsx"
_DEFAULT_ANALYSIS_DATE = "2025-12-31"
_DEFAULT_BASE = "ACT/360"
_DEFAULT_SHEET = "0"
_REPO_ROOT = _PROJECT_ROOT.parent
_DATA_ROOT = _REPO_ROOT.parent / "data"
_DEFAULT_OUT = _DATA_ROOT / "out" / "forward_curves.png"


def _parse_sheet(value: str):
    s = str(value).strip()
    return int(s) if s.isdigit() else s


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Fecha invalida '{value}'. Usa formato YYYY-MM-DD.") from exc


def _plot_all_curves(curve_set: ForwardCurveSet, output_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Falta dependencia 'matplotlib'. Instalala para poder graficar: "
            "pip install matplotlib"
        ) from exc

    df = curve_set.points.sort_values(["IndexName", "YearFrac"]).copy()

    fig, ax = plt.subplots(figsize=(13, 7))
    for index_name, sub in df.groupby("IndexName", sort=True):
        ax.plot(
            sub["YearFrac"].astype(float),
            sub["FwdRate"].astype(float),
            marker="o",
            markersize=2.5,
            linewidth=1.3,
            label=str(index_name),
        )

    ax.set_title("Forward Curves Loaded From Input File")
    ax.set_xlabel("Year Fraction")
    ax.set_ylabel("Forward Rate (decimal)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=8, ncol=2)
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke test para graficar todas las curvas forward cargadas."
    )
    parser.add_argument(
        "--path",
        default=str(_DEFAULT_CURVE_FILE),
        help="Ruta del Excel de curvas.",
    )
    parser.add_argument(
        "--analysis-date",
        default=_DEFAULT_ANALYSIS_DATE,
        help="Fecha de analisis en formato YYYY-MM-DD.",
    )
    parser.add_argument(
        "--base",
        default=_DEFAULT_BASE,
        help="Base day count de curvas. Ej: ACT/360, ACT/365.",
    )
    parser.add_argument(
        "--sheet",
        default=_DEFAULT_SHEET,
        help="Indice o nombre de hoja. Por defecto: 0.",
    )
    parser.add_argument(
        "--out",
        default=str(_DEFAULT_OUT),
        help="Ruta de salida del grafico PNG.",
    )
    args = parser.parse_args()

    curve_file = Path(args.path)
    if not curve_file.exists():
        raise FileNotFoundError(f"No existe el archivo de curvas: {curve_file}")

    curve_set = load_forward_curve_set(
        path=str(curve_file),
        analysis_date=_parse_date(args.analysis_date),
        base=args.base,
        sheet_name=_parse_sheet(args.sheet),
    )

    output_path = Path(args.out)
    _plot_all_curves(curve_set, output_path)

    print("=== MARKET CURVES PLOT ===")
    print(f"path: {curve_file}")
    print(f"analysis_date: {args.analysis_date}")
    print(f"base: {args.base}")
    print(f"sheet: {args.sheet}")
    print(f"indices: {len(curve_set.curves)}")
    print(f"points: {len(curve_set.points)}")
    print(f"plot_file: {output_path.resolve()}")


if __name__ == "__main__":
    main()
