from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParallelShock:
    """
    Shock paralelo en basis points para sumar sobre FwdRate.
    """

    name: str
    shift_bps: float

    @property
    def shift_decimal(self) -> float:
        return float(self.shift_bps) / 10000.0

