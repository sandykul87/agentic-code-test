"""Field value reader, Missing_Value definition, and normalizers.

This module is the single definition of "missing" (Requirement 4). It only
reads records; it never writes back to them.
"""

import re
from collections.abc import Mapping
from typing import Any

PRESENT = "present"
MISSING = "missing"
INVALID_TYPE = "invalid_type"

_PLACEHOLDERS = frozenset({"", "null", "none", "n/a"})
_MPN_SEPARATORS = re.compile(r"[\s\-./_]+")


def _fields_of(record: Any) -> Mapping:
    """Return the field mapping of a plain mapping or a RawRecord-like object."""
    if isinstance(record, Mapping):
        return record
    return record.fields


def read(record: Any, field: str) -> tuple[str, str | None]:
    """Classify ``field`` of ``record`` and return (classification, trimmed value).

    The value is returned only for PRESENT; otherwise it is None.
    """
    fields = _fields_of(record)
    if field not in fields:
        return MISSING, None
    value = fields[field]
    if value is None:
        return MISSING, None
    if not isinstance(value, str):
        return INVALID_TYPE, None
    trimmed = value.strip()
    if trimmed.lower() in _PLACEHOLDERS:
        return MISSING, None
    return PRESENT, trimmed


def is_unbranded(manufacturer_value: str) -> bool:
    """True when the value is the Unbranded_Sentinel (case-insensitive, trimmed)."""
    return manufacturer_value.strip().lower() == "unbranded"


def normalize_text(s: str) -> str:
    """Trim, collapse internal whitespace, and casefold. Comparison only."""
    return " ".join(s.split()).casefold()


def normalize_mpn(s: str) -> str:
    """Upper-case and drop spaces, hyphens, dots, slashes, underscores."""
    return _MPN_SEPARATORS.sub("", s).upper()
