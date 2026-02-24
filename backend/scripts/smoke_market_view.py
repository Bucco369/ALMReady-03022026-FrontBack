from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parents[1]   # backend/
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.services.market import load_forward_curve_set


def _parse_sheet(value: str):
    s = str(value).strip()
    return int(s) if s.isdigit() else s


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Fecha invalida '{value}'. Usa formato YYYY-MM-DD.") from exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke test de mercado para visualizar carga de curvas."
    )
    parser.add_argument("--path", required=True, help="Ruta del Excel de curvas.")
    parser.add_argument(
        "--analysis-date",
        required=True,
        help="Fecha de analisis en formato YYYY-MM-DD.",
    )
    parser.add_argument(
        "--base",
        default="ACT/360",
        help="Base day count de curvas. Ej: ACT/360, ACT/365.",
    )
    parser.add_argument(
        "--sheet",
        default="0",
        help="Indice o nombre de hoja. Por defecto: 0.",
    )
    parser.add_argument(
        "--index",
        default=None,
        help="IndexName para consulta puntual. Si no se informa, usa el primero.",
    )
    parser.add_argument(
        "--query-date",
        default=None,
        help="Fecha de consulta YYYY-MM-DD. Si no se informa, usa analysis_date + 90d.",
    )
    parser.add_argument(
        "--head",
        type=int,
        default=8,
        help="Numero de filas a mostrar de points.",
    )

    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo de curvas: {path}")

    analysis_date = _parse_date(args.analysis_date)
    sheet = _parse_sheet(args.sheet)

    curve_set = load_forward_curve_set(
        path=str(path),
        analysis_date=analysis_date,
        base=args.base,
        sheet_name=sheet,
    )

    indexes = sorted(curve_set.curves.keys())
    if not indexes:
        raise ValueError("No se han cargado indices de curva.")

    selected_index = args.index if args.index else indexes[0]
    query_date = _parse_date(args.query_date) if args.query_date else analysis_date + timedelta(days=90)

    print("=== MARKET SMOKE VIEW ===")
    print(f"path: {path}")
    print(f"analysis_date: {analysis_date.isoformat()}")
    print(f"base: {args.base}")
    print(f"sheet: {sheet}")
    print(f"indices: {len(indexes)}")
    print(f"points: {len(curve_set.points)}")
    print(f"index_names: {indexes}")
    print()
    print("points head:")
    print(curve_set.points.head(args.head).to_string(index=False))
    print()
    print(f"query index: {selected_index}")
    print(f"query date: {query_date.isoformat()}")
    print(f"rate_on_date: {curve_set.rate_on_date(selected_index, query_date):.8f}")
    print(f"df_on_date: {curve_set.df_on_date(selected_index, query_date):.8f}")


if __name__ == "__main__":
    main()

