"""Unicaja bank adapter."""

from __future__ import annotations

from engine.banks.unicaja import mapping
from engine.banks._base import BankAdapter

ADAPTER = BankAdapter(
    bank_id="unicaja",
    label="Unicaja",
    mapping_module=mapping,
    client_id="unicaja",
    excluded_contract_types=frozenset({"fixed_scheduled", "variable_scheduled"}),
)
