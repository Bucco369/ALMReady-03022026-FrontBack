"""Shared EVE utilities: EVEBucket dataclass and bucket normalisation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EVEBucket:
    name: str
    start_years: float
    end_years: float | None = None

    def contains(self, t_years: float) -> bool:
        t = max(0.0, float(t_years))
        start = max(0.0, float(self.start_years))
        if t < start:
            return False
        if self.end_years is None:
            return True
        return t <= float(self.end_years)

    def representative_t(self, *, open_ended_years: float = 10.0) -> float:
        """Punto medio del bucket, usado para descuento y aplicacion de shocks.

        Para el bucket abierto (>20Y), el default open_ended_years=10.0 produce
        un midpoint de 25 anios (20 + 10/2), alineado con la convencion
        regulatoria BCBS d368 y EBA-GL-2022/14 que asume un rango 20-30Y.
        """
        start = max(0.0, float(self.start_years))
        if self.end_years is None:
            return start + max(0.0, float(open_ended_years)) / 2.0
        end = float(self.end_years)
        return 0.5 * (start + end)


def normalise_buckets(
    buckets: Sequence[EVEBucket | Mapping[str, Any]] | None,
    *,
    default: Sequence[EVEBucket | Mapping[str, Any]],
) -> list[EVEBucket]:
    """Normalise a bucket sequence into a sorted list of EVEBucket objects.

    Parameters
    ----------
    buckets : sequence or None
        User-supplied buckets, or None to use *default*.
    default : sequence
        Fallback bucket sequence when *buckets* is None.
    """
    raw = list(default if buckets is None else buckets)
    if not raw:
        raise ValueError("Se requiere al menos un bucket.")

    out: list[EVEBucket] = []
    for i, b in enumerate(raw, start=1):
        if isinstance(b, EVEBucket):
            candidate = b
        else:
            if not isinstance(b, Mapping):
                raise ValueError(f"Bucket invalido en posicion {i}: {type(b)}")
            candidate = EVEBucket(
                name=str(b.get("name", f"bucket_{i}")),
                start_years=float(b.get("start_years", 0.0)),
                end_years=None if b.get("end_years", None) is None else float(b.get("end_years")),
            )

        if candidate.end_years is not None and float(candidate.end_years) <= float(candidate.start_years):
            raise ValueError(
                f"Bucket con end_years <= start_years: {candidate.name!r} "
                f"({candidate.start_years}, {candidate.end_years})"
            )
        out.append(candidate)

    out = sorted(out, key=lambda x: float(x.start_years))
    return out
