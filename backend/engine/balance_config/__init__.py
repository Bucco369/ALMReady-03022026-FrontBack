"""
balance_config – Balance classification module for ALMReady.

**Single source of truth** for:
  - Balance tree structure (categories, subcategories, display order)
  - Position classification rules (per client)
  - Subcategory labels and identifiers

Quick start::

    from engine.balance_config import classify_position
    from engine.balance_config.clients import get_client_rules
    from engine.balance_config.schema import SUBCATEGORY_LABELS

    rules = get_client_rules("unicaja")
    result = classify_position(
        apartado="A",
        producto="HIPOTECARIOS COMPRADOR DIRECTO",
        **rules,
    )
    # result.side           == "asset"
    # result.subcategory_id == "mortgages"

To add a new client:
  1. Create ``balance_config/clients/<name>.py`` (copy unicaja.py as template)
  2. Register in ``balance_config/clients/__init__.py``
"""

from engine.balance_config.classifier import (
    ClassificationResult,
    classify_position,
)
from engine.balance_config.clients import get_client_rules
from engine.balance_config.schema import (
    ASSET_DEFAULT,
    ASSET_SUBCATEGORY_ORDER,
    LIABILITY_DEFAULT,
    LIABILITY_SUBCATEGORY_ORDER,
    SIDE_CATEGORIA_UI,
    SUBCATEGORY_LABELS,
)

__all__ = [
    "ClassificationResult",
    "classify_position",
    "get_client_rules",
    "ASSET_DEFAULT",
    "ASSET_SUBCATEGORY_ORDER",
    "LIABILITY_DEFAULT",
    "LIABILITY_SUBCATEGORY_ORDER",
    "SIDE_CATEGORIA_UI",
    "SUBCATEGORY_LABELS",
]
