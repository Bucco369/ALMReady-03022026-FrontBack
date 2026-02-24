"""Shared IO utilities for mapping access, glob resolution, and token helpers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd


def mapping_attr(mapping_module: Any, attr_name: str) -> Any:
    """Get a required attribute from a mapping module or dict; raises on missing."""
    if isinstance(mapping_module, Mapping):
        if attr_name not in mapping_module:
            raise ValueError(f"mapping_module sin clave requerida: {attr_name}")
        return mapping_module[attr_name]

    if not hasattr(mapping_module, attr_name):
        raise ValueError(f"mapping_module sin atributo requerido: {attr_name}")
    return getattr(mapping_module, attr_name)


def mapping_attr_optional(mapping_module: Any, attr_name: str, default: Any) -> Any:
    """Get an optional attribute from a mapping module or dict; returns default."""
    if isinstance(mapping_module, Mapping):
        return mapping_module.get(attr_name, default)
    return getattr(mapping_module, attr_name, default)


def to_sequence(value: Any) -> list[Any]:
    """Wrap scalars in a list; pass lists/tuples through."""
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def resolve_glob_matches(root_path: Path, pattern: str) -> list[Path]:
    """Resolve a glob pattern relative to *root_path*, returning sorted file matches."""
    return sorted(p for p in root_path.glob(pattern) if p.is_file())


def norm_header(value: Any) -> str:
    """Normalise a column header for fuzzy matching (upper, strip whitespace/punctuation)."""
    s = str(value).strip().upper()
    return s.replace(" ", "").replace("_", "").replace("-", "")


def norm_token(value: Any) -> str | None:
    """Normalise a cell value to a stripped string, or None if blank/NaN."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    return s if s else None


def parse_number(value: Any, *, allow_percent: bool = False) -> float | None:
    """Parse a numeric value with flexible decimal/thousand separators."""
    if pd.isna(value):
        return None

    s = str(value).strip()
    if s == "":
        return None

    has_percent = "%" in s
    s = s.replace("%", "").replace(" ", "")

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")

    try:
        v = float(s)
    except ValueError:
        return None

    if allow_percent and has_percent:
        v = v / 100.0

    return v


def parse_date(value: Any, *, dayfirst: bool) -> Any:
    """Parse a date value; returns datetime.date or None."""
    if pd.isna(value):
        return None
    dt = pd.to_datetime(value, errors="coerce", dayfirst=dayfirst)
    if pd.isna(dt):
        return None
    return dt.date()
