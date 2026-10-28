"""Suggestion_Validator for untrusted AI output (Requirements 10.6-10.8, 11).

This is trust boundary 2. Every AI_Suggestion is checked against a fixed
schema before it can become a Review_Candidate. Rejected suggestions are
dropped and counted; a suggester that raises or returns a non-list is counted
as an error for that record. Neither stops the run.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

from dq_assistant.ai_suggester import AISuggester, minimal_view
from dq_assistant.fields import PRESENT, normalize_text, read
from dq_assistant.loader import JSON_NON_OBJECT
from dq_assistant.models import (
    KNOWN_CATEGORIES,
    MAX_EXPLANATION_CHARS,
    MAX_SUGGESTED_ACTION_CHARS,
    contains_forbidden_term,
    has_action_wording,
    has_explanation_wording,
    make_candidate,
)

ISSUE_TYPE = "category_mismatch_candidate"
SOURCE = "ai_suggestion"
SEVERITY = "low"
FIELD = "category"
REQUIRED_KEYS = (
    "issue_type",
    "confidence",
    "suggested_category",
    "explanation",
    "suggested_action",
)


@dataclass
class AIResult:
    """Accepted candidates plus the summary counters of Req 11.7 and 11.8."""

    candidates: list = field(default_factory=list)
    rejected: int = 0
    errors: int = 0


def _bounded_text(value, limit: int) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= limit and bool(value.strip())


def is_valid(suggestion, current_category: str | None) -> bool:
    """Apply the Req 11.1-11.6 acceptance rules. Never raises on odd shapes."""
    # 11.1 shape and issue type
    if not isinstance(suggestion, Mapping):
        return False
    if any(key not in suggestion for key in REQUIRED_KEYS):
        return False
    if not isinstance(suggestion["issue_type"], str) or suggestion["issue_type"] != ISSUE_TYPE:
        return False
    # 11.2 confidence: real number, finite, 0..1
    confidence = suggestion["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return False
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        return False
    # 11.3 known category, different from the current one
    category = suggestion["suggested_category"]
    if not isinstance(category, str) or category not in KNOWN_CATEGORIES:
        return False
    if current_category is not None and normalize_text(category) == normalize_text(
        current_category
    ):
        return False
    # 11.4 lengths
    explanation = suggestion["explanation"]
    action = suggestion["suggested_action"]
    if not _bounded_text(explanation, MAX_EXPLANATION_CHARS):
        return False
    if not _bounded_text(action, MAX_SUGGESTED_ACTION_CHARS):
        return False
    # 11.5 forbidden terms
    if contains_forbidden_term(explanation) or contains_forbidden_term(action):
        return False
    # 11.6 review wording
    return has_explanation_wording(explanation) and has_action_wording(action)


def validate(suggestion, record) -> dict | None:
    """Return a Review_Candidate for a valid suggestion, else None.

    Only confidence, suggested_category, explanation, and suggested_action
    come from the suggestion. item_id, row_index, field, severity, and source
    are set here (Req 11.9, 11.10); any other keys are ignored.
    """
    category_status, category = read(record, FIELD)
    current = category if category_status == PRESENT else None
    if not is_valid(suggestion, current):
        return None
    id_status, id_value = read(record, "item_id")
    return make_candidate(
        issue_type=ISSUE_TYPE,
        row_index=record.row_index,
        item_id=id_value if id_status == PRESENT else None,
        field=FIELD,
        severity=SEVERITY,
        confidence=round(float(suggestion["confidence"]), 2),
        explanation=suggestion["explanation"],
        suggested_action=suggestion["suggested_action"],
        source=SOURCE,
        suggested_category=suggestion["suggested_category"],
    )


def _eligible(record) -> bool:
    """Skip invalid records (Req 5.1/5.2) and records lacking description or category (Req 10.6)."""
    if record.kind == JSON_NON_OBJECT or record.ragged:
        return False
    return read(record, "item_description")[0] == PRESENT and read(record, FIELD)[0] == PRESENT


def run_ai_suggestions(records, suggester: AISuggester) -> AIResult:
    """Call ``suggester`` per eligible record and validate everything it returns."""
    result = AIResult()
    for record in records:
        if not _eligible(record):
            continue
        try:
            suggestions = suggester.suggest(minimal_view(record))
        except Exception:  # untrusted component: discard its output, count, continue
            result.errors += 1
            continue
        if not isinstance(suggestions, list):
            result.errors += 1
            continue
        accepted = False
        for suggestion in suggestions:
            candidate = validate(suggestion, record)
            if candidate is None or accepted:
                result.rejected += 1  # invalid, or a valid extra beyond the first (Req 11.11)
                continue
            result.candidates.append(candidate)
            accepted = True
    return result
