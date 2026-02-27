"""Unified bank registry.

To add a new bank:
  1. Create ``engine/banks/<bank>/`` (copy an existing bank as template).
  2. Define ``__init__.py`` exporting an ``ADAPTER`` instance.
  3. Add ``mapping.py``, ``classification.py``, and ``whatif.py``.
  4. Register the module path in ``_REGISTRY`` below.
"""

from __future__ import annotations

import importlib

from engine.banks._base import BankAdapter

__all__ = [
    "BankAdapter",
    "resolve_bank",
    "available_banks",
    "default_bank",
    # Backward-compat alias
    "resolve_adapter",
]

_REGISTRY: dict[str, str] = {
    "unicaja": "engine.banks.unicaja",
    # "bbva": "engine.banks.bbva",
}

_DEFAULT_BANK = "unicaja"


def resolve_bank(bank_id: str) -> BankAdapter:
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


# Backward-compat alias used by app.bank_adapters shim.
resolve_adapter = resolve_bank


def available_banks() -> list[str]:
    """Return registered bank IDs."""
    return sorted(_REGISTRY.keys())


def default_bank() -> str:
    """Return the default bank ID."""
    return _DEFAULT_BANK
