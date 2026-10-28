"""Coverage test for the repository demo inputs (Requirements 18.8, 18.9).

The two demo files under ``examples/`` exist so a reviewer can run the tool
once and see every kind of finding. This test is the executable guarantee of
Requirement 18.8: it runs the full Report pipeline on ``demo.json`` and
``demo.csv`` and asserts that, between them, the Reports cover every
Issue_Type the tool can currently produce.

``cross_system_duplicate`` (Requirement 22) is deferred: its check is a stub
that yields nothing, so it is excluded from the required coverage set and its
summary count must stay 0 (tasks.md task 11).
"""

import json
from pathlib import Path

from dq_assistant.ai_suggester import StubAISuggester
from dq_assistant.heuristics import run_heuristics
from dq_assistant.loader import load
from dq_assistant.models import ISSUE_TYPES
from dq_assistant.report import build_report
from dq_assistant.rules import run_rules
from dq_assistant.validator import run_ai_suggestions

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
DEMO_FILES = ("demo.json", "demo.csv")

# Requirement 22 is deferred; its stub produces no candidates (Req 22.7), so it
# is not part of the coverage demo and its count stays 0.
DEFERRED = {"cross_system_duplicate"}
REQUIRED_TYPES = ISSUE_TYPES - DEFERRED


def _report_for(path: Path) -> dict:
    """Run the full Report_Mode pipeline (rules + heuristics + AI) on one file."""
    records = load(str(path))
    candidates = run_rules(records)
    candidates += run_heuristics(records)
    ai = run_ai_suggestions(records, StubAISuggester())
    candidates += ai.candidates
    return build_report(records, candidates, True, ai.rejected, ai.errors)


def _types_in(report: dict) -> set[str]:
    return {name for name, count in report["summary"]["by_issue_type"].items() if count > 0}


def test_demo_files_exist():
    for name in DEMO_FILES:
        assert (EXAMPLES / name).is_file(), f"missing demo file: {name}"


def test_combined_demos_cover_every_active_issue_type():
    covered: set[str] = set()
    for name in DEMO_FILES:
        covered |= _types_in(_report_for(EXAMPLES / name))

    missing = REQUIRED_TYPES - covered
    assert not missing, f"demo inputs do not trigger: {sorted(missing)}"


def test_deferred_cross_system_duplicate_not_triggered():
    for name in DEMO_FILES:
        report = _report_for(EXAMPLES / name)
        assert report["summary"]["by_issue_type"]["cross_system_duplicate"] == 0


def test_demo_json_is_a_list_of_records():
    data = json.loads((EXAMPLES / "demo.json").read_text(encoding="utf-8"))
    assert isinstance(data, list) and data


def test_each_demo_file_triggers_several_types():
    # Each file should be useful on its own, not just in combination.
    for name in DEMO_FILES:
        assert len(_types_in(_report_for(EXAMPLES / name))) >= 5
