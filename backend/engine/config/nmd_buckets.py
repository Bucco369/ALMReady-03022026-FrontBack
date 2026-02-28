"""
19 EBA time buckets for NMD behavioural cash-flow slotting.

Bucket IDs match the frontend definition in BehaviouralContext.tsx.
Midpoints are in years — used to compute flow_date = analysis_date + midpoint.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NMDBucket:
    id: str
    label: str
    midpoint_years: float


NMD_BUCKETS: tuple[NMDBucket, ...] = (
    NMDBucket("ON",       "O/N",        0.003),
    NMDBucket("ON_1M",    ">O/N–1M",    0.042),
    NMDBucket("1M_3M",    ">1M–3M",     0.167),
    NMDBucket("3M_6M",    ">3M–6M",     0.375),
    NMDBucket("6M_9M",    ">6M–9M",     0.625),
    NMDBucket("9M_1Y",    ">9M–1Y",     0.875),
    NMDBucket("1Y_1H",    ">1Y–1.5Y",   1.25),
    NMDBucket("1H_2Y",    ">1.5Y–2Y",   1.75),
    NMDBucket("2Y_3Y",    ">2Y–3Y",     2.5),
    NMDBucket("3Y_4Y",    ">3Y–4Y",     3.5),
    NMDBucket("4Y_5Y",    ">4Y–5Y",     4.5),
    NMDBucket("5Y_6Y",    ">5Y–6Y",     5.5),
    NMDBucket("6Y_7Y",    ">6Y–7Y",     6.5),
    NMDBucket("7Y_8Y",    ">7Y–8Y",     7.5),
    NMDBucket("8Y_9Y",    ">8Y–9Y",     8.5),
    NMDBucket("9Y_10Y",   ">9Y–10Y",    9.5),
    NMDBucket("10Y_15Y",  ">10Y–15Y",   12.5),
    NMDBucket("15Y_20Y",  ">15Y–20Y",   17.5),
    NMDBucket("20Y_PLUS", ">20Y",       25.0),
)

# Quick lookup: bucket_id → NMDBucket
NMD_BUCKET_MAP: dict[str, NMDBucket] = {b.id: b for b in NMD_BUCKETS}
