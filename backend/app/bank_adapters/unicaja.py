"""Unicaja bank adapter."""

from __future__ import annotations

from engine.config import bank_mapping_unicaja

from app.bank_adapters._base import BankAdapter

ADAPTER = BankAdapter(
    bank_id="unicaja",
    label="Unicaja",
    mapping_module=bank_mapping_unicaja,
    client_id="unicaja",
    excluded_contract_types=frozenset({"fixed_scheduled", "variable_scheduled"}),
)
