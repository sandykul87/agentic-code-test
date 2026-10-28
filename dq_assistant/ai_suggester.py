"""AISuggester Protocol, StubAISuggester, and the minimal record view (Req 10).

The AISuggester is the single swap point for a future real LLM. Whatever it
returns is untrusted and must go through :mod:`dq_assistant.validator`. The
stub here is deterministic, offline, and uses a fixed keyword map.
"""

from typing import Protocol

from dq_assistant.fields import PRESENT, normalize_text, read
from dq_assistant.models import KNOWN_CATEGORIES, observed

VIEW_FIELDS = ("item_id", "item_description", "category")

# Whole-word, case-insensitive keyword -> category map (design section 6).
KEYWORD_MAP = {
    "bearing": "Mechanical",
    "gearbox": "Mechanical",
    "coupling": "Mechanical",
    "valve": "Mechanical",
    "pump": "Mechanical",
    "cable": "Electrical",
    "fuse": "Electrical",
    "breaker": "Electrical",
    "relay": "Electrical",
    "transformer": "Electrical",
    "pipe": "Plumbing",
    "fitting": "Plumbing",
    "gasket": "Plumbing",
    "flange": "Plumbing",
    "sensor": "Electronics",
    "resistor": "Electronics",
    "capacitor": "Electronics",
    "pcb": "Electronics",
    "helmet": "Safety",
    "glove": "Safety",
    "goggles": "Safety",
}
assert set(KEYWORD_MAP.values()) <= set(KNOWN_CATEGORIES)

STUB_CONFIDENCE = 0.7
_STUB_ACTION = "Review the category assignment with the source owner before approval."


class AISuggester(Protocol):
    """Receives a minimal record view and returns zero or more raw suggestions."""

    def suggest(self, view: dict) -> list[dict]: ...


def minimal_view(record) -> dict:
    """Build the minimal view (item_id, item_description, category) via fields.read.

    Values are trimmed copies; a missing or invalid-type value becomes None.
    No other field of the record is included (Req 10.1, 10.2).
    """
    view = {}
    for name in VIEW_FIELDS:
        status, value = read(record, name)
        view[name] = value if status == PRESENT else None
    return view


def _is_boundary(text: str, index: int) -> bool:
    """True at the string edges or next to a character that is not a letter/digit."""
    return index < 0 or index >= len(text) or not text[index].isalnum()


def matched_keywords(description: str) -> list[str]:
    """Keywords found as whole words, ordered by first position in the text."""
    text = description.lower()
    hits = []
    for keyword in KEYWORD_MAP:
        start = text.find(keyword)
        while start != -1:
            end = start + len(keyword)
            if _is_boundary(text, start - 1) and _is_boundary(text, end):
                hits.append((start, keyword))
                break
            start = text.find(keyword, start + 1)
    return [keyword for _, keyword in sorted(hits)]


class StubAISuggester:
    """Deterministic, offline stand-in for a real LLM category suggester."""

    def suggest(self, view: dict) -> list[dict]:
        description = view.get("item_description")
        category = view.get("category")
        if not isinstance(description, str) or not isinstance(category, str):
            return []
        keywords = matched_keywords(description)
        categories = {KEYWORD_MAP[k] for k in keywords}
        if len(categories) != 1:
            return []
        (suggested,) = categories
        if normalize_text(suggested) == normalize_text(category):
            return []
        quoted = ", ".join(f"'{k}'" for k in keywords)
        noun = "keyword" if len(keywords) == 1 else "keywords"
        return [
            {
                "issue_type": "category_mismatch_candidate",
                "confidence": STUB_CONFIDENCE,
                "suggested_category": suggested,
                "explanation": (
                    f"Candidate issue: description {noun} {quoted} suggests category "
                    f"{suggested}, recorded as {observed(category)}."
                ),
                "suggested_action": _STUB_ACTION,
            }
        ]
