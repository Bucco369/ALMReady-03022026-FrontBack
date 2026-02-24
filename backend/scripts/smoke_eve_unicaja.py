from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parents[1]   # backend/
_REPO_ROOT = _PROJECT_ROOT.parent                     # repository root
_DATA_ROOT = _REPO_ROOT.parent / "data"               # ../data/ (sibling of repo)
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.config import bank_mapping_unicaja as unicaja_mapping
from engine.services.eve_pipeline import run_eve_from_specs


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
        description="Runner EVE para Unicaja (base + escenarios regulatorios)."
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
        help="Indice risk-free para descuento.",
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
        help="Escenarios regulatorios a ejecutar.",
    )
    parser.add_argument(
        "--method",
        choices=["exact", "bucketed"],
        default="exact",
        help="Metodo EVE: exact flujo a flujo o bucketed.",
    )
    parser.add_argument(
        "--open-ended-bucket-years",
        type=float,
        default=10.0,
        help="Anchos de referencia para bucket abierto en modo bucketed.",
    )
    parser.add_argument(
        "--no-preserve-basis",
        action="store_true",
        help="Si se informa, no preserva basis en curvas no risk-free.",
    )
    parser.add_argument(
        "--no-post-shock-floor",
        action="store_true",
        help="Si se informa, desactiva floor post-shock regulatorio.",
    )
    parser.add_argument(
        "--no-charts",
        action="store_true",
        help="Si se informa, no genera graficos EVE.",
    )
    parser.add_argument(
        "--charts-out-dir",
        default=str(_DATA_ROOT / "out"),
        help="Directorio de salida para PNG de EVE.",
    )

    args = parser.parse_args()

    positions_root = Path(args.positions_root)
    curves_path = Path(args.curves_path)
    if not positions_root.exists():
        raise FileNotFoundError(f"No existe positions-root: {positions_root}")
    if not curves_path.exists():
        raise FileNotFoundError(f"No existe curves-path: {curves_path}")

    out = run_eve_from_specs(
        positions_root_path=positions_root,
        mapping_module=unicaja_mapping,
        curves_path=curves_path,
        analysis_date=_parse_date(args.analysis_date),
        curve_base=args.curve_base,
        curve_sheet=_parse_sheet(args.curve_sheet),
        risk_free_index=args.risk_free_index,
        currency=args.currency,
        scenario_ids=tuple(args.scenarios),
        method=args.method,
        open_ended_bucket_years=float(args.open_ended_bucket_years),
        preserve_basis_for_non_risk_free=not bool(args.no_preserve_basis),
        apply_post_shock_floor=not bool(args.no_post_shock_floor),
        build_charts=not bool(args.no_charts),
        charts_output_dir=args.charts_out_dir,
    )

    print("=== EVE RUN (UNICAJA) ===")
    print(f"positions_root: {positions_root}")
    print(f"curves_path: {curves_path}")
    print(f"analysis_date: {out.analysis_date.isoformat()}")
    print(f"method: {out.method}")
    print(f"positions_count: {out.positions_count}")
    print(f"scheduled_flows_count: {out.scheduled_flows_count}")
    if out.worst_scenario is not None:
        print(f"worst_scenario: {out.worst_scenario}")
    if out.excluded_source_contract_types:
        print(f"excluded_source_contract_types: {out.excluded_source_contract_types}")
    print()
    print(f"EVE base: {out.base_eve:,.2f}")
    for scenario_name, value in out.scenario_eve.items():
        delta = float(value) - float(out.base_eve)
        print(f"EVE {scenario_name}: {value:,.2f}  (delta vs base: {delta:,.2f})")
    if out.chart_paths:
        print()
        print("charts:")
        for key, p in out.chart_paths.items():
            print(f" - {key}: {Path(p).resolve()}")
    if out.table_paths:
        print()
        print("tables:")
        for key, p in out.table_paths.items():
            print(f" - {key}: {Path(p).resolve()}")


if __name__ == "__main__":
    main()
