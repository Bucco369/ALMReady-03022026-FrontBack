"""Bank adapter dataclass — bundles everything the parser needs per bank."""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Any


@dataclass(frozen=True)
class BankAdapter:
    """All bank-specific configuration needed by the ingestion pipeline.

    Each supported bank gets one instance (see per-bank packages under
    ``engine/banks/<bank>/``).  The parser receives this instead of
    importing bank-specific modules directly.
    """

    bank_id: str                        # e.g. "unicaja"
    label: str                          # e.g. "Unicaja"
    mapping_module: ModuleType          # engine.banks.<bank>.mapping
    client_id: str                      # key for balance_config classifier rules
    excluded_contract_types: frozenset[str]  # contract types to skip during ZIP parse

    def get_client_rules(self) -> dict[str, Any]:
        """Load classification rules for this bank (lazy import)."""
        from engine.balance_config.clients import get_client_rules

        return get_client_rules(self.client_id)
