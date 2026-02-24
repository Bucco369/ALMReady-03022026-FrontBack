from __future__ import annotations

"""
Buckets temporales para EVE en modo bucketed.

Se definen de forma declarativa para poder cambiarlos sin tocar el motor.
Unidad: anios.
"""


DEFAULT_REGULATORY_BUCKETS: tuple[dict[str, float | str | None], ...] = (
    {"name": "0-1M", "start_years": 0.0, "end_years": 1.0 / 12.0},
    {"name": "1-3M", "start_years": 1.0 / 12.0, "end_years": 3.0 / 12.0},
    {"name": "3-6M", "start_years": 3.0 / 12.0, "end_years": 6.0 / 12.0},
    {"name": "6-9M", "start_years": 6.0 / 12.0, "end_years": 9.0 / 12.0},
    {"name": "9-12M", "start_years": 9.0 / 12.0, "end_years": 1.0},
    {"name": "1-1.5Y", "start_years": 1.0, "end_years": 1.5},
    {"name": "1.5-2Y", "start_years": 1.5, "end_years": 2.0},
    {"name": "2-3Y", "start_years": 2.0, "end_years": 3.0},
    {"name": "3-4Y", "start_years": 3.0, "end_years": 4.0},
    {"name": "4-5Y", "start_years": 4.0, "end_years": 5.0},
    {"name": "5-6Y", "start_years": 5.0, "end_years": 6.0},
    {"name": "6-7Y", "start_years": 6.0, "end_years": 7.0},
    {"name": "7-8Y", "start_years": 7.0, "end_years": 8.0},
    {"name": "8-9Y", "start_years": 8.0, "end_years": 9.0},
    {"name": "9-10Y", "start_years": 9.0, "end_years": 10.0},
    {"name": "10-15Y", "start_years": 10.0, "end_years": 15.0},
    {"name": "15-20Y", "start_years": 15.0, "end_years": 20.0},
    {"name": "20Y+", "start_years": 20.0, "end_years": None},
)


# Rejilla recomendada para visualizacion ALCO:
# - mas detalle en corto plazo (<1Y)
# - granularidad progresiva en tramos largos
EVE_VIS_BUCKETS_OPTIMAL: tuple[dict[str, float | str | None], ...] = (
    {"name": "0-1M", "start_years": 0.0, "end_years": 1.0 / 12.0},
    {"name": "1-3M", "start_years": 1.0 / 12.0, "end_years": 3.0 / 12.0},
    {"name": "3-6M", "start_years": 3.0 / 12.0, "end_years": 6.0 / 12.0},
    {"name": "6-12M", "start_years": 6.0 / 12.0, "end_years": 1.0},
    {"name": "1-2Y", "start_years": 1.0, "end_years": 2.0},
    {"name": "2-3Y", "start_years": 2.0, "end_years": 3.0},
    {"name": "3-5Y", "start_years": 3.0, "end_years": 5.0},
    {"name": "5-7Y", "start_years": 5.0, "end_years": 7.0},
    {"name": "7-10Y", "start_years": 7.0, "end_years": 10.0},
    {"name": "10-15Y", "start_years": 10.0, "end_years": 15.0},
    {"name": "15-20Y", "start_years": 15.0, "end_years": 20.0},
    {"name": "20-30Y", "start_years": 20.0, "end_years": 30.0},
    {"name": "30-40Y", "start_years": 30.0, "end_years": 40.0},
    {"name": "40-50Y", "start_years": 40.0, "end_years": 50.0},
    {"name": "50Y+", "start_years": 50.0, "end_years": None},
)
