"""Command-line interface: argparse, modes, and exit codes (Requirements 1, 15, 20).

The CLI parses arguments, dispatches to one of three modes, and owns the
process exit code. It never modifies the Input_File: the Loader opens it
read-only and the in-memory Raw_Records are read through
:func:`dq_assistant.fields.read`, which never writes back (Requirement 15).

Modes:
  * Report_Mode  -- an Input_File positional argument (Requirements 1 to 16).
  * Sample_Mode  -- the ``--sample json|csv`` option (Requirement 21).
  * Help         -- ``-h`` / ``--help``, handled by argparse, wins over every
    other argument (Requirement 20).

Exit codes:
  * ``0`` a Report or Bundled_Sample was written.
  * ``2`` a usage error or an input error (bad arguments, unreadable or
    malformed Input_File).
  * ``1`` output could not be written, the output path would overwrite the
    input, or an unexpected internal error occurred.

Standard library only (Requirement 1.9).
"""

import argparse
import os
import sys

from dq_assistant.ai_suggester import StubAISuggester
from dq_assistant.heuristics import run_heuristics
from dq_assistant.loader import InputError, load
from dq_assistant.report import build_report, to_json
from dq_assistant.rules import run_rules
from dq_assistant.validator import run_ai_suggestions

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_OUTPUT = 1

# Error lines written to standard error (one line, no values, no traceback).
MSG_OVERWRITE_INPUT = "Output path would overwrite the input"
MSG_CANNOT_WRITE = "Cannot write output: {path}"
MSG_UNEXPECTED = "Unexpected error while processing input"
MSG_SAMPLE_PENDING = "Sample mode is not available yet"

_DESCRIPTION = (
    "Data Quality Assistant: read a file of item master records (.json or "
    ".csv) and write a JSON report of candidate issues for a data steward to "
    "review. It only produces review candidates and never modifies the input "
    "data."
)

# Epilog carries the content of Requirement 20 criteria 5 to 9 that does not
# fit naturally in per-argument help strings.
_EPILOG = (
    "input formats:\n"
    "  .json  a list of record objects\n"
    "  .csv   a header row followed by one row per record\n"
    "\n"
    "fields:\n"
    "  required: item_id, item_description, manufacturer, category,\n"
    "            unit_of_measure, source_system\n"
    "  optional: manufacturer_part_number\n"
    "  Items without a manufacturer use the value UNBRANDED in the\n"
    "  manufacturer field.\n"
    "\n"
    "usage notes:\n"
    "  The input file argument and --sample cannot be used in the same run.\n"
    "  Maximum input size is 5 MiB.\n"
    "  The tool only produces review candidates for a data steward and never\n"
    "  modifies the input data.\n"
    "\n"
    "exit codes:\n"
    "  0  a report or sample file was written\n"
    "  2  usage or input error\n"
    "  1  output could not be written, or an unexpected internal error\n"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    argparse supplies ``-h``/``--help`` automatically; its default handling
    prints the usage text to standard output and exits 0 before any other
    argument is validated, which satisfies Requirement 20 criteria 1 to 3 and
    the help-precedence case (Requirement 19.21).
    """
    parser = argparse.ArgumentParser(
        prog="dq_assistant",
        description=_DESCRIPTION,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        nargs="?",
        metavar="INPUT",
        help="path to the input file to check (.json or .csv)",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="write the report (or sample) to PATH instead of standard output",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="skip the AI category suggester; keep only rule and heuristic findings",
    )
    parser.add_argument(
        "--sample",
        choices=("json", "csv"),
        metavar="{json,csv}",
        help="write a bundled clean sample file of this format instead of a report",
    )
    return parser


def _same_file(a: str, b: str) -> bool:
    """True when two paths resolve (symlinks and relative parts) to one file."""
    return os.path.realpath(a) == os.path.realpath(b)


def _write_output(path: str, text: str) -> None:
    """Write ``text`` to ``path`` as UTF-8, replacing any existing file.

    Raises :class:`OSError` on any write failure; the caller turns that into
    the output error exit code.
    """
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _run_report(args: argparse.Namespace) -> int:
    """Report_Mode: load, run every check, assemble and write the Report.

    Returns the process exit code. The Input_File is opened read-only by the
    Loader and the in-memory records are never mutated (Requirement 15).
    """
    output = args.output

    # Guard before loading so an output-equals-input run touches no file and
    # produces nothing (Requirements 1.4, 15.4).
    if output is not None and os.path.exists(output) and _same_file(output, args.input):
        print(MSG_OVERWRITE_INPUT, file=sys.stderr)
        return EXIT_OUTPUT

    records = load(args.input)  # raises InputError (exit 2); caught in main

    candidates = run_rules(records)
    candidates += run_heuristics(records)

    ai_enabled = not args.no_ai
    rejected = errors = 0
    if ai_enabled:
        result = run_ai_suggestions(records, StubAISuggester())
        candidates += result.candidates
        rejected, errors = result.rejected, result.errors

    report = build_report(records, candidates, ai_enabled, rejected, errors)
    text = to_json(report)

    if output is None:
        sys.stdout.write(text)
        return EXIT_OK

    # Re-check overwrite now that the input path is known good; realpath only
    # resolves an existing output path, so also compare after a would-be write.
    if _same_file(output, args.input):
        print(MSG_OVERWRITE_INPUT, file=sys.stderr)
        return EXIT_OUTPUT
    try:
        _write_output(output, text)
    except OSError:
        print(MSG_CANNOT_WRITE.format(path=output), file=sys.stderr)
        return EXIT_OUTPUT
    return EXIT_OK


def _run_sample(args: argparse.Namespace) -> int:
    """Sample_Mode entry point.

    The argparse surface for ``--sample`` is wired here (the option is
    recognised and its mutual exclusivity with the Input_File argument is
    enforced in :func:`main`). The actual Bundled_Sample emission is
    implemented in a later task; until then this reports a clean error and the
    non-zero output exit code rather than pretending to succeed.
    """
    print(MSG_SAMPLE_PENDING, file=sys.stderr)
    return EXIT_OUTPUT


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns the process exit code (0 success, 2 usage/input, 1 other).

    argparse handles ``-h``/``--help`` (prints usage, exits 0) and unknown
    options (prints usage to stderr, exits 2) before this function's own
    dispatch runs.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # Report_Mode and Sample_Mode are mutually exclusive, and at least one of
    # them must be selected (Requirements 1.6, 21.6).
    if args.sample is not None and args.input is not None:
        parser.error("argument INPUT: not allowed with argument --sample")
    if args.sample is None and args.input is None:
        parser.error("an input file or --sample is required")

    try:
        if args.sample is not None:
            return _run_sample(args)
        return _run_report(args)
    except InputError as exc:
        print(exc.message, file=sys.stderr)
        return exc.exit_code
    except Exception:  # last-resort guard: no traceback, no field values
        print(MSG_UNEXPECTED, file=sys.stderr)
        return EXIT_OUTPUT
