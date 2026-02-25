"""Bank adapter registry.

To add a new bank:
  1. Create ``app/bank_adapters/<bank>.py`` (copy ``unicaja.py`` as template).
  2. Register its module path in ``_REGISTRY`` below.
"""

from __future__ import annotations

import importlib

from app.bank_adapters._base import BankAdapter

__all__ = ["BankAdapter", "resolve_adapter", "available_banks", "default_bank"]

_REGISTRY: dict[str, str] = {
    "unicaja": "app.bank_adapters.unicaja",
    # "bbva": "app.bank_adapters.bbva",
}

_DEFAULT_BANK = "unicaja"


def resolve_adapter(bank_id: str) -> BankAdapter:
    """Load and return the adapter for *bank_id*.

    Raises ``ValueError`` with list of available banks on unknown id.
    """
    module_path = _REGISTRY.get(bank_id.lower())
    if module_path is None:
        raise ValueError(
            f"Unknown bank_id: '{bank_id}'. "
            f"Available: {sorted(_REGISTRY.keys())}"
        )
    mod = importlib.import_module(module_path)
    return mod.ADAPTER  # type: ignore[attr-defined]


def available_banks() -> list[str]:
    """Return registered bank IDs."""
    return sorted(_REGISTRY.keys())


def default_bank() -> str:
    """Return the default bank ID."""
    return _DEFAULT_BANK
