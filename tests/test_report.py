"""Tests for report assembly and deterministic output (Req 13.2-13.5, 14, 16)."""

from dq_assistant.models import (
    FORBIDDEN_TERMS,
    ISSUE_TYPES,
    SEVERITIES,
    SOURCES,
    contains_forbidden_term,
    make_candidate,
)
from dq_assistant.report import REVIEW_NOTICE, build_report, to_json


def _candidate(**overrides):
    """Build a plausible Review_Candidate, overriding selected fields."""
    base = dict(
        issue_type="missing_part_number",
        row_index=0,
        item_id="1001",
        field="manufacturer_part_number",
        severity="medium",
        confidence=0.95,
        explanation="Candidate issue: part number is missing and needs review.",
        suggested_action="Confirm the manufacturer part number with the owner.",
        source="deterministic_rule",
    )
    base.update(overrides)
    return make_candidate(**base)


def _records(n):
    return [object()] * n


# --- summary counts (Req 16.1-16.5) ---


def test_count_maps_have_all_keys_zero_filled_and_sum_to_total():
    candidates = [
        _candidate(row_index=0),
        _candidate(row_index=1, issue_type="unsupported_unit_of_measure",
                   field="unit_of_measure", severity="medium", confidence=0.9),
        _candidate(row_index=2, issue_type="weak_description",
                   field="item_description", severity="low", confidence=0.8,
                   source="heuristic",
                   explanation="Candidate issue: description looks weak, needs review.",
                   suggested_action="Review the description with the source owner."),
    ]
    report = build_report(_records(3), candidates, ai_enabled=True, rejected=0, errors=0)
    summary = report["summary"]

    assert set(summary["by_issue_type"]) == set(ISSUE_TYPES)
    assert set(summary["by_severity"]) == set(SEVERITIES)
    assert set(summary["by_source"]) == set(SOURCES)

    total = summary["candidates_total"]
    assert total == 3
    for key in ("by_issue_type", "by_severity", "by_source"):
        assert sum(summary[key].values()) == total
        assert all(isinstance(v, int) and v >= 0 for v in summary[key].values())
    # Zero-filled example: an unused issue type is present and 0.
    assert summary["by_issue_type"]["invalid_record"] == 0


def test_empty_candidates_zero_fill_sums_to_zero():
    report = build_report(_records(2), [], ai_enabled=True, rejected=0, errors=0)
    summary = report["summary"]
    assert set(summary["by_issue_type"]) == set(ISSUE_TYPES)
    assert sum(summary["by_issue_type"].values()) == 0
    assert sum(summary["by_severity"].values()) == 0
    assert sum(summary["by_source"].values()) == 0


def test_records_read_and_candidates_total():
    candidates = [_candidate(row_index=0), _candidate(row_index=1)]
    report = build_report(_records(5), candidates, ai_enabled=True, rejected=0, errors=0)
    assert report["summary"]["records_read"] == 5
    assert report["summary"]["candidates_total"] == 2
    assert len(report["candidates"]) == 2


def test_count_maps_use_deterministic_sorted_key_order():
    report = build_report(_records(1), [], ai_enabled=True, rejected=0, errors=0)
    summary = report["summary"]
    assert list(summary["by_issue_type"]) == sorted(ISSUE_TYPES)
    assert list(summary["by_severity"]) == sorted(SEVERITIES)
    assert list(summary["by_source"]) == sorted(SOURCES)


# --- candidate ordering (Req 13.5) ---


def test_candidates_ordered_by_row_then_issue_then_field_null_first():
    # Whole-record candidate (field is None) on row 0 must sort before the
    # named-field candidate on the same row.
    whole = _candidate(
        row_index=0,
        issue_type="invalid_record",
        item_id=None,
        field=None,
        severity="high",
        confidence=1.0,
        explanation="Candidate issue: record is invalid and needs review.",
        suggested_action="Review the raw record with the source owner.",
    )
    named_a = _candidate(row_index=0, field="category", issue_type="invalid_field_type",
                         severity="medium", confidence=1.0,
                         explanation="Candidate issue: field type looks wrong, needs review.",
                         suggested_action="Verify the field type with the owner.")
    named_b = _candidate(row_index=0, field="manufacturer_part_number")
    row1 = _candidate(row_index=1)

    unordered = [row1, named_b, named_a, whole]
    report = build_report(_records(2), unordered, ai_enabled=True, rejected=0, errors=0)
    ordered = report["candidates"]

    keys = [(c["row_index"], c["issue_type"], c["field"]) for c in ordered]
    # row_index first, then issue_type ascending, then field. Row 0's three
    # findings sort by issue_type (invalid_field_type < invalid_record <
    # missing_part_number), and row 1 comes last.
    assert keys == [
        (0, "invalid_field_type", "category"),
        (0, "invalid_record", None),
        (0, "missing_part_number", "manufacturer_part_number"),
        (1, "missing_part_number", "manufacturer_part_number"),
    ]


def test_null_field_sorts_before_named_field_within_same_issue_type():
    # When row_index and issue_type match, a null field sorts before a named
    # one (Req 13.5). conflicting_source_values is a whole-record (null-field)
    # duplicate-family type; invalid_field_type carries a named field. Use the
    # sort key directly to isolate the null-first tiebreaker.
    from dq_assistant.report import _candidate_sort_key

    null_field = {"row_index": 0, "issue_type": "x", "field": None}
    named_field = {"row_index": 0, "issue_type": "x", "field": "category"}
    assert _candidate_sort_key(null_field) < _candidate_sort_key(named_field)


def test_issue_type_breaks_ties_before_field():
    a = _candidate(row_index=0, issue_type="invalid_field_type", field="unit_of_measure",
                   severity="medium", confidence=1.0,
                   explanation="Candidate issue: field type looks wrong, needs review.",
                   suggested_action="Verify the field type with the owner.")
    b = _candidate(row_index=0, issue_type="unsupported_unit_of_measure",
                   field="unit_of_measure", severity="medium", confidence=0.9)
    report = build_report(_records(1), [b, a], ai_enabled=True, rejected=0, errors=0)
    assert [c["issue_type"] for c in report["candidates"]] == [
        "invalid_field_type",
        "unsupported_unit_of_measure",
    ]


# --- deterministic output (Req 13.2, 13.3, 13.4) ---


def test_output_is_byte_identical_on_repeat():
    candidates = [
        _candidate(row_index=2),
        _candidate(row_index=0, issue_type="invalid_record", item_id=None, field=None,
                   severity="high", confidence=1.0,
                   explanation="Candidate issue: record is invalid and needs review.",
                   suggested_action="Review the raw record with the source owner."),
        _candidate(row_index=1, source="heuristic", issue_type="weak_description",
                   field="item_description", severity="low", confidence=0.8,
                   explanation="Candidate issue: description looks weak, needs review.",
                   suggested_action="Review the description with the source owner."),
    ]
    first = to_json(build_report(_records(3), list(candidates), True, 1, 2))
    second = to_json(build_report(_records(3), list(candidates), True, 1, 2))
    assert first == second


def test_output_has_trailing_newline():
    out = to_json(build_report(_records(1), [], ai_enabled=True, rejected=0, errors=0))
    assert out.endswith("\n")
    assert not out.endswith("\n\n")


def test_candidate_key_order_preserved_in_json():
    report = build_report(_records(1), [_candidate()], ai_enabled=True, rejected=0, errors=0)
    out = to_json(report)
    # finding_id is the first key of each candidate; order from make_candidate.
    assert out.index('"finding_id"') < out.index('"item_id"') < out.index('"row_index"')
    # summary precedes candidates in the top-level document.
    assert out.index('"summary"') < out.index('"candidates"')


# --- review-language notice and forbidden terms (Req 14) ---


def test_notice_matches_exact_review_language():
    expected = (
        "All findings are candidate issues that need human review by a data "
        "steward. No input data was modified."
    )
    assert REVIEW_NOTICE == expected
    report = build_report(_records(1), [], ai_enabled=True, rejected=0, errors=0)
    assert report["summary"]["notice"] == expected


def test_notice_contains_no_forbidden_terms():
    assert not contains_forbidden_term(REVIEW_NOTICE)
    for term in FORBIDDEN_TERMS:
        assert term not in REVIEW_NOTICE.lower()


def test_notice_present_for_zero_candidate_report():
    report = build_report(_records(1), [], ai_enabled=True, rejected=0, errors=0)
    assert report["summary"]["notice"] == REVIEW_NOTICE


def test_notice_present_when_ai_disabled():
    report = build_report(_records(1), [], ai_enabled=False, rejected=0, errors=0)
    assert report["summary"]["notice"] == REVIEW_NOTICE


# --- --no-ai behavior (Req 16.7, 16.8) ---


def test_ai_disabled_forces_ai_counters_and_source_count_to_zero():
    ai_candidate = _candidate(
        row_index=0,
        issue_type="category_mismatch_candidate",
        field="category",
        severity="low",
        confidence=0.7,
        source="ai_suggestion",
        explanation="Candidate issue: category may be wrong, needs review.",
        suggested_action="Review the category assignment before approval.",
        suggested_category="Mechanical",
    )
    # Pass nonzero counters defensively; they must be zeroed out.
    report = build_report(_records(1), [ai_candidate], ai_enabled=False, rejected=4, errors=2)
    summary = report["summary"]
    assert summary["ai_enabled"] is False
    assert summary["ai_suggestions_rejected"] == 0
    assert summary["ai_errors"] == 0
    assert summary["by_source"]["ai_suggestion"] == 0


def test_ai_enabled_sets_flag_true_and_keeps_counters():
    report = build_report(_records(1), [], ai_enabled=True, rejected=3, errors=1)
    summary = report["summary"]
    assert summary["ai_enabled"] is True
    assert summary["ai_suggestions_rejected"] == 3
    assert summary["ai_errors"] == 1


def test_summary_has_exactly_the_required_keys_in_order():
    report = build_report(_records(1), [], ai_enabled=True, rejected=0, errors=0)
    assert list(report["summary"]) == [
        "records_read",
        "candidates_total",
        "by_issue_type",
        "by_severity",
        "by_source",
        "ai_enabled",
        "ai_suggestions_rejected",
        "ai_errors",
        "notice",
    ]
