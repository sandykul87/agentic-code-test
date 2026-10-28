"""Integration tests for the CLI (Requirements 1, 15, 20).

These exercise ``cli.main`` end to end: the full Report_Mode pipeline, exit
codes 0/2/1, ``--no-ai`` filtering, output-to-file vs stdout, ``--help``
precedence, the output-equals-input overwrite guard, an unwritable output
path, the missing-argument usage error, and the no-mutation guarantee.

Fixtures are written to temporary files so the tests do not depend on the
demo inputs added in a later task.
"""

import json

import pytest

from dq_assistant.cli import EXIT_OK, EXIT_OUTPUT, EXIT_USAGE, build_parser, main

# A small record set that together triggers several Issue_Types: a real
# manufacturer with no part number (missing_part_number), a bad unit of
# measure (unsupported_unit_of_measure), an UNBRANDED record (no part-number
# finding), and a description keyword that mismatches the category
# (category_mismatch_candidate from the AI stub).
_RECORDS = [
    {
        "item_id": "1001",
        "item_description": "Deep groove ball bearing 6205 ZZ sealed",
        "manufacturer": "SKF",
        "manufacturer_part_number": "",
        "category": "Electrical",
        "unit_of_measure": "EA",
        "source_system": "ERP",
    },
    {
        "item_id": "1002",
        "item_description": "Generic cleaning cloth pack",
        "manufacturer": "UNBRANDED",
        "manufacturer_part_number": "",
        "category": "Safety",
        "unit_of_measure": "WIDGET",
        "source_system": "ERP",
    },
]


def _write_json(path, records):
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def _write_csv(path, records):
    fields = [
        "item_id",
        "item_description",
        "manufacturer",
        "manufacturer_part_number",
        "category",
        "unit_of_measure",
        "source_system",
    ]
    lines = [",".join(fields)]
    for record in records:
        lines.append(",".join(str(record.get(f, "")) for f in fields))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# --- full run on an input file (Req 1.1, 1.8) ---


def test_report_to_stdout_is_one_json_document_exit_zero(tmp_path, capsys):
    src = _write_json(tmp_path / "items.json", _RECORDS)
    code = main([str(src)])
    captured = capsys.readouterr()

    assert code == EXIT_OK
    report = json.loads(captured.out)  # exactly one JSON document on stdout
    assert report["summary"]["records_read"] == 2
    assert report["summary"]["ai_enabled"] is True
    assert captured.out.endswith("\n")


def test_full_run_on_csv_input(tmp_path, capsys):
    src = _write_csv(tmp_path / "items.csv", _RECORDS)
    code = main([str(src)])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    report = json.loads(captured.out)
    assert report["summary"]["records_read"] == 2


def test_clean_input_still_exits_zero_with_empty_candidates(tmp_path, capsys):
    clean = [
        {
            "item_id": "2001",
            "item_description": "Stainless steel hexagonal bolt forty millimetre",
            "manufacturer": "UNBRANDED",
            "manufacturer_part_number": "",
            "category": "Mechanical",
            "unit_of_measure": "EA",
            "source_system": "ERP",
        }
    ]
    src = _write_json(tmp_path / "clean.json", clean)
    code = main([str(src)])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    report = json.loads(captured.out)
    assert report["candidates"] == []


# --- --no-ai filtering (Req 1.7, 16.7) ---


def test_no_ai_excludes_ai_candidates(tmp_path, capsys):
    src = _write_json(tmp_path / "items.json", _RECORDS)

    with_ai = json.loads(_run_capture(capsys, [str(src)]))
    without_ai = json.loads(_run_capture(capsys, [str(src), "--no-ai"]))

    assert with_ai["summary"]["ai_enabled"] is True
    assert without_ai["summary"]["ai_enabled"] is False
    assert without_ai["summary"]["ai_suggestions_rejected"] == 0
    assert without_ai["summary"]["ai_errors"] == 0
    assert without_ai["summary"]["by_source"]["ai_suggestion"] == 0
    for candidate in without_ai["candidates"]:
        assert candidate["source"] in ("deterministic_rule", "heuristic")
    # The AI run found at least one category mismatch the --no-ai run drops.
    assert with_ai["summary"]["by_source"]["ai_suggestion"] >= 1


def _run_capture(capsys, argv):
    """Run main and return captured stdout, asserting a clean exit."""
    code = main(argv)
    out = capsys.readouterr().out
    assert code == EXIT_OK
    return out


# --- output file vs stdout (Req 1.1, 1.3) ---


def test_output_file_written_and_stdout_empty(tmp_path, capsys):
    src = _write_json(tmp_path / "items.json", _RECORDS)
    out_path = tmp_path / "report.json"
    code = main([str(src), "--output", str(out_path)])
    captured = capsys.readouterr()

    assert code == EXIT_OK
    assert captured.out == ""  # nothing to stdout in --output mode
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["summary"]["records_read"] == 2


def test_output_replaces_existing_file(tmp_path, capsys):
    src = _write_json(tmp_path / "items.json", _RECORDS)
    out_path = tmp_path / "report.json"
    out_path.write_text("stale contents", encoding="utf-8")
    code = main([str(src), "--output", str(out_path)])

    assert code == EXIT_OK
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["summary"]["records_read"] == 2


def test_stdout_and_file_reports_match(tmp_path, capsys):
    src = _write_json(tmp_path / "items.json", _RECORDS)
    stdout_text = _run_capture(capsys, [str(src)])
    out_path = tmp_path / "report.json"
    main([str(src), "--output", str(out_path)])
    capsys.readouterr()
    assert out_path.read_text(encoding="utf-8") == stdout_text


# --- exit code 2: usage / input errors (Req 1.6, 3) ---


def test_missing_arg_is_usage_error_exit_two(capsys):
    with pytest.raises(SystemExit) as exc:
        main([])
    captured = capsys.readouterr()
    assert exc.value.code == EXIT_USAGE
    assert captured.err  # usage message to stderr
    assert captured.out == ""


def test_unknown_option_is_usage_error_exit_two(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--nope"])
    captured = capsys.readouterr()
    assert exc.value.code == EXIT_USAGE
    assert captured.err
    assert captured.out == ""


def test_sample_with_input_is_usage_error_exit_two(tmp_path, capsys):
    src = _write_json(tmp_path / "items.json", _RECORDS)
    with pytest.raises(SystemExit) as exc:
        main([str(src), "--sample", "json"])
    captured = capsys.readouterr()
    assert exc.value.code == EXIT_USAGE
    assert captured.err
    assert captured.out == ""


def test_input_error_from_loader_exits_two_one_line(tmp_path, capsys):
    missing = tmp_path / "does_not_exist.json"
    code = main([str(missing)])
    captured = capsys.readouterr()
    assert code == EXIT_USAGE
    assert captured.out == ""
    assert captured.err.strip().count("\n") == 0  # exactly one line
    assert "Traceback" not in captured.err


def test_unsupported_extension_exits_two(tmp_path, capsys):
    bad = tmp_path / "items.txt"
    bad.write_text("whatever", encoding="utf-8")
    code = main([str(bad)])
    captured = capsys.readouterr()
    assert code == EXIT_USAGE
    assert ".json" in captured.err and ".csv" in captured.err
    assert captured.out == ""


# --- exit code 1: output write failures (Req 1.4, 1.5, 15.4) ---


def test_output_equals_input_refused_input_unchanged(tmp_path, capsys):
    src = _write_json(tmp_path / "items.json", _RECORDS)
    before = src.read_bytes()
    code = main([str(src), "--output", str(src)])
    captured = capsys.readouterr()

    assert code == EXIT_OUTPUT
    assert captured.out == ""
    assert "overwrite the input" in captured.err
    assert src.read_bytes() == before  # byte-for-byte unchanged


def test_output_equals_input_via_relative_path_refused(tmp_path, capsys, monkeypatch):
    src = _write_json(tmp_path / "items.json", _RECORDS)
    before = src.read_bytes()
    monkeypatch.chdir(tmp_path)
    code = main(["items.json", "--output", str(src)])
    captured = capsys.readouterr()
    assert code == EXIT_OUTPUT
    assert "overwrite the input" in captured.err
    assert src.read_bytes() == before


def test_unwritable_output_path_exits_one_names_path(tmp_path, capsys):
    src = _write_json(tmp_path / "items.json", _RECORDS)
    out_path = tmp_path / "no_such_dir" / "report.json"  # parent missing
    code = main([str(src), "--output", str(out_path)])
    captured = capsys.readouterr()

    assert code == EXIT_OUTPUT
    assert captured.out == ""
    assert str(out_path) in captured.err
    assert not out_path.exists()


# --- --help precedence (Req 20.1-20.3, 19.21) ---


def test_help_exits_zero_usage_on_stdout_stderr_empty(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    captured = capsys.readouterr()
    assert exc.value.code == EXIT_OK
    assert captured.err == ""
    for token in ("--output", "--no-ai", "--sample", "UNBRANDED", "5 MiB"):
        assert token in captured.out


def test_short_help_flag_behaves_like_long(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["-h"])
    captured = capsys.readouterr()
    assert exc.value.code == EXIT_OK
    assert captured.err == ""
    assert "usage" in captured.out.lower()


def test_help_wins_over_other_args_and_touches_no_file(tmp_path, capsys):
    missing_input = tmp_path / "never_opened.json"
    out_path = tmp_path / "never_created.json"
    with pytest.raises(SystemExit) as exc:
        main([str(missing_input), "--output", str(out_path), "--sample", "json", "-h"])
    captured = capsys.readouterr()

    assert exc.value.code == EXIT_OK
    assert captured.err == ""
    assert "usage" in captured.out.lower()
    assert not out_path.exists()  # no file created
    assert not missing_input.exists()  # input never created/opened


# --- no-mutation guarantee (Req 15.1, 15.2) ---


def test_input_file_unchanged_after_run(tmp_path, capsys):
    src = _write_json(tmp_path / "items.json", _RECORDS)
    before_bytes = src.read_bytes()
    before_mtime = src.stat().st_mtime_ns

    main([str(src)])
    capsys.readouterr()

    assert src.read_bytes() == before_bytes
    assert src.stat().st_mtime_ns == before_mtime


def test_input_file_unchanged_after_output_run(tmp_path, capsys):
    src = _write_json(tmp_path / "items.json", _RECORDS)
    before_bytes = src.read_bytes()
    out_path = tmp_path / "report.json"

    main([str(src), "--output", str(out_path)])
    capsys.readouterr()

    assert src.read_bytes() == before_bytes


# --- parser surface (Req 20.4-20.9) ---


def test_parser_exposes_all_options():
    parser = build_parser()
    options = {action.dest for action in parser._actions}
    assert {"input", "output", "no_ai", "sample", "help"} <= options


def test_help_text_names_required_fields_and_formats(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    for field in (
        "item_id",
        "item_description",
        "manufacturer",
        "category",
        "unit_of_measure",
        "source_system",
        "manufacturer_part_number",
    ):
        assert field in out
    assert ".json" in out and ".csv" in out
    # exit codes documented
    assert "exit codes" in out.lower()
