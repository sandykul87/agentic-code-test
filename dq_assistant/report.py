"""Report assembly: summary, ordering, deterministic JSON, review-language notice.

Builds the Report document (a ``summary`` object plus an ordered ``candidates``
list) and serializes it to byte-identical UTF-8 JSON. Nothing here depends on
the clock, the working directory, or the input path, so repeated runs on the
same inputs produce identical bytes (Requirements 13.2-13.5, 14.1-14.6,
16.1-16.8). Standard library only.
"""

import json

from dq_assistant.models import ISSUE_TYPES, SEVERITIES, SOURCES

REVIEW_NOTICE = (
    "All findings are candidate issues that need human review by a data "
    "steward. No input data was modified."
)

# Deterministic key orders for the count maps (Req 13.4, 16.4).
_ISSUE_TYPE_ORDER = tuple(sorted(ISSUE_TYPES))
_SEVERITY_ORDER = tuple(sorted(SEVERITIES))
_SOURCE_ORDER = tuple(sorted(SOURCES))


def _candidate_sort_key(candidate: dict) -> tuple:
    """Order by row_index, then issue_type, then field with null field first.

    A ``None`` field sorts before any named field (Req 13.5); the leading flag
    (0 for null, 1 otherwise) encodes that, and the field name itself is only
    compared when both fields are present.
    """
    field_value = candidate["field"]
    field_is_present = field_value is not None
    return (
        candidate["row_index"],
        candidate["issue_type"],
        field_is_present,
        field_value if field_is_present else "",
    )


def _count_map(candidates: list[dict], key: str, order: tuple) -> dict[str, int]:
    """Zero-filled count of ``candidates`` by ``candidate[key]`` in ``order``.

    Every value in ``order`` appears as a key even when no candidate has it, so
    the map's values always sum to ``len(candidates)`` (Req 16.4, 16.5).
    """
    counts = {value: 0 for value in order}
    for candidate in candidates:
        value = candidate[key]
        if value in counts:
            counts[value] += 1
    return counts


def build_report(
    records: list,
    candidates: list[dict],
    ai_enabled: bool,
    rejected: int,
    errors: int,
) -> dict:
    """Assemble the Report dict from loaded records and built candidates.

    ``records`` is the full list of Raw_Records (counted whole, including any
    that produced an ``invalid_record`` candidate). ``candidates`` are the
    built Review_Candidates. ``ai_enabled`` reflects whether the AI_Suggester
    ran; ``rejected`` and ``errors`` are the Suggestion_Validator counters.

    With AI disabled, the AI counters and the ``ai_suggestion`` source count are
    forced to 0 (Req 16.7). Candidates are ordered per Req 13.5. The returned
    dict has a fixed key order in every object, ready for :func:`to_json`.
    """
    ordered = sorted(candidates, key=_candidate_sort_key)

    by_source = _count_map(ordered, "source", _SOURCE_ORDER)
    if not ai_enabled:
        # Defensive: with --no-ai no AI candidates or counters should exist.
        rejected = 0
        errors = 0
        by_source["ai_suggestion"] = 0

    summary = {
        "records_read": len(records),
        "candidates_total": len(ordered),
        "by_issue_type": _count_map(ordered, "issue_type", _ISSUE_TYPE_ORDER),
        "by_severity": _count_map(ordered, "severity", _SEVERITY_ORDER),
        "by_source": by_source,
        "ai_enabled": bool(ai_enabled),
        "ai_suggestions_rejected": int(rejected),
        "ai_errors": int(errors),
        "notice": REVIEW_NOTICE,
    }

    return {"summary": summary, "candidates": ordered}


def to_json(report: dict) -> str:
    """Serialize a Report to deterministic UTF-8 JSON with a trailing newline.

    Insertion order is preserved (``sort_keys`` is intentionally left off so the
    candidate key order from ``make_candidate`` is kept, Req 13.4). ``indent=2``
    gives a stable, readable layout; ``ensure_ascii=False`` keeps non-ASCII
    field values readable while the serializer still escapes control characters.
    """
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"
