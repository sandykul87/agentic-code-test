"""Constants, Review_Candidate builder, and finding_id (Requirements 12, 13)."""

import hashlib

ISSUE_TYPES = frozenset(
    {
        "missing_required_field",
        "invalid_field_type",
        "invalid_record",
        "missing_part_number",
        "unsupported_unit_of_measure",
        "weak_description",
        "duplicate_item_id",
        "conflicting_source_values",
        "potential_duplicate",
        "cross_system_duplicate",
        "category_mismatch_candidate",
    }
)
SEVERITIES = frozenset({"low", "medium", "high"})
SOURCES = frozenset({"deterministic_rule", "heuristic", "ai_suggestion"})

UOM_ALLOW_LIST = frozenset({"EA", "BOX", "KG", "G", "M", "CM", "L", "ML", "PK", "ROLL"})
KNOWN_CATEGORIES = ("Mechanical", "Electrical", "Plumbing", "Electronics", "Safety")

RECORD_FIELDS = (
    "item_id",
    "item_description",
    "manufacturer",
    "manufacturer_part_number",
    "category",
    "unit_of_measure",
    "source_system",
)
REQUIRED_FIELDS = tuple(f for f in RECORD_FIELDS if f != "manufacturer_part_number")

DUPLICATE_FAMILY = frozenset(
    {
        "duplicate_item_id",
        "conflicting_source_values",
        "potential_duplicate",
        "cross_system_duplicate",
    }
)
WHOLE_RECORD_TYPES = frozenset(
    {"invalid_record", "conflicting_source_values", "cross_system_duplicate"}
)

STATUS = "needs_review"
ALLOWED_ACTIONS = ("approve", "reject", "investigate")
MAX_OBSERVED_CHARS = 50
MAX_EXPLANATION_CHARS = 500
MAX_SUGGESTED_ACTION_CHARS = 300


def finding_id(issue_type: str, row_index: int, item_id: str | None, field: str | None) -> str:
    """First 16 hex chars of SHA-256 over ``issue_type|row_index|item_id|field``."""
    key = "|".join([issue_type, str(int(row_index)), item_id or "", field or ""])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def observed(value: object) -> str:
    """Render an observed input value for an explanation, capped at 50 chars."""
    return str(value)[:MAX_OBSERVED_CHARS]


def make_candidate(
    *,
    issue_type: str,
    row_index: int,
    item_id: str | None,
    field: str | None,
    severity: str,
    confidence: float,
    explanation: str,
    suggested_action: str,
    source: str,
    related: list[tuple[int, str | None]] | None = None,
    suggested_category: str | None = None,
) -> dict:
    """Build one Review_Candidate with the fixed field set and key order.

    ``related`` is a list of (row_index, item_id) for the other records in a
    duplicate-family group; it is required for that family and forbidden
    otherwise. ``suggested_category`` follows the same rule for
    ``category_mismatch_candidate``. Callers pass observed values through
    :func:`observed` so explanations never carry more than 50 chars of input.
    """
    if issue_type not in ISSUE_TYPES:
        raise ValueError(f"unknown issue_type: {issue_type}")
    if severity not in SEVERITIES:
        raise ValueError(f"unknown severity: {severity}")
    if source not in SOURCES:
        raise ValueError(f"unknown source: {source}")
    if isinstance(row_index, bool) or not isinstance(row_index, int) or row_index < 0:
        raise ValueError("row_index must be a non-negative int")
    if item_id is not None and not isinstance(item_id, str):
        raise ValueError("item_id must be a str or None")
    if field is not None and field not in RECORD_FIELDS:
        raise ValueError(f"unknown field: {field}")
    if (field is None) != (issue_type in WHOLE_RECORD_TYPES):
        raise ValueError("field must be None exactly for whole-record issue types")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("confidence must be a number")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be within 0.0..1.0")
    if not isinstance(explanation, str) or not explanation.strip():
        raise ValueError("explanation must be a non-empty string")
    if not isinstance(suggested_action, str) or not suggested_action.strip():
        raise ValueError("suggested_action must be a non-empty string")
    if len(explanation) > MAX_EXPLANATION_CHARS:
        raise ValueError("explanation exceeds 500 characters")
    if len(suggested_action) > MAX_SUGGESTED_ACTION_CHARS:
        raise ValueError("suggested_action exceeds 300 characters")

    candidate = {
        "finding_id": finding_id(issue_type, row_index, item_id, field),
        "item_id": item_id,
        "row_index": row_index,
        "issue_type": issue_type,
        "field": field,
        "severity": severity,
        "confidence": round(float(confidence), 2),
        "explanation": explanation,
        "suggested_action": suggested_action,
        "source": source,
        "status": STATUS,
        "allowed_actions": list(ALLOWED_ACTIONS),
    }

    if issue_type in DUPLICATE_FAMILY:
        if not related:
            raise ValueError("duplicate-family candidates need related records")
        ordered = sorted(related, key=lambda pair: pair[0])
        candidate["related_item_ids"] = [iid for _, iid in ordered]
        candidate["related_row_indexes"] = [idx for idx, _ in ordered]
    elif related is not None:
        raise ValueError("related records only apply to the duplicate family")

    if issue_type == "category_mismatch_candidate":
        if suggested_category not in KNOWN_CATEGORIES:
            raise ValueError("suggested_category must be in the Known_Category_List")
        candidate["suggested_category"] = suggested_category
    elif suggested_category is not None:
        raise ValueError("suggested_category only applies to category_mismatch_candidate")

    return candidate
