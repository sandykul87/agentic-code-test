"""Command-line interface: argparse, modes, and exit codes.

Stub for task 1. Full wiring (Report / Sample / Help modes, exit codes,
no-mutation guarantee) is implemented in a later task.
"""

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Minimal for now so that ``python -m dq_assistant --help`` works.
    """
    parser = argparse.ArgumentParser(
        prog="dq_assistant",
        description=(
            "Data Quality Assistant: suggest human-review candidates for "
            "item master records. Never changes the input data."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code (0 success, 2 usage/input, other).

    Stub: parses args and returns 0. Real dispatch arrives in a later task.
    """
    parser = build_parser()
    parser.parse_args(argv)
    return 0
