import hashlib

import pytest

from dq_assistant.models import (
    ISSUE_TYPES,
    KNOWN_CATEGORIES,
    SEVERITIES,
    SOURCES,
    UOM_ALLOW_LIST,
    finding_id,
    make_candidate,
    observed,
)

BASE_FIELDS = [
    "finding_id",
    "item_id",
    "row_index",
    "issue_type",
    "field",
    "severity",
    "confidence",
    "explanation",
    "suggested_action",
    "source",
    "status",
    "allowed_actions",
]


def _kwargs(**overrides):
    kw = dict(
        issue_type="missing_part_number",
        row_index=3,
        item_id="A1",
        field="manufacturer_part_number",
        severity="medium",
        confidence=0.95,
        explanation="Candidate issue: part number may be missing.",
        suggested_action="Review and add the part number if known.",
        source="deterministic_rule",
    )
    kw.update(overrides)
    return kw


def test_constant_sets():
    assert len(ISSUE_TYPES) == 11
    assert SEVERITIES == {"low", "medium", "high"}
    assert SOURCES == {"deterministic_rule", "heuristic", "ai_suggestion"}
    assert {"EA", "BOX", "KG", "M", "ROLL"} <= UOM_ALLOW_LIST
    assert "Mechanical" in KNOWN_CATEGORIES


def test_base_candidate_schema():
    c = make_candidate(**_kwargs())
    assert list(c) == BASE_FIELDS
    assert c["status"] == "needs_review"
    assert c["allowed_actions"] == ["approve", "reject", "investigate"]
    assert c["row_index"] == 3 and c["item_id"] == "A1"


def test_confidence_rounded_and_numeric():
    c = make_candidate(**_kwargs(confidence=0.756))
    assert c["confidence"] == 0.76 and type(c["confidence"]) is float
    assert make_candidate(**_kwargs(confidence=1))["confidence"] == 1.0


@pytest.mark.parametrize("bad", [1.5, -0.1, "0.9", True])
def test_bad_confidence_rejected(bad):
    with pytest.raises(ValueError):
        make_candidate(**_kwargs(confidence=bad))


@pytest.mark.parametrize(
    "override",
    [
        {"issue_type": "nope"},
        {"severity": "critical"},
        {"source": "llm"},
        {"row_index": -1},
        {"field": "colour"},
        {"explanation": ""},
        {"explanation": "x" * 501},
        {"suggested_action": "y" * 301},
        {"field": None},
    ],
)
def test_invalid_values_rejected(override):
    with pytest.raises(ValueError):
        make_candidate(**_kwargs(**override))


def test_whole_record_and_null_item_id():
    c = make_candidate(
        **_kwargs(issue_type="invalid_record", field=None, item_id=None, severity="high", confidence=1.0)
    )
    assert c["field"] is None and c["item_id"] is None
    assert list(c) == BASE_FIELDS


def test_duplicate_family_related_fields_sorted():
    c = make_candidate(
        **_kwargs(issue_type="duplicate_item_id", field="item_id", source="heuristic"),
        related=[(7, "A1"), (1, None)],
    )
    assert list(c) == BASE_FIELDS + ["related_item_ids", "related_row_indexes"]
    assert c["related_row_indexes"] == [1, 7]
    assert c["related_item_ids"] == [None, "A1"]


def test_duplicate_family_requires_related_and_others_forbid_it():
    with pytest.raises(ValueError):
        make_candidate(**_kwargs(issue_type="potential_duplicate", source="heuristic"))
    with pytest.raises(ValueError):
        make_candidate(**_kwargs(), related=[(1, "B")])


def test_suggested_category_rules():
    c = make_candidate(
        **_kwargs(issue_type="category_mismatch_candidate", field="category", source="ai_suggestion"),
        suggested_category="Mechanical",
    )
    assert list(c) == BASE_FIELDS + ["suggested_category"]
    with pytest.raises(ValueError):
        make_candidate(
            **_kwargs(issue_type="category_mismatch_candidate", field="category"),
            suggested_category="Food",
        )
    with pytest.raises(ValueError):
        make_candidate(**_kwargs(), suggested_category="Mechanical")


def test_observed_truncates_to_50():
    assert observed("z" * 80) == "z" * 50
    assert observed("short") == "short"


def test_finding_id_matches_spec_and_is_stable():
    expected = hashlib.sha256(b"missing_part_number|3|A1|manufacturer_part_number").hexdigest()[:16]
    assert finding_id("missing_part_number", 3, "A1", "manufacturer_part_number") == expected
    assert make_candidate(**_kwargs())["finding_id"] == expected
    assert make_candidate(**_kwargs())["finding_id"] == expected
    nulls = hashlib.sha256(b"invalid_record|0||").hexdigest()[:16]
    assert finding_id("invalid_record", 0, None, None) == nulls
    assert len(expected) == 16 and expected == expected.lower()


def test_finding_id_unique_across_type_row_field():
    ids = {
        finding_id(t, r, "A1", f)
        for t in ("missing_required_field", "invalid_field_type")
        for r in (0, 1, 10)
        for f in ("item_id", "category", None)
    }
    assert len(ids) == 18
