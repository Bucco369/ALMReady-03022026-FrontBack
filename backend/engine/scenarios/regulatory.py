from __future__ import annotations

from dataclasses import dataclass
from math import exp
from typing import Mapping

# Escenarios oficiales (Art. 1 y 2 del Reglamento Delegado (UE) 2024/856).
EVE_REGULATORY_SCENARIO_IDS: tuple[str, ...] = (
    "parallel-up",
    "parallel-down",
    "short-up",
    "short-down",
    "steepener",
    "flattener",
)
NII_REGULATORY_SCENARIO_IDS: tuple[str, ...] = (
    "parallel-up",
    "parallel-down",
)

# Soporte interno opcional (no oficial SOT): long-up/down.
_EXTENDED_INTERNAL_SCENARIOS: tuple[str, ...] = (
    "long-up",
    "long-down",
)

SUPPORTED_SCENARIO_IDS: tuple[str, ...] = (
    *EVE_REGULATORY_SCENARIO_IDS,
    *_EXTENDED_INTERNAL_SCENARIOS,
)


@dataclass(frozen=True)
class RegulatoryShockParameters:
    parallel: float
    short: float
    long: float


@dataclass(frozen=True)
class PostShockFloorParameters:
    immediate_floor: float = -0.015
    annual_step: float = 0.0003
    max_floor: float = 0.0


@dataclass(frozen=True)
class CurrencyShockBps:
    parallel: int
    short: int
    long: int


# Annex Part A del Reglamento (UE) 2024/856 (valores en bps).
ANNEX_PART_A_SHOCKS_BPS: dict[str, CurrencyShockBps] = {
    "ARS": CurrencyShockBps(parallel=400, short=500, long=300),
    "AUD": CurrencyShockBps(parallel=300, short=450, long=200),
    "BGN": CurrencyShockBps(parallel=250, short=350, long=150),
    "BRL": CurrencyShockBps(parallel=400, short=500, long=300),
    "CAD": CurrencyShockBps(parallel=200, short=300, long=150),
    "CHF": CurrencyShockBps(parallel=100, short=150, long=100),
    "CNY": CurrencyShockBps(parallel=250, short=300, long=150),
    "CZK": CurrencyShockBps(parallel=200, short=250, long=100),
    "DKK": CurrencyShockBps(parallel=200, short=250, long=150),
    "EUR": CurrencyShockBps(parallel=200, short=250, long=100),
    "GBP": CurrencyShockBps(parallel=250, short=300, long=150),
    "HKD": CurrencyShockBps(parallel=200, short=250, long=100),
    "HUF": CurrencyShockBps(parallel=300, short=450, long=200),
    "IDR": CurrencyShockBps(parallel=400, short=500, long=350),
    "INR": CurrencyShockBps(parallel=400, short=500, long=300),
    "JPY": CurrencyShockBps(parallel=100, short=100, long=100),
    "KRW": CurrencyShockBps(parallel=300, short=400, long=200),
    "MXN": CurrencyShockBps(parallel=400, short=500, long=300),
    "PLN": CurrencyShockBps(parallel=250, short=350, long=150),
    "RON": CurrencyShockBps(parallel=350, short=500, long=250),
    "RUB": CurrencyShockBps(parallel=400, short=500, long=300),
    "SAR": CurrencyShockBps(parallel=200, short=300, long=150),
    "SEK": CurrencyShockBps(parallel=200, short=300, long=150),
    "SGD": CurrencyShockBps(parallel=150, short=200, long=100),
    "TRY": CurrencyShockBps(parallel=400, short=500, long=300),
    "USD": CurrencyShockBps(parallel=200, short=300, long=150),
    "ZAR": CurrencyShockBps(parallel=400, short=500, long=300),
}

DEFAULT_FLOOR_PARAMETERS = PostShockFloorParameters()


def shock_parameters_for_currency(currency: str) -> RegulatoryShockParameters:
    code = str(currency).strip().upper()
    if code not in ANNEX_PART_A_SHOCKS_BPS:
        available = sorted(ANNEX_PART_A_SHOCKS_BPS.keys())
        raise KeyError(
            f"Divisa sin parametros en Annex Part A: {code!r}. Disponibles: {available}"
        )

    v = ANNEX_PART_A_SHOCKS_BPS[code]
    return RegulatoryShockParameters(
        parallel=float(v.parallel) / 10000.0,
        short=float(v.short) / 10000.0,
        long=float(v.long) / 10000.0,
    )


def maturity_post_shock_floor(
    t_years: float,
    *,
    floor_parameters: PostShockFloorParameters = DEFAULT_FLOOR_PARAMETERS,
) -> float:
    t = max(0.0, float(t_years))
    floor_value = floor_parameters.immediate_floor + floor_parameters.annual_step * t
    return min(floor_parameters.max_floor, floor_value)


def _scenario_delta(
    t_years: float,
    scenario_id: str,
    *,
    shock_parameters: RegulatoryShockParameters,
) -> float:
    t = max(0.0, float(t_years))
    sid = str(scenario_id).strip().lower()

    delta_short = shock_parameters.short * exp(-t / 4.0)
    delta_long = shock_parameters.long * (1.0 - exp(-t / 4.0))

    if sid == "parallel-up":
        return shock_parameters.parallel
    if sid == "parallel-down":
        return -shock_parameters.parallel
    if sid == "short-up":
        return delta_short
    if sid == "short-down":
        return -delta_short
    if sid == "long-up":
        return delta_long
    if sid == "long-down":
        return -delta_long
    if sid == "steepener":
        return (-0.65 * abs(delta_short)) + (0.9 * abs(delta_long))
    if sid == "flattener":
        return (+0.8 * abs(delta_short)) - (0.6 * abs(delta_long))

    available = sorted(SUPPORTED_SCENARIO_IDS)
    raise ValueError(f"Escenario no soportado: {scenario_id!r}. Disponibles: {available}")


def apply_regulatory_shock_rate(
    base_rate: float,
    t_years: float,
    scenario_id: str,
    *,
    shock_parameters: RegulatoryShockParameters,
    apply_post_shock_floor: bool = True,
    floor_parameters: PostShockFloorParameters = DEFAULT_FLOOR_PARAMETERS,
) -> float:
    """
    Aplica shock regulatorio sobre la risk-free:
    - Formula de escenarios Art. 2.
    - Floor post-shock de Art. 3(7), con regla de observed lower rate.
    """
    base_rate = float(base_rate)
    shocked = base_rate + _scenario_delta(
        t_years=t_years,
        scenario_id=scenario_id,
        shock_parameters=shock_parameters,
    )

    if not apply_post_shock_floor:
        return shocked

    floor_curve_value = maturity_post_shock_floor(
        t_years=t_years,
        floor_parameters=floor_parameters,
    )
    effective_floor = min(floor_curve_value, base_rate)
    return max(shocked, effective_floor)


def is_regulatory_scenario_id(value: str) -> bool:
    return str(value).strip().lower() in set(SUPPORTED_SCENARIO_IDS)


def build_scenario_set(
    purpose: str,
    *,
    include_internal_extended: bool = False,
) -> tuple[str, ...]:
    """
    Devuelve escenarios por proposito:
    - purpose="eve": 6 oficiales
    - purpose="nii": 2 oficiales
    """
    p = str(purpose).strip().lower()
    if p == "eve":
        base_set = EVE_REGULATORY_SCENARIO_IDS
    elif p == "nii":
        base_set = NII_REGULATORY_SCENARIO_IDS
    else:
        raise ValueError("purpose debe ser 'eve' o 'nii'")

    if include_internal_extended:
        return (*base_set, *_EXTENDED_INTERNAL_SCENARIOS)
    return base_set


def override_shock_parameters(
    base_parameters: RegulatoryShockParameters,
    *,
    parallel: float | None = None,
    short: float | None = None,
    long: float | None = None,
) -> RegulatoryShockParameters:
    """
    Utilidad para cambios regulatorios futuros sin romper API.
    """
    return RegulatoryShockParameters(
        parallel=base_parameters.parallel if parallel is None else float(parallel),
        short=base_parameters.short if short is None else float(short),
        long=base_parameters.long if long is None else float(long),
    )


def shock_parameters_from_mapping(
    mapping: Mapping[str, float],
) -> RegulatoryShockParameters:
    required = {"parallel", "short", "long"}
    missing = sorted(required - set(mapping.keys()))
    if missing:
        raise ValueError(f"Faltan claves en mapping de shocks: {missing}")
    return RegulatoryShockParameters(
        parallel=float(mapping["parallel"]),
        short=float(mapping["short"]),
        long=float(mapping["long"]),
    )
