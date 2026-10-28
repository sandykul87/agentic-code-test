import copy
import json

import pytest

from dq_assistant.loader import CSV_ROW, JSON_NON_OBJECT, JSON_OBJECT, RawRecord, load
from dq_assistant.models import REQUIRED_FIELDS, UOM_ALLOW_LIST
from dq_assistant.rules import run_rules

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


def _assert_rule(c, severity, confidence):
    assert c["severity"] == severity
    assert c["confidence"] == confidence
    assert c["source"] == "deterministic_rule"
    assert c["status"] == "needs_review"
    assert "candidate" in c["explanation"].lower()


def test_clean_record_yields_no_candidates():
    assert run_rules([_rec()]) == []


# --- invalid_record (Req 5.1, 5.2) ---


@pytest.mark.parametrize("value", [42, "text", True, ["a"], None])
def test_non_object_json_record_is_one_invalid_record(value):
    out = run_rules([RawRecord(3, {}, JSON_NON_OBJECT, value=value)])
    assert len(out) == 1
    c = out[0]
    assert c["issue_type"] == "invalid_record"
    assert c["item_id"] is None and c["field"] is None and c["row_index"] == 3
    _assert_rule(c, "high", 1.0)


def test_ragged_csv_row_is_only_invalid_record(tmp_path):
    path = tmp_path / "in.csv"
    path.write_text("item_id,manufacturer\n1001,SKF,extra\n,\n", encoding="utf-8")
    records = load(str(path))
    out = run_rules(records)
    row0 = [c for c in out if c["row_index"] == 0]
    assert [c["issue_type"] for c in row0] == ["invalid_record"]
    assert row0[0]["item_id"] is None
    _assert_rule(row0[0], "high", 1.0)
    # The short row is not invalid; absent cells are Missing_Values (Req 5.3).
    row1 = [c for c in out if c["row_index"] == 1]
    assert not _only(row1, "invalid_record")
    assert len(_only(row1, "missing_required_field")) == 6


# --- missing_required_field (Req 5.4, 5.5, 5.9, 5.10) ---


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
@pytest.mark.parametrize("value", [_DROP, None, "", "   ", "N/A", "null"])
def test_missing_required_field(field, value):
    out = _only(run_rules([_rec(**{field: value})]), "missing_required_field")
    assert [c["field"] for c in out] == [field]
    _assert_rule(out[0], "high" if field == "item_id" else "medium", 1.0)


def test_missing_item_id_sets_null_item_id_on_every_candidate():
    out = run_rules([_rec(row_index=7, item_id="  ", unit_of_measure="pcs")])
    assert {c["issue_type"] for c in out} == {
        "missing_required_field",
        "unsupported_unit_of_measure",
    }
    assert all(c["item_id"] is None and c["row_index"] == 7 for c in out)


def test_missing_mpn_alone_is_not_missing_required_field():
    out = run_rules([_rec(manufacturer_part_number="")])
    assert not _only(out, "missing_required_field")


def test_all_blank_record_yields_six_missing_required_fields():
    blank = {name: "" for name in CLEAN}
    out = run_rules([RawRecord(0, blank, CSV_ROW)])
    assert sorted(c["field"] for c in out) == sorted(REQUIRED_FIELDS)
    assert all(c["issue_type"] == "missing_required_field" for c in out)


def test_missing_manufacturer_action_mentions_unbranded():
    out = run_rules([_rec(manufacturer=None, manufacturer_part_number=None)])
    assert [c["issue_type"] for c in out] == ["missing_required_field"]
    action = out[0]["suggested_action"]
    assert "confirm" in action.lower() and "UNBRANDED" in action


# --- invalid_field_type (Req 5.6, 5.8, 5.9) ---


@pytest.mark.parametrize(
    "value, type_name",
    [(1001, "number"), (1.5, "number"), (True, "boolean"), (False, "boolean"),
     (0, "number"), (["a"], "list"), ({"a": 1}, "object")],
)
def test_invalid_field_type_names_observed_type(value, type_name):
    out = run_rules([_rec(category=value)])
    assert len(out) == 1
    c = out[0]
    assert c["issue_type"] == "invalid_field_type" and c["field"] == "category"
    assert f"type {type_name}" in c["explanation"]
    _assert_rule(c, "medium", 1.0)


def test_invalid_item_id_suppresses_missing_and_nulls_item_id():
    out = run_rules([_rec(row_index=2, item_id=1001, manufacturer_part_number="")])
    types = sorted((c["issue_type"], c["field"]) for c in out)
    assert types == [
        ("invalid_field_type", "item_id"),
        ("missing_part_number", "manufacturer_part_number"),
    ]
    assert all(c["item_id"] is None for c in out)
    assert "1001" not in json.dumps([c["explanation"] for c in out])


def test_invalid_uom_type_suppresses_uom_check():
    out = run_rules([_rec(unit_of_measure=12)])
    assert [c["issue_type"] for c in out] == ["invalid_field_type"]


def test_invalid_mpn_type_is_reported_and_no_part_number_candidate():
    out = run_rules([_rec(manufacturer_part_number=6205)])
    assert [(c["issue_type"], c["field"]) for c in out] == [
        ("invalid_field_type", "manufacturer_part_number")
    ]


def test_unknown_fields_are_ignored():
    out = run_rules([_rec(Item_ID=5, extra=None, notes=["x"])])
    assert out == []


# --- missing_part_number (Req 6) ---


@pytest.mark.parametrize("mpn", [_DROP, None, "", "  ", "N/A"])
def test_missing_part_number(mpn):
    out = run_rules([_rec(manufacturer_part_number=mpn)])
    assert len(out) == 1
    c = out[0]
    assert c["issue_type"] == "missing_part_number"
    assert c["field"] == "manufacturer_part_number" and c["item_id"] == "1001"
    assert c["explanation"].startswith("Candidate issue:")
    assert c["suggested_action"] == "Confirm the manufacturer part number with the source owner."
    assert "suggested_value" not in c and "6205" not in c["explanation"]
    _assert_rule(c, "medium", 0.95)


@pytest.mark.parametrize("mfr", ["UNBRANDED", "unbranded", " Unbranded ", "\tUnBrAnDeD\n"])
def test_unbranded_is_present_and_exempt_from_part_number(mfr):
    out = run_rules([_rec(manufacturer=mfr, manufacturer_part_number="")])
    assert out == []


def test_unbranded_prefix_is_a_real_manufacturer():
    out = run_rules([_rec(manufacturer="Unbranded Generic", manufacturer_part_number="")])
    assert [c["issue_type"] for c in out] == ["missing_part_number"]


def test_invalid_manufacturer_type_gives_no_part_number_candidate():
    out = run_rules([_rec(manufacturer=True, manufacturer_part_number="")])
    assert [c["issue_type"] for c in out] == ["invalid_field_type"]


# --- unsupported_unit_of_measure (Req 7) ---


@pytest.mark.parametrize("uom", sorted(UOM_ALLOW_LIST) + ["ea", "EA ", " roll", "Kg"])
def test_allowed_uom_case_insensitive(uom):
    assert run_rules([_rec(unit_of_measure=uom)]) == []


@pytest.mark.parametrize("uom", ["EACH", "pcs", "bx"])
def test_unsupported_uom(uom):
    out = run_rules([_rec(unit_of_measure=f" {uom} ")])
    assert len(out) == 1
    c = out[0]
    assert c["issue_type"] == "unsupported_unit_of_measure" and c["field"] == "unit_of_measure"
    assert f"'{uom}'" in c["explanation"]
    assert "confirm" in c["suggested_action"].lower()
    _assert_rule(c, "medium", 0.9)


def test_unsupported_uom_truncates_observed_value_to_50_chars():
    long_value = "X" * 49 + "YZ" + "W" * 100
    out = run_rules([_rec(unit_of_measure=long_value)])
    explanation = out[0]["explanation"]
    assert ("X" * 49 + "Y") in explanation
    assert "Z" not in explanation and "W" not in explanation


def test_missing_uom_gives_only_missing_required_field():
    out = run_rules([_rec(unit_of_measure="")])
    assert [(c["issue_type"], c["field"]) for c in out] == [
        ("missing_required_field", "unit_of_measure")
    ]


# --- general guarantees ---


def test_rules_do_not_mutate_records():
    records = [
        _rec(0, item_id=1001, manufacturer_part_number=""),
        _rec(1, unit_of_measure="  pcs  ", manufacturer=" Unbranded "),
        RawRecord(2, {}, JSON_NON_OBJECT, value=[1, 2]),
        RawRecord(3, {"item_id": " A1 "}, CSV_ROW, ragged=True, extra=("x",)),
    ]
    before = copy.deepcopy(records)
    run_rules(records)
    assert records == before
    assert [r.value for r in records] == [r.value for r in before]


def test_finding_ids_unique_and_output_deterministic():
    records = [_rec(i, item_id="", unit_of_measure="pcs", category=1) for i in range(3)]
    first = run_rules(records)
    assert first == run_rules(records)
    ids = [c["finding_id"] for c in first]
    assert len(ids) == len(set(ids))
