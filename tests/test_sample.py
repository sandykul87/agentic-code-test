"""Integration tests for Sample_Mode (``--sample``) — Requirement 21.

These exercise ``cli.main`` with ``--sample json|csv``: writing bytes to
stdout or an ``--output`` file, the Field_Guide on stderr, exclusive-create
refusal of an existing path, an unwritable path, ``--no-ai`` having no effect,
determinism, and — the critical guarantee (Req 21.11 / 18.13) — that a sample
fed back through Report_Mode produces an empty ``candidates`` list.

The bundled sample bytes are read here the same way the CLI reads them, via
``importlib.resources``, so the tests assert byte-for-byte equality.
"""

import json
from importlib.resources import files

import pytest

from dq_assistant.cli import EXIT_OK, EXIT_OUTPUT, EXIT_USAGE, main

SAMPLE_FORMATS = ("json", "csv")


def _bundled_bytes(fmt: str) -> bytes:
    return (files("dq_assistant.samples") / f"sample.{fmt}").read_bytes()


# --- Req 21.9: the bundled samples meet their structural constraints ---


@pytest.mark.parametrize("fmt", SAMPLE_FORMATS)
def test_bundled_sample_is_valid_utf8_with_3_to_10_records(fmt):
    raw = _bundled_bytes(fmt)
    text = raw.decode("utf-8")  # must decode as UTF-8
    if fmt == "json":
        records = json.loads(text)
        assert isinstance(records, list)
        assert all(isinstance(r, dict) for r in records)  # top-level list of objects
    else:
        rows = [line for line in text.splitlines() if line]
        records = rows[1:]  # drop header
    assert 3 <= len(records) <= 10


def test_json_sample_every_record_has_seven_keys():
    records = json.loads(_bundled_bytes("json").decode("utf-8"))
    seven = {
        "item_id",
        "item_description",
        "manufacturer",
        "manufacturer_part_number",
        "category",
        "unit_of_measure",
        "source_system",
    }
    for record in records:
        assert set(record) == seven


def test_json_sample_has_unbranded_and_real_manufacturer_records():
    records = json.loads(_bundled_bytes("json").decode("utf-8"))
    unbranded = [
        r
        for r in records
        if r["manufacturer"].strip().lower() == "unbranded"
        and r["manufacturer_part_number"] == ""
    ]
    real = [
        r
        for r in records
        if r["manufacturer"].strip().lower() not in ("unbranded", "")
        and r["manufacturer_part_number"].strip() != ""
    ]
    assert unbranded  # Req 21.9: at least one UNBRANDED record with empty MPN
    assert real  # Req 21.9: at least one real manufacturer with a part number


def test_csv_sample_header_and_every_row_have_seven_columns():
    text = _bundled_bytes("csv").decode("utf-8")
    rows = [line for line in text.splitlines() if line]
    header = rows[0].split(",")
    assert header == [
        "item_id",
        "item_description",
        "manufacturer",
        "manufacturer_part_number",
        "category",
        "unit_of_measure",
        "source_system",
    ]
    for row in rows[1:]:
        assert len(row.split(",")) == 7


# --- Req 21.1: stdout bytes, Field_Guide on stderr, no file, exit 0 ---


@pytest.mark.parametrize("fmt", SAMPLE_FORMATS)
def test_sample_to_stdout_matches_bundled_bytes(fmt, capsysbinary):
    code = main(["--sample", fmt])
    captured = capsysbinary.readouterr()
    assert code == EXIT_OK
    assert captured.out == _bundled_bytes(fmt)  # byte-for-byte, incl. line endings
    assert captured.err  # Field_Guide written to stderr


@pytest.mark.parametrize("fmt", SAMPLE_FORMATS)
def test_sample_to_stdout_creates_no_file(fmt, tmp_path, capsysbinary, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["--sample", fmt])
    capsysbinary.readouterr()
    assert list(tmp_path.iterdir()) == []  # nothing written to disk


# --- Req 21.2: --output creates the file, stdout empty, Field_Guide on stderr ---


@pytest.mark.parametrize("fmt", SAMPLE_FORMATS)
def test_sample_to_output_file_matches_bundled_bytes(fmt, tmp_path, capsysbinary):
    out_path = tmp_path / f"out.{fmt}"
    code = main(["--sample", fmt, "--output", str(out_path)])
    captured = capsysbinary.readouterr()
    assert code == EXIT_OK
    assert captured.out == b""  # nothing to stdout in --output mode
    assert captured.err  # Field_Guide on stderr
    assert out_path.read_bytes() == _bundled_bytes(fmt)


@pytest.mark.parametrize("fmt", SAMPLE_FORMATS)
def test_sample_stdout_and_file_bytes_are_equal(fmt, tmp_path, capsysbinary):
    stdout_bytes = None
    main(["--sample", fmt])
    stdout_bytes = capsysbinary.readouterr().out
    out_path = tmp_path / f"out.{fmt}"
    main(["--sample", fmt, "--output", str(out_path)])
    capsysbinary.readouterr()
    assert out_path.read_bytes() == stdout_bytes


# --- Req 21.4: exclusive-create refuses an existing path, unchanged ---


def test_sample_output_existing_file_refused_unchanged(tmp_path, capsys):
    out_path = tmp_path / "exists.csv"
    out_path.write_text("original contents", encoding="utf-8")
    before = out_path.read_bytes()
    code = main(["--sample", "csv", "--output", str(out_path)])
    captured = capsys.readouterr()

    assert code == EXIT_OUTPUT
    assert captured.out == ""
    assert captured.err.strip().count("\n") == 0  # exactly one line
    assert "already exists" in captured.err
    assert out_path.read_bytes() == before  # unchanged


def test_sample_output_existing_directory_refused(tmp_path, capsys):
    out_path = tmp_path / "adir"
    out_path.mkdir()
    code = main(["--sample", "json", "--output", str(out_path)])
    captured = capsys.readouterr()
    assert code == EXIT_OUTPUT
    assert captured.out == ""
    assert "already exists" in captured.err
    assert out_path.is_dir()  # left as a directory


def test_sample_output_existing_symlink_refused_unchanged(tmp_path, capsys):
    target = tmp_path / "target.json"
    target.write_text("target data", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    code = main(["--sample", "json", "--output", str(link)])
    captured = capsys.readouterr()
    assert code == EXIT_OUTPUT
    assert captured.out == ""
    assert "already exists" in captured.err
    assert link.is_symlink()  # link itself untouched
    assert target.read_text(encoding="utf-8") == "target data"


# --- Req 21.5: unwritable path -> exit 1, names path, no partial file ---


def test_sample_output_unwritable_path_exits_one_no_partial(tmp_path, capsys):
    out_path = tmp_path / "no_such_dir" / "out.json"  # parent missing
    code = main(["--sample", "json", "--output", str(out_path)])
    captured = capsys.readouterr()

    assert code == EXIT_OUTPUT
    assert captured.out == ""
    assert captured.err.strip().count("\n") == 0
    assert str(out_path) in captured.err
    assert not out_path.exists()  # no partial file left behind


# --- Req 21.6: --sample together with an input file (18.14) ---


def test_sample_with_input_file_usage_error_no_file(tmp_path, capsys):
    src = tmp_path / "items.json"
    src.write_text("[]", encoding="utf-8")
    out_path = tmp_path / "out.json"
    with pytest.raises(SystemExit) as exc:
        main([str(src), "--sample", "json", "--output", str(out_path)])
    captured = capsys.readouterr()

    assert exc.value.code == EXIT_USAGE
    assert captured.out == ""
    assert captured.err  # usage message on stderr
    assert not out_path.exists()  # no file created


# --- Req 21.7: bad --sample value / missing value -> exit 2, names json & csv ---


@pytest.mark.parametrize("bad", ["JSON", "Csv", "xml"])
def test_bad_sample_format_rejected_exit_two(bad, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--sample", bad])
    captured = capsys.readouterr()
    assert exc.value.code == EXIT_USAGE
    assert captured.out == ""
    assert "json" in captured.err and "csv" in captured.err


def test_sample_with_no_value_rejected_exit_two(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--sample"])
    captured = capsys.readouterr()
    assert exc.value.code == EXIT_USAGE
    assert captured.out == ""


# --- Req 21.8: --no-ai has no effect on Sample_Mode output ---


@pytest.mark.parametrize("fmt", SAMPLE_FORMATS)
def test_no_ai_does_not_change_sample_output(fmt, tmp_path, capsysbinary):
    main(["--sample", fmt])
    plain = capsysbinary.readouterr()
    main(["--sample", fmt, "--no-ai"])
    with_flag = capsysbinary.readouterr()
    assert with_flag.out == plain.out
    assert with_flag.err == plain.err


# --- Req 21.10: Field_Guide content ---


def test_field_guide_lists_fields_unbranded_and_command(capsys):
    main(["--sample", "json"])
    err = capsys.readouterr().err
    assert 1 <= err.strip().count("\n") + 1 <= 15  # 1 to 15 lines
    for field in (
        "item_id",
        "item_description",
        "manufacturer",
        "category",
        "unit_of_measure",
        "source_system",
        "manufacturer_part_number",
    ):
        assert field in err
    assert "UNBRANDED" in err
    assert "python -m dq_assistant" in err


def test_field_guide_shows_output_path_when_given(tmp_path, capsys):
    out_path = tmp_path / "template.json"
    main(["--sample", "json", "--output", str(out_path)])
    err = capsys.readouterr().err
    assert str(out_path) in err  # command points at the --output path


def test_field_guide_shows_matching_extension_without_output(capsys):
    main(["--sample", "csv"])
    err = capsys.readouterr().err
    assert ".csv" in err  # filename matches the --sample value


# --- Req 21.12: determinism ---


@pytest.mark.parametrize("fmt", SAMPLE_FORMATS)
def test_sample_output_is_deterministic(fmt, capsysbinary):
    main(["--sample", fmt])
    first = capsysbinary.readouterr()
    main(["--sample", fmt])
    second = capsysbinary.readouterr()
    assert first.out == second.out
    assert first.err == second.err


# --- Req 21.11 / 18.13: sample fed back yields zero candidates ---


@pytest.mark.parametrize("fmt", SAMPLE_FORMATS)
@pytest.mark.parametrize("extra", [[], ["--no-ai"]])
def test_sample_fed_back_through_report_mode_has_no_candidates(fmt, extra, tmp_path, capsys):
    out_path = tmp_path / f"sample.{fmt}"
    code = main(["--sample", fmt, "--output", str(out_path)])
    assert code == EXIT_OK
    capsys.readouterr()

    code = main([str(out_path), *extra])
    report_out = capsys.readouterr().out
    assert code == EXIT_OK
    report = json.loads(report_out)
    assert report["candidates"] == []  # Req 21.11: clean, valid file
    assert report["summary"]["candidates_total"] == 0


def test_sample_json_stdout_without_output_equals_bundled_bytes(capsysbinary):
    main(["--sample", "json"])
    out = capsysbinary.readouterr().out
    assert out == _bundled_bytes("json")  # Req 18.13 stdout equals bundled bytes
