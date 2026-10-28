"""Deterministic rule checks (Requirements 5, 6, 7).

Every check here is exact, so confidence is fixed per issue type. Field values
are read only through :func:`dq_assistant.fields.read`; records are never
modified and no proposed replacement value is ever written into a candidate.
"""

from dq_assistant.fields import INVALID_TYPE, MISSING, PRESENT, is_unbranded, read
from dq_assistant.loader import JSON_NON_OBJECT
from dq_assistant.models import (
    RECORD_FIELDS,
    REQUIRED_FIELDS,
    UOM_ALLOW_LIST,
    make_candidate,
    observed,
)

SOURCE = "deterministic_rule"

_UOM_ALLOWED_UPPER = frozenset(code.upper() for code in UOM_ALLOW_LIST)
_UOM_DISPLAY = ", ".join(sorted(UOM_ALLOW_LIST))

_MANUFACTURER_ACTION = (
    "Confirm the manufacturer with the source owner, or confirm that the item "
    "has no manufacturer and should record UNBRANDED."
)


def run_rules(records) -> list[dict]:
    """Run all deterministic checks over ``records`` (a list of RawRecord)."""
    candidates: list[dict] = []
    for record in records:
        candidates.extend(_check_record(record))
    return candidates


def _check_record(record) -> list[dict]:
    if record.kind == JSON_NON_OBJECT or record.ragged:
        return [_invalid_record(record)]

    classes = {name: read(record, name) for name in RECORD_FIELDS}
    item_status, item_value = classes["item_id"]
    item_id = item_value if item_status == PRESENT else None
    row = record.row_index

    out: list[dict] = []
    for name in RECORD_FIELDS:
        status, _ = classes[name]
        if status == INVALID_TYPE:
            out.append(_invalid_field_type(record, row, item_id, name))
        elif status == MISSING and name in REQUIRED_FIELDS:
            out.append(_missing_required(row, item_id, name))

    part = _missing_part_number(row, item_id, classes)
    if part is not None:
        out.append(part)
    uom = _unsupported_uom(row, item_id, classes["unit_of_measure"])
    if uom is not None:
        out.append(uom)
    return out


def _invalid_record(record) -> dict:
    if record.kind == JSON_NON_OBJECT:
        detail = "the entry is not a JSON object"
        action = "Check the source export and confirm this entry should be an item record."
    else:
        detail = "the CSV row has more cells than the header has columns"
        action = "Check the source export for unquoted commas and confirm the row's values."
    return make_candidate(
        issue_type="invalid_record",
        row_index=record.row_index,
        item_id=None,
        field=None,
        severity="high",
        confidence=1.0,
        explanation=f"Candidate issue: {detail}, so no other checks were run on it.",
        suggested_action=action,
        source=SOURCE,
    )


def _json_type_name(value) -> str:
    """Name the observed JSON type of a non-string, non-null value."""
    if isinstance(value, bool):  # bool is a subclass of int; check it first
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "list"
    return "object"


def _invalid_field_type(record, row: int, item_id, name: str) -> dict:
    type_name = _json_type_name(record.fields[name])
    return make_candidate(
        issue_type="invalid_field_type",
        row_index=row,
        item_id=item_id,
        field=name,
        severity="medium",
        confidence=1.0,
        explanation=(
            f"Candidate issue: field '{name}' has JSON type {type_name}; "
            "a text value is expected."
        ),
        suggested_action=(
            f"Confirm the correct {name} value with the source owner and check "
            "that it is exported as text."
        ),
        source=SOURCE,
    )


def _missing_required(row: int, item_id, name: str) -> dict:
    if name == "manufacturer":
        action = _MANUFACTURER_ACTION
    elif name == "item_id":
        action = (
            f"Confirm the item ID with the source owner; this record is "
            f"identified by row_index {row}."
        )
    else:
        action = f"Confirm the {name} value with the source owner."
    return make_candidate(
        issue_type="missing_required_field",
        row_index=row,
        item_id=item_id,
        field=name,
        severity="high" if name == "item_id" else "medium",
        confidence=1.0,
        explanation=f"Candidate issue: required field '{name}' is missing or blank.",
        suggested_action=action,
        source=SOURCE,
    )


def _missing_part_number(row: int, item_id, classes: dict) -> dict | None:
    mfr_status, mfr_value = classes["manufacturer"]
    mpn_status, _ = classes["manufacturer_part_number"]
    if mfr_status != PRESENT or is_unbranded(mfr_value) or mpn_status != MISSING:
        return None
    return make_candidate(
        issue_type="missing_part_number",
        row_index=row,
        item_id=item_id,
        field="manufacturer_part_number",
        severity="medium",
        confidence=0.95,
        explanation=(
            "Candidate issue: manufacturer is present but manufacturer part number is missing."
        ),
        suggested_action="Confirm the manufacturer part number with the source owner.",
        source=SOURCE,
    )


def _unsupported_uom(row: int, item_id, uom: tuple) -> dict | None:
    status, value = uom
    if status != PRESENT or value.upper() in _UOM_ALLOWED_UPPER:
        return None
    return make_candidate(
        issue_type="unsupported_unit_of_measure",
        row_index=row,
        item_id=item_id,
        field="unit_of_measure",
        severity="medium",
        confidence=0.9,
        explanation=(
            f"Candidate issue: unit of measure '{observed(value)}' is not in the "
            f"approved list ({_UOM_DISPLAY})."
        ),
        suggested_action=(
            "Confirm the correct unit with the source owner and map the value to "
            "an approved code."
        ),
        source=SOURCE,
    )
