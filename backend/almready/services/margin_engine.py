from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
import re

import pandas as pd
from dateutil.relativedelta import relativedelta

from almready.services.market import ForwardCurveSet


_DIMENSIONS = ("source_contract_type", "side", "repricing_freq", "index_name")


def _norm_token(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    s = str(value).strip()
    if s == "":
        return None
    return s


def _norm_rate_type(value: Any) -> str | None:
    token = _norm_token(value)
    if token is None:
        return None
    t = token.lower()
    if t in {"fixed", "float"}:
        return t
    return None


def _parse_frequency_token(value: Any) -> tuple[int, str] | None:
    token = _norm_token(value)
    if token is None:
        return None
    t = token.upper().replace(" ", "")
    if t in {"0D", "0W", "0M", "0Y"}:
        return None
    if t in {"ON", "O/N"}:
        return (1, "D")
    m = re.match(r"^(\d+)([DWMY])$", t)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    if n <= 0:
        return None
    return (n, unit)


def _add_frequency(d: date, frequency: tuple[int, str] | None) -> date:
    if frequency is None:
        return d + relativedelta(years=1)
    n, unit = frequency
    if unit == "D":
        return d + relativedelta(days=n)
    if unit == "W":
        return d + relativedelta(weeks=n)
    if unit == "M":
        return d + relativedelta(months=n)
    if unit == "Y":
        return d + relativedelta(years=n)
    return d + relativedelta(years=1)


def _weighted_average(values: pd.Series, weights: pd.Series) -> float:
    if values.empty:
        raise ValueError("No hay valores para calcular promedio ponderado.")
    w = weights.fillna(0.0).astype(float)
    v = values.astype(float)
    total_w = float(w.sum())
    if total_w <= 0.0:
        return float(v.mean())
    return float((v * w).sum() / total_w)


def _filter_recent_positions(
    positions: pd.DataFrame,
    *,
    as_of_date: date,
    lookback_months: int | None,
    start_date_col: str = "start_date",
) -> pd.DataFrame:
    if lookback_months is None:
        return positions.copy()

    months = int(lookback_months)
    if months <= 0:
        raise ValueError("lookback_months debe ser > 0 o None.")

    if start_date_col not in positions.columns:
        return positions.copy()

    start_series = pd.to_datetime(positions[start_date_col], errors="coerce").dt.date
    window_start = as_of_date - relativedelta(months=months)
    mask = start_series.notna() & (start_series >= window_start) & (start_series <= as_of_date)
    return positions.loc[mask].copy()


@dataclass
class CalibratedMarginSet:
    """
    Tabla agregada de margenes para renovaciones de balance constante.
    """

    table: pd.DataFrame

    def __post_init__(self) -> None:
        if self.table is None:
            self.table = pd.DataFrame()
        if self.table.empty:
            self.table = pd.DataFrame(columns=["rate_type", *_DIMENSIONS, "margin_rate", "weight"])
            return

        required = {"rate_type", "margin_rate"}
        missing = sorted(required - set(self.table.columns))
        if missing:
            raise ValueError(f"CalibratedMarginSet.table sin columnas requeridas: {missing}")

        df = self.table.copy()
        for c in ("rate_type", *_DIMENSIONS):
            if c not in df.columns:
                df[c] = pd.NA
        if "weight" not in df.columns:
            df["weight"] = 1.0

        df["rate_type"] = df["rate_type"].astype("string").str.strip().str.lower()
        df["margin_rate"] = pd.to_numeric(df["margin_rate"], errors="coerce")
        df["weight"] = pd.to_numeric(df["weight"], errors="coerce").fillna(0.0)
        for c in _DIMENSIONS:
            df[c] = df[c].astype("string").str.strip()
            df[c] = df[c].replace({"": pd.NA})

        df = df[df["rate_type"].isin(["fixed", "float"]) & df["margin_rate"].notna()].copy()
        self.table = df.reset_index(drop=True)

    def lookup_margin(
        self,
        *,
        rate_type: str,
        source_contract_type: str | None = None,
        side: str | None = None,
        repricing_freq: str | None = None,
        index_name: str | None = None,
        default: float | None = None,
    ) -> float:
        if self.table.empty:
            if default is None:
                raise KeyError("CalibratedMarginSet vacio y sin default para lookup.")
            return float(default)

        req = {
            "source_contract_type": _norm_token(source_contract_type),
            "side": _norm_token(side),
            "repricing_freq": _norm_token(repricing_freq),
            "index_name": _norm_token(index_name),
        }
        rt = str(rate_type).strip().lower()
        if rt not in {"fixed", "float"}:
            if default is None:
                raise KeyError(f"rate_type invalido en lookup_margin: {rate_type!r}")
            return float(default)

        df = self.table[self.table["rate_type"] == rt].copy()
        if df.empty:
            if default is None:
                raise KeyError(f"Sin margenes para rate_type={rt!r}")
            return float(default)

        profiles: list[tuple[str, ...]] = [
            ("source_contract_type", "side", "repricing_freq", "index_name"),
            ("source_contract_type", "side", "repricing_freq"),
            ("source_contract_type", "repricing_freq"),
            ("source_contract_type", "side"),
            ("source_contract_type",),
            ("repricing_freq",),
            tuple(),
        ]

        for dims in profiles:
            if any(req[d] is None for d in dims):
                continue

            sub = df.copy()
            ok = True
            for d in dims:
                sub = sub[sub[d].astype("string") == str(req[d])]
                if sub.empty:
                    ok = False
                    break
            if not ok or sub.empty:
                continue

            return _weighted_average(sub["margin_rate"], sub["weight"])

        if default is not None:
            return float(default)
        raise KeyError(
            "No se encontro margen para lookup con request="
            f"(rate_type={rt!r}, source_contract_type={req['source_contract_type']!r}, "
            f"side={req['side']!r}, repricing_freq={req['repricing_freq']!r}, "
            f"index_name={req['index_name']!r})"
        )


def calibrate_margin_set(
    recent_positions: pd.DataFrame,
    *,
    curve_set: ForwardCurveSet,
    risk_free_index: str = "EUR_ESTR_OIS",
    as_of: date | None = None,
    lookback_months: int | None = 12,
    start_date_col: str = "start_date",
) -> CalibratedMarginSet:
    """
    Calibra margenes para renovacion usando datos recientes comparables.

    - fixed: margin = fixed_rate - rf(benchmark_date)
        * con repricing_freq: benchmark_date = as_of + repricing_freq
        * sin repricing_freq: benchmark_date = as_of + plazo original (maturity - start)
        * fallback si faltan fechas: benchmark_date = as_of + 1Y
    - float: margin = spread
    """
    if recent_positions.empty:
        return CalibratedMarginSet(pd.DataFrame())

    as_of_date = curve_set.analysis_date if as_of is None else as_of
    recent_positions = _filter_recent_positions(
        recent_positions,
        as_of_date=as_of_date,
        lookback_months=lookback_months,
        start_date_col=start_date_col,
    )
    if recent_positions.empty:
        return CalibratedMarginSet(pd.DataFrame())

    rows: list[dict[str, Any]] = []

    for row in recent_positions.itertuples(index=False):
        rt = _norm_rate_type(getattr(row, "rate_type", None))
        if rt is None:
            continue

        _notional_raw = getattr(row, "notional", "")
        weight = float(abs(float(_notional_raw))) if str(_notional_raw).strip() != "" else 1.0
        if weight <= 0.0:
            weight = 1.0

        source_contract_type = _norm_token(getattr(row, "source_contract_type", None))
        side = _norm_token(getattr(row, "side", None))
        repricing_freq = _norm_token(getattr(row, "repricing_freq", None))
        index_name = _norm_token(getattr(row, "index_name", None))

        if rt == "fixed":
            _fixed_rate_raw = getattr(row, "fixed_rate", None)
            if pd.isna(_fixed_rate_raw):
                continue
            fixed_rate = float(_fixed_rate_raw)
            freq = _parse_frequency_token(repricing_freq)
            if freq is not None:
                # Tipo fijo con repricing: benchmark al tenor del repricing.
                bench_date = _add_frequency(as_of_date, freq)
            else:
                # Tipo fijo sin repricing (caso habitual): el benchmark se
                # toma al plazo original del contrato (maturity - start) para
                # reflejar el punto de la curva al que se origino la posicion.
                # Ejemplo: prestamo fijo a 20 anos -> rf(20Y), no rf(1Y).
                # Fallback a 1Y solo si faltan fechas.
                sd = pd.to_datetime(getattr(row, "start_date", None), errors="coerce")
                md = pd.to_datetime(getattr(row, "maturity_date", None), errors="coerce")
                if pd.notna(sd) and pd.notna(md) and md > sd:
                    bench_date = as_of_date + (md - sd)
                else:
                    bench_date = _add_frequency(as_of_date, None)  # fallback 1Y
            rf = float(curve_set.rate_on_date(risk_free_index, bench_date))
            margin_rate = fixed_rate - rf
        else:
            _spread_raw = getattr(row, "spread", None)
            if pd.isna(_spread_raw):
                continue
            margin_rate = float(_spread_raw)

        rows.append(
            {
                "rate_type": rt,
                "source_contract_type": source_contract_type,
                "side": side,
                "repricing_freq": repricing_freq,
                "index_name": index_name,
                "margin_rate": float(margin_rate),
                "weight": float(weight),
            }
        )

    if not rows:
        return CalibratedMarginSet(pd.DataFrame())

    raw = pd.DataFrame(rows)
    grouped = (
        raw.groupby(["rate_type", *_DIMENSIONS], dropna=False, as_index=False)
        .apply(lambda g: pd.Series({"margin_rate": _weighted_average(g["margin_rate"], g["weight"]), "weight": float(g["weight"].sum())}))
        .reset_index(drop=True)
    )
    return CalibratedMarginSet(grouped)


def load_margin_set_csv(path: str | Path) -> CalibratedMarginSet:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"No existe fichero de margenes: {p}")
    df = pd.read_csv(p)
    return CalibratedMarginSet(df)


def save_margin_set_csv(margin_set: CalibratedMarginSet, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    margin_set.table.to_csv(p, index=False)
    return p
