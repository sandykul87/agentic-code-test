import copy
from types import SimpleNamespace

import pytest

from dq_assistant.fields import (
    INVALID_TYPE,
    MISSING,
    PRESENT,
    is_unbranded,
    normalize_mpn,
    normalize_text,
    read,
)


def test_absent_field_is_missing():
    assert read({}, "item_id") == (MISSING, None)


def test_none_is_missing():
    assert read({"item_id": None}, "item_id") == (MISSING, None)


@pytest.mark.parametrize(
    "value",
    ["", "   ", "\t\n", "\u00a0", "null", "NULL", " None ", "none", "N/A", "n/a", "\tN/a "],
)
def test_blank_and_placeholders_are_missing(value):
    assert read({"f": value}, "f") == (MISSING, None)


@pytest.mark.parametrize("value", [0, 1.5, False, True, [], ["x"], {}, {"a": 1}])
def test_non_string_is_invalid_type(value):
    assert read({"f": value}, "f") == (INVALID_TYPE, None)


def test_present_is_trimmed_case_preserved():
    assert read({"f": "  SKF Bearing 6205 ZZ\t"}, "f") == (PRESENT, "SKF Bearing 6205 ZZ")


def test_placeholder_inside_longer_value_is_present():
    assert read({"f": "N/A bracket"}, "f") == (PRESENT, "N/A bracket")


def test_unbranded_is_present_and_case_kept():
    assert read({"manufacturer": " Unbranded "}, "manufacturer") == (PRESENT, "Unbranded")


def test_reads_object_with_fields_mapping():
    rec = SimpleNamespace(fields={"item_id": " 1001 "})
    assert read(rec, "item_id") == (PRESENT, "1001")


def test_repeat_read_is_stable_and_record_unchanged():
    rec = {"a": " x ", "b": None, "c": 5, "d": ["l"], "e": {"k": "v"}, "f": "n/a"}
    before = copy.deepcopy(rec)
    for field in list(rec) + ["absent"]:
        assert read(rec, field) == read(rec, field)
    assert rec == before


@pytest.mark.parametrize("value", ["UNBRANDED", "unbranded", " Unbranded ", "\tUnBranded\n"])
def test_is_unbranded_matches(value):
    assert is_unbranded(value)


@pytest.mark.parametrize("value", ["Unbranded Generic", "un branded", "", "SKF"])
def test_is_unbranded_rejects(value):
    assert not is_unbranded(value)


def test_normalize_text():
    assert normalize_text("  SKF   Bearing\t6205 ") == "skf bearing 6205"
    assert normalize_text("ABC") == normalize_text(" abc ")


def test_normalize_mpn():
    assert normalize_mpn("6205-ZZ") == "6205ZZ"
    assert normalize_mpn("6205 zz") == "6205ZZ"
    assert normalize_mpn("a.b/c_d-e f") == "ABCDEF"
