import copy

import pytest

from dq_assistant.heuristics import run_heuristics
from dq_assistant.loader import CSV_ROW, JSON_NON_OBJECT, JSON_OBJECT, RawRecord

CLEAN = {
    "item_id": "1001",
    "item_description": "SKF deep groove ball bearing 6205 ZZ",
    "manufacturer": "SKF",
    "manufacturer_part_number": "6205-ZZ",
    "category": "Mechanical",
    "unit_of_measure": "EA",
    "source_system": "SAP",
}
_DROP = object()  # marker: remove the field from the record
_FORBIDDEN_ACTION_WORDS = ("merge", "delete", "overwrite")


def _rec(row_index=0, **overrides):
    fields = dict(CLEAN)
    for key, value in overrides.items():
        if value is _DROP:
            fields.pop(key, None)
        else:
            fields[key] = value
    return RawRecord(row_index, fields, JSON_OBJECT)


def _only(candidates, issue_type):
    return [c for c in candidates if c["issue_type"] == issue_type]


def _by_row(candidates, issue_type):
    return {c["row_index"]: c for c in _only(candidates, issue_type)}


def _assert_heuristic(c, severity, confidence):
    assert c["severity"] == severity
    assert c["confidence"] == confidence
    assert c["source"] == "heuristic"
    assert c["status"] == "needs_review"
    assert c["explanation"].startswith("Candidate issue:")


def test_clean_single_record_yields_no_candidates():
    assert run_heuristics([_rec()]) == []


# --- weak_description (Req 8) ---


@pytest.mark.parametrize(
    "description, words, chars",
    [
        ("bearing", 1, 7),
        ("valve", 1, 5),
        ("a b cdefg", 3, 9),  # 3 words but under 10 characters
        ("  ball \t  bearing  ", 2, 12),  # whitespace collapsed before counting
    ],
)
def test_short_description_is_weak(description, words, chars):
    out = run_heuristics([_rec(item_description=description)])
    (c,) = _only(out, "weak_description")
    _assert_heuristic(c, "low", 0.8)
    assert c["field"] == "item_description"
    assert "too short" in c["explanation"]
    assert f"{words} words, {chars} characters" in c["explanation"]
    assert "check" in c["suggested_action"].lower()
    for part in ("item type", "size", "key attributes"):
        assert part in c["suggested_action"]


def test_abbreviation_heavy_description_is_weak():
    out = run_heuristics([_rec(item_description="BRG BL 6205 ZZ SS")])
    (c,) = _only(out, "weak_description")
    _assert_heuristic(c, "low", 0.6)
    assert "abbreviation-heavy" in c["explanation"]
    assert "4 of 5 words" in c["explanation"]


def test_exactly_three_words_and_ten_chars_is_not_short():
    # Not criterion 1; all three words are short so criterion 2 applies.
    out = run_heuristics([_rec(item_description="abc def gh")])
    (c,) = _only(out, "weak_description")
    assert c["confidence"] == 0.6


def test_short_and_abbreviated_yields_one_candidate_with_short_confidence():
    out = run_heuristics([_rec(item_description="BRG BL")])
    (c,) = _only(out, "weak_description")
    assert c["confidence"] == 0.8


@pytest.mark.parametrize("description", ["Hex bolt steel", "SKF ball bearing 6205"])
def test_adequate_description_is_not_weak(description):
    assert _only(run_heuristics([_rec(item_description=description)]), "weak_description") == []


def test_exactly_half_short_words_is_not_abbreviation_heavy():
    out = run_heuristics([_rec(item_description="BRG ball SS bearing")])
    assert _only(out, "weak_description") == []


@pytest.mark.parametrize("value", [_DROP, None, "", "   ", "N/A", 42, ["bearing"]])
def test_missing_or_invalid_description_is_not_weak(value):
    out = run_heuristics([_rec(item_description=value)])
    assert _only(out, "weak_description") == []


def test_non_ascii_description_counts_unicode_characters():
    out = run_heuristics([_rec(item_description="轴承")])
    (c,) = _only(out, "weak_description")
    assert "1 words, 2 characters" in c["explanation"]
    assert (
        _only(run_heuristics([_rec(item_description="Kugellager für Welle")]), "weak_description")
        == []
    )


# --- duplicate_item_id (Req 9.1) ---


def test_duplicate_item_id_in_same_system_matches_case_and_whitespace():
    records = [_rec(0, item_id="A-1"), _rec(1, item_id=" a-1 ", source_system=" sap ")]
    out = _by_row(run_heuristics(records), "duplicate_item_id")
    assert set(out) == {0, 1}
    _assert_heuristic(out[0], "high", 0.95)
    assert out[0]["field"] == "item_id"
    assert out[0]["item_id"] == "A-1" and out[1]["item_id"] == "a-1"
    assert out[0]["related_item_ids"] == ["a-1"] and out[0]["related_row_indexes"] == [1]
    assert out[1]["related_item_ids"] == ["A-1"] and out[1]["related_row_indexes"] == [0]


def test_three_record_duplicate_group_lists_others_in_row_order():
    records = [_rec(2), _rec(0), _rec(1)]
    out = _by_row(run_heuristics(records), "duplicate_item_id")
    assert set(out) == {0, 1, 2}
    assert out[1]["related_row_indexes"] == [0, 2]
    assert out[1]["related_item_ids"] == ["1001", "1001"]
    assert out[2]["related_row_indexes"] == [0, 1]


@pytest.mark.parametrize("a, b", [(None, _DROP), ("", 7), ("n/a", None)])
def test_missing_or_invalid_source_systems_count_as_equal(a, b):
    records = [_rec(0, source_system=a), _rec(1, source_system=b)]
    assert set(_by_row(run_heuristics(records), "duplicate_item_id")) == {0, 1}


@pytest.mark.parametrize("value", [_DROP, None, "  ", 1001])
def test_missing_or_invalid_item_id_is_not_grouped(value):
    records = [_rec(0, item_id=value), _rec(1, item_id=value)]
    out = run_heuristics(records)
    assert _only(out, "duplicate_item_id") == []
    assert _only(out, "conflicting_source_values") == []


# --- conflicting_source_values (Req 9.2–9.6) ---


def test_conflicting_values_across_systems_names_fields_in_order():
    records = [
        _rec(0),
        _rec(
            1,
            source_system="Oracle",
            unit_of_measure="BOX",
            item_description="Bearing 6205 sealed steel",
        ),
    ]
    out = _by_row(run_heuristics(records), "conflicting_source_values")
    assert set(out) == {0, 1}
    c = out[0]
    _assert_heuristic(c, "medium", 0.85)
    assert c["field"] is None
    assert c["explanation"].endswith("different values in: item_description, unit_of_measure.")
    assert c["related_item_ids"] == ["1001"] and c["related_row_indexes"] == [1]


def test_missing_source_system_differs_from_named_system():
    records = [_rec(0), _rec(1, source_system=None, category="Electrical")]
    out = run_heuristics(records)
    assert set(_by_row(out, "conflicting_source_values")) == {0, 1}
    assert _only(out, "duplicate_item_id") == []


def test_mpn_format_variants_and_text_case_are_not_conflicts():
    records = [
        _rec(0),
        _rec(
            1,
            source_system="Oracle",
            manufacturer_part_number="6205 zz",
            manufacturer=" skf ",
            category="MECHANICAL",
        ),
    ]
    out = run_heuristics(records)
    assert _only(out, "conflicting_source_values") == []
    assert _only(out, "cross_system_duplicate") == []  # Requirement 22 is a separate task


@pytest.mark.parametrize(
    "a, b, conflicts",
    [
        (_DROP, None, False),  # two Missing_Values are equal
        (_DROP, "6205-ZZ", True),  # missing vs present differs
        (42, "9999", False),  # Invalid_Type_Value skips the field
    ],
)
def test_compare_rules_for_missing_and_invalid_values(a, b, conflicts):
    records = [
        _rec(0, manufacturer_part_number=a),
        _rec(1, source_system="Oracle", manufacturer_part_number=b),
    ]
    out = _only(run_heuristics(records), "conflicting_source_values")
    assert bool(out) is conflicts
    if conflicts:
        assert "manufacturer_part_number" in out[0]["explanation"]


def test_mixed_group_gets_duplicate_and_conflict_independently():
    records = [_rec(0), _rec(1), _rec(2, source_system="Oracle", category="Electrical")]
    out = run_heuristics(records)
    dup = _by_row(out, "duplicate_item_id")
    conflict = _by_row(out, "conflicting_source_values")
    assert set(dup) == {0, 1}
    assert set(conflict) == {0, 1, 2}
    assert dup[0]["related_row_indexes"] == [1]
    assert conflict[0]["related_row_indexes"] == [2]
    assert conflict[2]["related_row_indexes"] == [0, 1]


# --- potential_duplicate (Req 9.7–9.11) ---


def test_same_mpn_under_different_item_ids_is_potential_duplicate():
    records = [_rec(0, item_id="1001"), _rec(1, item_id="2002")]
    out = _by_row(run_heuristics(records), "potential_duplicate")
    assert set(out) == {0, 1}
    _assert_heuristic(out[0], "medium", 0.9)
    assert out[0]["field"] == "manufacturer_part_number"
    assert out[0]["related_item_ids"] == ["2002"] and out[1]["related_item_ids"] == ["1001"]


def test_mpn_format_variants_lower_confidence_for_whole_group():
    records = [
        _rec(0, item_id="1001", manufacturer_part_number="6205-ZZ"),
        _rec(1, item_id="2002", manufacturer_part_number="6205 ZZ", manufacturer="skf"),
        _rec(2, item_id="3003", manufacturer_part_number=" 6205-ZZ "),
    ]
    out = _by_row(run_heuristics(records), "potential_duplicate")
    assert set(out) == {0, 1, 2}
    assert {c["confidence"] for c in out.values()} == {0.75}
    assert out[1]["related_item_ids"] == ["1001", "3003"]
    assert out[1]["related_row_indexes"] == [0, 2]


def test_mpn_case_difference_is_a_format_variant():
    records = [_rec(0, item_id="1001"), _rec(1, item_id="2002", manufacturer_part_number="6205-zz")]
    out = _only(run_heuristics(records), "potential_duplicate")
    assert {c["confidence"] for c in out} == {0.75}


@pytest.mark.parametrize("manufacturer", ["UNBRANDED", " unbranded "])
def test_unbranded_items_are_not_part_number_grouped(manufacturer):
    records = [
        _rec(0, item_id="1001", manufacturer=manufacturer),
        _rec(1, item_id="2002", manufacturer=manufacturer),
    ]
    assert _only(run_heuristics(records), "potential_duplicate") == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"manufacturer_part_number": "--"},  # Normalized_MPN is empty
        {"manufacturer_part_number": None},
        {"manufacturer_part_number": 6205},
        {"manufacturer": None},
        {"manufacturer": 5},
    ],
)
def test_records_without_usable_part_number_are_not_grouped(overrides):
    records = [_rec(0, item_id="1001", **overrides), _rec(1, item_id="2002", **overrides)]
    assert _only(run_heuristics(records), "potential_duplicate") == []


def test_different_manufacturers_are_not_potential_duplicates():
    records = [_rec(0, item_id="1001"), _rec(1, item_id="2002", manufacturer="FAG")]
    assert _only(run_heuristics(records), "potential_duplicate") == []


def test_same_item_id_is_not_potential_duplicate():
    out = run_heuristics([_rec(0), _rec(1)])
    assert _only(out, "potential_duplicate") == []


# --- shared behavior ---


def test_invalid_records_get_no_heuristics_and_are_not_related():
    ragged = RawRecord(
        1, dict(CLEAN, item_description="bearing"), CSV_ROW, ragged=True, extra=("x",)
    )
    non_object = RawRecord(2, {}, JSON_NON_OBJECT, value="bearing")
    out = run_heuristics([_rec(0), ragged, non_object])
    assert out == []


def test_duplicate_actions_ask_for_review_and_never_merge():
    records = [
        _rec(0),
        _rec(1),
        _rec(2, source_system="Oracle", category="Electrical"),
        _rec(3, item_id="2002"),
    ]
    out = run_heuristics(records)
    family = [c for c in out if "related_item_ids" in c]
    assert {c["issue_type"] for c in family} == {
        "duplicate_item_id",
        "conflicting_source_values",
        "potential_duplicate",
    }
    for c in family:
        action = c["suggested_action"].lower()
        assert "review" in action and "authoritative" in action
        assert not any(word in action for word in _FORBIDDEN_ACTION_WORDS)


def test_heuristics_do_not_modify_records():
    records = [
        _rec(0, item_id=" A-1 ", item_description="BRG BL"),
        _rec(1, item_id="a-1", source_system="Oracle", manufacturer_part_number="6205 zz"),
        _rec(2, item_id="B-2", manufacturer=" UNBRANDED "),
    ]
    before = copy.deepcopy(records)
    run_heuristics(records)
    assert records == before
    assert [r.fields for r in records] == [r.fields for r in before]
