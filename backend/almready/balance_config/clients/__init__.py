"""
Client registry for balance classification rules.

Each client module must export:
  - ASSET_RULES:      list[tuple[str, str]]
  - LIABILITY_RULES:  list[tuple[str, str]]
  - DERIVATIVE_RULES: list[tuple[str, str]]

To add a new client:
  1. Create a module in this package (e.g. ``bbva.py``)
  2. Define the three *_RULES lists (copy unicaja.py as template)
  3. Register the module path in ``_CLIENT_MODULES`` below
"""

from __future__ import annotations

from typing import Any

_CLIENT_MODULES: dict[str, str] = {
    "unicaja": "almready.balance_config.clients.unicaja",
    # "bbva": "almready.balance_config.clients.bbva",
    # "santander": "almready.balance_config.clients.santander",
}


def get_client_rules(client_id: str) -> dict[str, Any]:
    """
    Load classification rules for a given client.

    Returns a dict with keys ``asset_rules``, ``liability_rules``,
    ``derivative_rules`` — ready to unpack into ``classify_position()``.
    """
    import importlib

    module_path = _CLIENT_MODULES.get(client_id.lower())
    if module_path is None:
        raise ValueError(
            f"Unknown balance_config client: '{client_id}'. "
            f"Available: {sorted(_CLIENT_MODULES.keys())}"
        )

    mod = importlib.import_module(module_path)
    return {
        "asset_rules": getattr(mod, "ASSET_RULES", []),
        "liability_rules": getattr(mod, "LIABILITY_RULES", []),
        "derivative_rules": getattr(mod, "DERIVATIVE_RULES", []),
    }


def available_clients() -> list[str]:
    """Return registered client IDs."""
    return sorted(_CLIENT_MODULES.keys())
