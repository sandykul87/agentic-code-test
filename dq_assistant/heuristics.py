"""Heuristic checks (Requirements 8, 9, and the Requirement 22 slot).

These checks are fuzzy, so they carry confidence below 1.0 and Source
``heuristic``. Field values are read only through
:func:`dq_assistant.fields.read`; records are never modified, and duplicate
candidates only point at related records. Nothing here merges or rewrites data.

Records that get an ``invalid_record`` candidate (non-object JSON entries and
ragged CSV rows) are skipped entirely: they get no heuristic candidate and
never appear in another record's related lists.
"""

from dataclasses import dataclass

from dq_assistant.fields import (
    INVALID_TYPE,
    MISSING,
    PRESENT,
    is_unbranded,
    normalize_mpn,
    normalize_text,
    read,
)
from dq_assistant.loader import JSON_NON_OBJECT
from dq_assistant.models import RECORD_FIELDS, make_candidate, observed

SOURCE = "heuristic"

# Compared fields for conflicting_source_values, in the order Req 9.3 lists them.
COMPARED_FIELDS = (
    "item_description",
    "manufacturer",
    "manufacturer_part_number",
    "category",
    "unit_of_measure",
)

_DESCRIPTION_ACTION = (
    "Check with the source owner and request a fuller description that "
    "includes the item type, the size, and the key attributes."
)
_DUPLICATE_ACTION = (
    "Review the related records with the source owner and decide which one " "is authoritative."
)


@dataclass(frozen=True)
class _View:
    """Read-only, pre-classified view of one checkable record."""

    row: int
    item_id: str | None  # trimmed item_id, or None when missing/invalid
    id_key: str | None  # Normalized_Text item_id, or None when missing/invalid
    system_key: str | None  # Normalized_Text source_system; None = missing/invalid
    values: dict  # field name -> (classification, trimmed value)


def run_heuristics(records) -> list[dict]:
    """Run all heuristic checks over ``records`` (a list of RawRecord)."""
    views = [_view(r) for r in records if not _is_invalid_record(r)]
    candidates: list[dict] = []
    for view in views:
        weak = _weak_description(view)
        if weak is not None:
            candidates.append(weak)
    id_groups = _item_id_groups(views)
    candidates.extend(_duplicate_item_ids(id_groups))
    candidates.extend(_conflicting_source_values(id_groups))
    candidates.extend(_cross_system_duplicates(id_groups))
    candidates.extend(_potential_duplicates(views))
    return candidates


def _is_invalid_record(record) -> bool:
    return record.kind == JSON_NON_OBJECT or record.ragged


def _view(record) -> _View:
    values = {name: read(record, name) for name in RECORD_FIELDS}
    id_status, id_value = values["item_id"]
    ss_status, ss_value = values["source_system"]
    present_id = id_value if id_status == PRESENT else None
    return _View(
        row=record.row_index,
        item_id=present_id,
        id_key=normalize_text(present_id) if present_id is not None else None,
        system_key=normalize_text(ss_value) if ss_status == PRESENT else None,
        values=values,
    )


# --- weak_description (Req 8) ---


def _weak_description(view: _View) -> dict | None:
    status, value = view.values["item_description"]
    if status != PRESENT:  # Req 8.5: missing / invalid type handled elsewhere
        return None
    words = value.split()
    collapsed = " ".join(words)
    word_count, char_count = len(words), len(collapsed)
    if word_count < 3 or char_count < 10:  # Req 8.1 wins over 8.2 (Req 8.3)
        confidence = 0.8
        explanation = (
            "Candidate issue: the description is too short to identify the item "
            f"({word_count} words, {char_count} characters)."
        )
    else:
        short = sum(1 for w in words if len(w) <= 3)
        if short * 2 <= word_count:
            return None
        confidence = 0.6
        explanation = (
            "Candidate issue: the description appears abbreviation-heavy "
            f"({short} of {word_count} words are 3 characters or shorter)."
        )
    return make_candidate(
        issue_type="weak_description",
        row_index=view.row,
        item_id=view.item_id,
        field="item_description",
        severity="low",
        confidence=confidence,
        explanation=explanation,
        suggested_action=_DESCRIPTION_ACTION,
        source=SOURCE,
    )


# --- item_id grouping: duplicate_item_id, conflicting_source_values (Req 9) ---


def _item_id_groups(views: list[_View]) -> list[list[_View]]:
    """Group views by Normalized_Text item_id; drop id-less views (Req 9.11)."""
    groups: dict[str, list[_View]] = {}
    for view in views:
        if view.id_key is not None:
            groups.setdefault(view.id_key, []).append(view)
    return [g for g in groups.values() if len(g) > 1]


def _related(peers: list[_View]) -> list[tuple[int, str | None]]:
    return [(p.row, p.item_id) for p in peers]


def _duplicate_item_ids(id_groups: list[list[_View]]) -> list[dict]:
    out: list[dict] = []
    for group in id_groups:
        for view in group:
            peers = [p for p in group if p is not view and p.system_key == view.system_key]
            if not peers:
                continue
            out.append(
                make_candidate(
                    issue_type="duplicate_item_id",
                    row_index=view.row,
                    item_id=view.item_id,
                    field="item_id",
                    severity="high",
                    confidence=0.95,
                    explanation=(
                        f"Candidate issue: item_id '{observed(view.item_id)}' appears "
                        f"{len(peers) + 1} times in the same source system."
                    ),
                    suggested_action=_DUPLICATE_ACTION,
                    source=SOURCE,
                    related=_related(peers),
                )
            )
    return out


def _other_system_peers(view: _View, group: list[_View]) -> list[_View]:
    return [p for p in group if p.system_key != view.system_key]


def _field_differs(a: tuple, b: tuple, name: str) -> bool | None:
    """Compare one field of two records per Req 9.4; None means skipped."""
    (a_status, a_value), (b_status, b_value) = a, b
    if a_status == INVALID_TYPE or b_status == INVALID_TYPE:
        return None
    if a_status == MISSING or b_status == MISSING:
        return a_status != b_status
    norm = normalize_mpn if name == "manufacturer_part_number" else normalize_text
    return norm(a_value) != norm(b_value)


def _differing_fields(view: _View, peers: list[_View]) -> list[str]:
    """Compared fields that differ between ``view`` and at least one peer."""
    return [
        name
        for name in COMPARED_FIELDS
        if any(_field_differs(view.values[name], p.values[name], name) for p in peers)
    ]


def _conflicting_source_values(id_groups: list[list[_View]]) -> list[dict]:
    out: list[dict] = []
    for group in id_groups:
        for view in group:
            peers = _other_system_peers(view, group)
            if not peers:
                continue
            differing = _differing_fields(view, peers)
            if not differing:  # Req 9.5: identical copies belong to Req 22
                continue
            out.append(
                make_candidate(
                    issue_type="conflicting_source_values",
                    row_index=view.row,
                    item_id=view.item_id,
                    field=None,
                    severity="medium",
                    confidence=0.85,
                    explanation=(
                        f"Candidate issue: item_id '{observed(view.item_id)}' appears "
                        "in another source system with different values in: "
                        f"{', '.join(differing)}."
                    ),
                    suggested_action=_DUPLICATE_ACTION,
                    source=SOURCE,
                    related=_related(peers),
                )
            )
    return out


def _cross_system_duplicates(id_groups: list[list[_View]]) -> list[dict]:
    """Requirement 22 slot (lower priority, implemented in a later task).

    Will flag records whose other-system peers all match on the compared
    fields, i.e. records with peers but no ``_differing_fields``. Until then it
    yields no candidates, as Requirement 22 criterion 7 allows.
    """
    return []


# --- potential_duplicate: same manufacturer + Normalized_MPN (Req 9.7–9.11) ---


def _part_number_key(view: _View) -> tuple[str, str] | None:
    mfr_status, mfr = view.values["manufacturer"]
    mpn_status, mpn = view.values["manufacturer_part_number"]
    if mfr_status != PRESENT or mpn_status != PRESENT or is_unbranded(mfr):
        return None
    norm_mpn = normalize_mpn(mpn)
    if not norm_mpn:
        return None
    return normalize_text(mfr), norm_mpn


def _potential_duplicates(views: list[_View]) -> list[dict]:
    buckets: dict[tuple[str, str], list[_View]] = {}
    for view in views:
        key = _part_number_key(view)
        if key is not None:
            buckets.setdefault(key, []).append(view)
    out: list[dict] = []
    for group in buckets.values():
        if len({v.id_key for v in group}) < 2:  # needs different item_ids (Req 9.7)
            continue
        raw_mpns = {v.values["manufacturer_part_number"][1] for v in group}
        exact = len(raw_mpns) == 1
        detail = "the same part number" if exact else "part numbers that differ only in format"
        for view in group:
            peers = [p for p in group if p is not view]
            out.append(
                make_candidate(
                    issue_type="potential_duplicate",
                    row_index=view.row,
                    item_id=view.item_id,
                    field="manufacturer_part_number",
                    severity="medium",
                    confidence=0.9 if exact else 0.75,
                    explanation=(
                        "Candidate issue: potential duplicate; this record shares "
                        f"its manufacturer and {detail} with {len(peers)} other "
                        "record(s), at least one under a different item_id."
                    ),
                    suggested_action=_DUPLICATE_ACTION,
                    source=SOURCE,
                    related=_related(peers),
                )
            )
    return out
