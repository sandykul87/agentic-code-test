import copy

import pytest

from dq_assistant.ai_suggester import (
    KEYWORD_MAP,
    StubAISuggester,
    matched_keywords,
    minimal_view,
)
from dq_assistant.loader import CSV_ROW, JSON_NON_OBJECT, JSON_OBJECT, RawRecord
from dq_assistant.models import KNOWN_CATEGORIES, finding_id
from dq_assistant.validator import run_ai_suggestions, validate

MISCATEGORIZED = {
    "item_id": " 1002 ",
    "item_description": "SKF Bearing 6205 ZZ",
    "manufacturer": "SKF",
    "manufacturer_part_number": "6205-ZZ",
    "category": "Electrical",
    "unit_of_measure": "EA",
    "source_system": "SAP",
}

VALID = {
    "issue_type": "category_mismatch_candidate",
    "confidence": 0.7,
    "suggested_category": "Mechanical",
    "explanation": "Candidate issue: description suggests Mechanical.",
    "suggested_action": "Review the category assignment.",
}


def _rec(row_index=0, **overrides):
    fields = dict(MISCATEGORIZED)
    fields.update(overrides)
    return RawRecord(row_index, fields, JSON_OBJECT)


class _Fixed:
    """Suggester that returns a fixed value (or raises) regardless of input."""

    def __init__(self, value=None, raises=False):
        self.value = value
        self.raises = raises
        self.views = []

    def suggest(self, view):
        self.views.append(view)
        if self.raises:
            raise RuntimeError("model unavailable")
        return copy.deepcopy(self.value)


def _with(**changes):
    s = dict(VALID)
    s.update(changes)
    return s


# --- Stub suggester and minimal view (Req 10) ---


def test_happy_path_category_mismatch_candidate():
    result = run_ai_suggestions([_rec(row_index=4)], StubAISuggester())
    assert result.rejected == 0 and result.errors == 0
    assert len(result.candidates) == 1
    c = result.candidates[0]
    assert c["issue_type"] == "category_mismatch_candidate"
    assert c["severity"] == "low"
    assert c["confidence"] == 0.7
    assert c["source"] == "ai_suggestion"
    assert c["field"] == "category"
    assert c["suggested_category"] == "Mechanical"
    assert c["item_id"] == "1002" and c["row_index"] == 4
    assert c["status"] == "needs_review"
    assert "'bearing'" in c["explanation"] and "Electrical" in c["explanation"]
    assert "review" in c["suggested_action"].lower()
    assert c["finding_id"] == finding_id("category_mismatch_candidate", 4, "1002", "category")


def test_minimal_view_has_only_three_trimmed_fields():
    view = minimal_view(_rec(item_id=1002))
    assert view == {
        "item_id": None,
        "item_description": "SKF Bearing 6205 ZZ",
        "category": "Electrical",
    }


def test_suggester_receives_only_minimal_view():
    spy = _Fixed(value=[])
    run_ai_suggestions([_rec()], spy)
    assert spy.views == [
        {"item_id": "1002", "item_description": "SKF Bearing 6205 ZZ", "category": "Electrical"}
    ]


@pytest.mark.parametrize(
    "description,category",
    [
        ("SKF Bearing 6205 ZZ", "mechanical "),  # same category after normalization
        ("Bearing and cable kit", "Safety"),  # ambiguous: two categories
        ("Cableway support bracket", "Mechanical"),  # keyword inside another word
        ("Stainless bracket 40mm", "Mechanical"),  # no keyword
    ],
)
def test_stub_returns_nothing(description, category):
    view = {"item_id": "1", "item_description": description, "category": category}
    assert StubAISuggester().suggest(view) == []


def test_keyword_boundaries_and_order():
    assert matched_keywords("PUMP-valve/bearing_x") == ["pump", "valve", "bearing"]
    assert matched_keywords("bearings 2xpump") == []
    assert matched_keywords("cable cableway") == ["cable"]


def test_stub_is_deterministic_and_categories_known():
    view = minimal_view(_rec())
    assert StubAISuggester().suggest(view) == StubAISuggester().suggest(view)
    assert set(KEYWORD_MAP.values()) <= set(KNOWN_CATEGORIES)


@pytest.mark.parametrize(
    "overrides",
    [{"item_description": "  "}, {"category": None}, {"category": 7}, {"item_description": []}],
)
def test_suggester_not_called_without_description_or_category(overrides):
    spy = _Fixed(value=[VALID])
    result = run_ai_suggestions([_rec(**overrides)], spy)
    assert spy.views == []
    assert (result.candidates, result.rejected, result.errors) == ([], 0, 0)


def test_suggester_not_called_for_invalid_records():
    spy = _Fixed(value=[VALID])
    records = [
        RawRecord(0, {}, JSON_NON_OBJECT, value=5),
        RawRecord(1, dict(MISCATEGORIZED), CSV_ROW, ragged=True, extra=("x",)),
    ]
    result = run_ai_suggestions(records, spy)
    assert spy.views == [] and result.candidates == []


# --- Suggestion_Validator: one test per rule and the Req 19.7 shapes ---


@pytest.mark.parametrize(
    "suggestion",
    [
        pytest.param("not a mapping", id="11.1-non-mapping"),
        pytest.param(["list"], id="11.1-list"),
        pytest.param({k: v for k, v in VALID.items() if k != "explanation"}, id="11.1-missing-key"),
        pytest.param(_with(issue_type="weak_description"), id="11.1-wrong-issue-type"),
        pytest.param(_with(confidence=1.5), id="11.2-above-1"),
        pytest.param(_with(confidence=-0.1), id="11.2-negative"),
        pytest.param(_with(confidence="0.9"), id="11.2-string"),
        pytest.param(_with(confidence=True), id="11.2-bool"),
        pytest.param(_with(confidence=float("nan")), id="11.2-nan"),
        pytest.param(_with(suggested_category="Furniture"), id="11.3-unknown-category"),
        pytest.param(_with(suggested_category="mechanical"), id="11.3-wrong-case"),
        pytest.param(_with(suggested_category="Electrical"), id="11.3-equals-current"),
        pytest.param(_with(explanation=""), id="11.4-empty-explanation"),
        pytest.param(_with(explanation="   "), id="11.4-whitespace-explanation"),
        pytest.param(_with(explanation="Candidate " + "x" * 491), id="11.4-explanation-501"),
        pytest.param(_with(suggested_action="Review " + "x" * 294), id="11.4-action-301"),
        pytest.param(
            _with(explanation="Candidate issue: auto-approved by model."), id="11.5-auto-approved"
        ),
        pytest.param(_with(suggested_action="Review: category fixed."), id="11.5-fixed-in-action"),
        pytest.param(_with(explanation="Category is Mechanical."), id="11.6-no-candidate-wording"),
        pytest.param(_with(suggested_action="Change the category."), id="11.6-no-review-wording"),
    ],
)
def test_invalid_suggestion_is_dropped_and_counted(suggestion):
    assert validate(suggestion, _rec()) is None
    result = run_ai_suggestions([_rec()], _Fixed(value=[suggestion]))
    assert result.candidates == []
    assert result.rejected == 1
    assert result.errors == 0


def test_length_limits_are_inclusive():
    s = _with(explanation="Candidate " + "x" * 490, suggested_action="Review " + "x" * 293)
    assert len(s["explanation"]) == 500 and len(s["suggested_action"]) == 300
    assert validate(s, _rec()) is not None


def test_forbidden_terms_match_whole_words_only():
    s = _with(explanation="Candidate issue: unfixedness is a potential sign.")
    assert validate(s, _rec()) is not None


def test_integer_confidence_accepted_and_rounded():
    assert validate(_with(confidence=1), _rec())["confidence"] == 1.0
    assert validate(_with(confidence=0.666), _rec())["confidence"] == 0.67


def test_validator_sets_identity_fields_and_ignores_extra_keys():
    s = _with(
        item_id="EVIL",
        row_index=99,
        field="manufacturer",
        severity="high",
        source="deterministic_rule",
        status="approved",
        note="extra",
    )
    c = validate(s, _rec(row_index=2))
    assert c["item_id"] == "1002" and c["row_index"] == 2
    assert c["field"] == "category" and c["severity"] == "low"
    assert c["source"] == "ai_suggestion" and c["status"] == "needs_review"
    assert "note" not in c


def test_only_first_valid_suggestion_accepted():
    second = _with(suggested_category="Plumbing")
    result = run_ai_suggestions([_rec()], _Fixed(value=[_with(confidence=1.5), VALID, second]))
    assert [c["suggested_category"] for c in result.candidates] == ["Mechanical"]
    assert result.rejected == 2


# --- Suggester failures (Req 11.8) ---


def test_suggester_raising_is_counted_and_run_continues():
    class _RaisesOnFirst:
        def suggest(self, view):
            if view["item_id"] == "A":
                raise RuntimeError("boom")
            return StubAISuggester().suggest(view)

    records = [_rec(0, item_id="A"), _rec(1, item_id="B")]
    result = run_ai_suggestions(records, _RaisesOnFirst())
    assert result.errors == 1 and result.rejected == 0
    assert [c["item_id"] for c in result.candidates] == ["B"]


@pytest.mark.parametrize("value", [None, VALID, "text", (VALID,)])
def test_non_list_return_is_an_error(value):
    result = run_ai_suggestions([_rec()], _Fixed(value=value))
    assert result.candidates == [] and result.errors == 1 and result.rejected == 0


def test_records_are_not_mutated():
    records = [_rec(0), _rec(1, category=None), RawRecord(2, {}, JSON_NON_OBJECT, value=[1])]
    before = copy.deepcopy(records)
    run_ai_suggestions(records, StubAISuggester())
    run_ai_suggestions(records, _Fixed(raises=True))
    assert records == before
