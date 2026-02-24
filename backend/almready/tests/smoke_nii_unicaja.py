from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parents[2]   # backend/
_REPO_ROOT = _PROJECT_ROOT.parent                     # repository root
_DATA_ROOT = _REPO_ROOT.parent / "data"               # ../data/ (sibling of repo)
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from almready.config import bank_mapping_unicaja as unicaja_mapping
from almready.services.nii_pipeline import run_nii_from_specs


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Fecha invalida '{value}'. Usa formato YYYY-MM-DD.") from exc


def _parse_sheet(value: str) -> int | str:
    s = str(value).strip()
    return int(s) if s.isdigit() else s


def _default_curve_file() -> Path:
    curves_dir = _DATA_ROOT / "fixtures" / "curves" / "forwards"
    if not curves_dir.exists():
        return curves_dir / "curve_input.xlsx"
    matches = sorted(curves_dir.glob("*.xlsx"))
    if matches:
        return matches[0]
    return curves_dir / "curve_input.xlsx"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Runner NII para Unicaja + grafico mensual (base/up/down)."
    )
    parser.add_argument(
        "--positions-root",
        default=str(_DATA_ROOT / "fixtures" / "positions" / "unicaja"),
        help="Ruta carpeta con CSV de posiciones Unicaja.",
    )
    parser.add_argument(
        "--curves-path",
        default=str(_default_curve_file()),
        help="Ruta fichero de curvas forwards.",
    )
    parser.add_argument(
        "--analysis-date",
        default="2024-11-30",
        help="Fecha de analisis YYYY-MM-DD.",
    )
    parser.add_argument(
        "--curve-base",
        default="ACT/360",
        help="Base de curvas (ACT/360 o ACT/365).",
    )
    parser.add_argument(
        "--curve-sheet",
        default="0",
        help="Hoja de curvas (indice o nombre).",
    )
    parser.add_argument(
        "--risk-free-index",
        default="EUR_ESTR_OIS",
        help="Indice risk-free para shocks/renovacion.",
    )
    parser.add_argument(
        "--currency",
        default="EUR",
        help="Divisa para shocks regulatorios.",
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=["parallel-up", "parallel-down"],
        help="Escenarios regulatorios NII.",
    )
    parser.add_argument(
        "--chart-out",
        default=str(_DATA_ROOT / "out" / "nii_monthly_base_parallel.png"),
        help="Ruta de salida del grafico mensual.",
    )

    args = parser.parse_args()

    positions_root = Path(args.positions_root)
    curves_path = Path(args.curves_path)
    if not positions_root.exists():
        raise FileNotFoundError(f"No existe positions-root: {positions_root}")
    if not curves_path.exists():
        raise FileNotFoundError(f"No existe curves-path: {curves_path}")

    out = run_nii_from_specs(
        positions_root_path=positions_root,
        mapping_module=unicaja_mapping,
        curves_path=curves_path,
        analysis_date=_parse_date(args.analysis_date),
        curve_base=args.curve_base,
        curve_sheet=_parse_sheet(args.curve_sheet),
        risk_free_index=args.risk_free_index,
        currency=args.currency,
        scenario_ids=tuple(args.scenarios),
        build_monthly_chart=True,
        chart_output_path=args.chart_out,
        monthly_chart_scenarios=("base", "parallel-up", "parallel-down"),
    )

    print("=== NII RUN (UNICAJA) ===")
    print(f"positions_root: {positions_root}")
    print(f"curves_path: {curves_path}")
    print(f"analysis_date: {out.analysis_date.isoformat()}")
    print(f"positions_count: {out.positions_count}")
    print(f"scheduled_flows_count: {out.scheduled_flows_count}")
    if out.excluded_source_contract_types:
        print(f"excluded_source_contract_types: {out.excluded_source_contract_types}")
    print()
    print(f"NII base (12M): {out.base_nii_12m:,.2f}")
    for scenario_name, value in out.scenario_nii_12m.items():
        delta = float(value) - float(out.base_nii_12m)
        print(f"NII {scenario_name} (12M): {value:,.2f}  (delta vs base: {delta:,.2f})")
    if out.chart_path is not None:
        print()
        print(f"nii_monthly_chart: {out.chart_path.resolve()}")
    if out.chart_base_vs_worst_path is not None:
        print(f"nii_base_vs_worst_chart: {out.chart_base_vs_worst_path.resolve()}")


if __name__ == "__main__":
    main()
