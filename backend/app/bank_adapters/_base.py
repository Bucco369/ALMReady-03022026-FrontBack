"""Bank adapter dataclass — bundles everything the parser needs per bank."""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType


@dataclass(frozen=True)
class BankAdapter:
    """All bank-specific configuration needed by the ZIP ingestion pipeline.

    Each supported bank gets one instance (see sibling modules).  The parser
    receives this instead of importing bank-specific modules directly.
    """

    bank_id: str                        # e.g. "unicaja"
    label: str                          # e.g. "Unicaja"
    mapping_module: ModuleType          # engine.config.bank_mapping_<bank>
    client_id: str                      # key for balance_config classifier rules
    excluded_contract_types: frozenset[str]  # contract types to skip during ZIP parse
