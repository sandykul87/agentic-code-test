import os

import pytest

from dq_assistant import fields
from dq_assistant.loader import (
    CSV_ROW,
    JSON_NON_OBJECT,
    JSON_OBJECT,
    MAX_INPUT_BYTES,
    InputError,
    load,
)

SECRET = "SECRETVALUE123"


def write(tmp_path, name, content):
    p = tmp_path / name
    p.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return str(p)


def expect_error(path, fragment):
    with pytest.raises(InputError) as info:
        load(path)
    err = info.value
    assert err.exit_code == 2
    assert fragment in err.message
    assert "\n" not in err.message
    assert SECRET not in err.message
    assert "Traceback" not in err.message
    # No chained parser exception (which could carry file content) is exposed.
    assert err.__cause__ is None
    assert err.__context__ is None or err.__suppress_context__
    return err


# --- Req 3 errors -----------------------------------------------------------

def test_missing_path(tmp_path):
    expect_error(str(tmp_path / "nope.json"), "Cannot read input file")


def test_directory_path(tmp_path):
    d = tmp_path / "dir.json"
    d.mkdir()
    expect_error(str(d), "Cannot read input file")


@pytest.mark.parametrize("name", ["a.txt", "a.xlsx", "noext"])
def test_unsupported_extension(tmp_path, name):
    expect_error(write(tmp_path, name, SECRET), ".json or .csv")


def test_oversized(tmp_path):
    path = write(tmp_path, "big.json", b"[" + b" " * MAX_INPUT_BYTES + b"]")
    expect_error(path, "5 MiB")


def test_exact_size_accepted(tmp_path):
    body = b'[{"item_id": "1"}]'
    path = write(tmp_path, "edge.json", body + b" " * (MAX_INPUT_BYTES - len(body)))
    assert os.path.getsize(path) == MAX_INPUT_BYTES
    assert len(load(path)) == 1


def test_invalid_utf8(tmp_path):
    expect_error(write(tmp_path, "a.csv", "item_id\ncafé\n".encode("latin-1")), "UTF-8")


@pytest.mark.parametrize("content", ["", " \t\r\n  \n"])
def test_empty(tmp_path, content):
    expect_error(write(tmp_path, "a.json", content), "empty")


def test_truncated_json(tmp_path):
    expect_error(write(tmp_path, "a.json", f'[{{"item_id": "{SECRET}"'), "not valid JSON")


@pytest.mark.parametrize("content", ['{"a": 1}', '"x"', "3", "true", "null"])
def test_json_not_list(tmp_path, content):
    expect_error(write(tmp_path, "a.json", content), "list of records")


def test_csv_unrecognized_header(tmp_path):
    expect_error(write(tmp_path, "a.csv", f"foo,bar\n{SECRET},2\n"), "header")


@pytest.mark.parametrize("name,content", [("a.json", "[]"), ("a.csv", "item_id,category\n\n")])
def test_zero_records(tmp_path, name, content):
    expect_error(write(tmp_path, name, content), "No records")


# --- precedence (Req 3.11) ----------------------------------------------------

def test_extension_before_size(tmp_path):
    expect_error(write(tmp_path, "a.txt", b" " * (MAX_INPUT_BYTES + 1)), ".json or .csv")


def test_size_before_encoding(tmp_path):
    expect_error(write(tmp_path, "a.json", b"\xff" * (MAX_INPUT_BYTES + 1)), "5 MiB")


def test_encoding_before_empty(tmp_path):
    expect_error(write(tmp_path, "a.json", b"  \xff  "), "UTF-8")


def test_header_before_zero_records(tmp_path):
    expect_error(write(tmp_path, "a.csv", "foo,bar\n"), "header")


# --- JSON loading ---------------------------------------------------------------

def test_json_records_keep_types_and_order(tmp_path):
    path = write(tmp_path, "a.JSON", '[{"item_id": "  A1 ", "n": 3, "Item_ID": null}, 5, [1]]')
    recs = load(path)
    assert [r.row_index for r in recs] == [0, 1, 2]
    assert recs[0].kind == JSON_OBJECT
    assert recs[0].fields == {"item_id": "  A1 ", "n": 3, "Item_ID": None}
    assert recs[1].kind == JSON_NON_OBJECT and recs[1].value == 5 and recs[1].fields == {}
    assert recs[2].kind == JSON_NON_OBJECT
    assert fields.read(recs[0], "item_id") == (fields.PRESENT, "A1")


# --- CSV loading ----------------------------------------------------------------

def test_csv_bom_and_mixed_case_headers(tmp_path):
    path = write(tmp_path, "a.CSV", "\ufeff ITEM_ID , Category,Extra\n A1 ,Tools,x\n")
    (rec,) = load(path)
    assert rec.kind == CSV_ROW
    assert rec.fields == {"item_id": " A1 ", "category": "Tools", "extra": "x"}


def test_csv_duplicate_header_last_wins(tmp_path):
    (rec,) = load(write(tmp_path, "a.csv", "Item_ID,item_id\nfirst,second\n"))
    assert rec.fields == {"item_id": "second"}


def test_csv_ragged_rows(tmp_path):
    recs = load(write(tmp_path, "a.csv", "item_id,category,uom\nA,B,C,D,E\nX\n"))
    long, short = recs
    assert long.ragged and long.extra == ("D", "E")
    assert long.fields == {"item_id": "A", "category": "B", "uom": "C"}
    assert not short.ragged and short.fields == {"item_id": "X"}
    assert fields.read(short, "category") == (fields.MISSING, None)


def test_csv_quoted_commas_and_newlines(tmp_path):
    (rec,) = load(write(tmp_path, "a.csv", 'item_id,item_description\nA,"bolt, hex\nM8"\n'))
    assert rec.fields["item_description"] == "bolt, hex\nM8"


def test_csv_blank_lines_skipped(tmp_path):
    recs = load(write(tmp_path, "a.csv", "item_id\r\n\r\nA\r\n\r\nB\r\n"))
    assert [(r.row_index, r.fields["item_id"]) for r in recs] == [(0, "A"), (1, "B")]
