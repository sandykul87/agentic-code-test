# Implementation Plan

Each task is a self-contained, committable slice: it leaves the repo building and the test suite green, and corresponds to one logical commit. Tasks are ordered by dependency. Numbers in parentheses trace to requirements.md.

All work happens in the repo `/Users/sandeshkulkarni/git/agentic-code-test` on a new `develop` branch. Commit after each task; do not push until the user approves.

- [x] 1. Set up project, branch, environment, and dev dependencies
  - Create and check out a `develop` branch off `main`.
  - Add `requirements.txt` with dev-only deps: `pytest` and `hypothesis` (pinned versions). Add a one-line comment stating the runtime has no dependencies.
  - Create a local virtual environment (`python -m venv .venv`) and install from `requirements.txt`.
  - Add `.gitignore` (`.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`).
  - Create the package skeleton: `dq_assistant/__init__.py`, `dq_assistant/__main__.py` (calls `cli.main`), empty module files, `tests/`, `docs/`, `examples/`, and an empty `dq_assistant/samples/` dir.
  - Add a minimal `pyproject.toml` (package name, pytest config) and confirm `python -m pytest` runs with zero tests collected and `python -m dq_assistant --help`-style import works.
  - _Requirements: 1.9, 19.10, 19.11_

- [x] 2. Field reader, missing-value rules, and normalizers (`fields.py`)
  - Implement `read()` returning (classification, trimmed value) for present / Missing_Value / Invalid_Type_Value, the Missing_Value definition (absent, null, blank, whitespace, `null`/`none`/`n/a`), `is_unbranded()`, `normalize_text()`, `normalize_mpn()`.
  - Unit tests for every classification branch, UNBRANDED casing/padding, and non-mutation of the record.
  - _Requirements: 4.1–4.8_

- [x] 3. Constants, candidate builder, and finding_id (`models.py`)
  - Add the Issue_Type/Severity/Source sets, UoM_Allow_List, Known_Category_List.
  - Implement `finding_id()` (SHA-256 of `issue_type|row_index|item_id|field`, first 16 hex) and `make_candidate()` (sets status, allowed_actions, rounds confidence, truncates observed values to 50 chars, enforces the fixed field set).
  - Tests: candidate schema (12.1–12.11), finding_id stability and uniqueness (13.1, 13.6).
  - _Requirements: 12.1–12.11, 13.1, 13.6_

- [x] 4. Safe loader with error precedence (`loader.py`)
  - Implement `load()`: extension check, 5 MiB cap before read, strict UTF-8, JSON list parsing, CSV parsing with BOM removal + header trim + lowercase, ragged-row handling, empty/zero-record detection, and the Req 3.11 precedence producing one clean stderr line and `InputError(exit_code=2)`.
  - Tests for each error in Req 3 (exit 2, one-line stderr, no traceback/values), mixed-case headers, duplicate-header collision, ragged rows.
  - _Requirements: 2.1–2.9, 3.1–3.12_

- [x] 5. Deterministic rules (`rules.py`)
  - Implement `run_rules()`: invalid_record, missing_required_field (incl. manufacturer required, UNBRANDED exempt, item_id high severity), invalid_field_type (with type suppression), missing_part_number (UNBRANDED exempt), unsupported_unit_of_measure (allow-list, 50-char truncation).
  - Tests per Issue_Type with severity/confidence/source, plus UNBRANDED and missing-manufacturer cases.
  - _Requirements: 5.1–5.10, 6.1–6.7, 7.1–7.6_

- [x] 6. Heuristics: weak description and duplicate family (`heuristics.py`)
  - Implement weak_description (short vs abbreviation-heavy, one per record) and the duplicate family: duplicate_item_id, conflicting_source_values, potential_duplicate (normalized MPN, UNBRANDED excluded from part-number grouping), with related_item_ids/related_row_indexes.
  - Tests per Issue_Type, MPN format variants, three-record groups, UNBRANDED exclusion.
  - _Requirements: 8.1–8.6, 9.1–9.13_

- [x] 7. AI suggester stub and untrusted-output validator (`ai_suggester.py`, `validator.py`)
  - Implement the `AISuggester` Protocol, `StubAISuggester` (keyword map, whole-word match, minimal view only), and `Suggestion_Validator` with all acceptance rules (type, confidence range, known category, length, review wording, forbidden terms), dropping+counting rejects and catching suggester exceptions.
  - Tests: category_mismatch_candidate happy path, one test per validator rule, the invalid shapes in Req 19.7, suggester-raises case.
  - _Requirements: 10.1–10.8, 11.1–11.11_

- [x] 8. Report assembly and deterministic output (`report.py`)
  - Implement summary (records_read, counts by issue_type/severity/source with zero-filled keys, ai flags, notice), candidate ordering (row_index, issue_type, field with null first), deterministic JSON serialization, and the review-language notice.
  - Tests: summary counts sum correctly, ordering, byte-identical output on repeat, no forbidden terms.
  - _Requirements: 13.2–13.5, 14.1–14.6, 16.1–16.8_

- [x] 9. CLI wiring: modes, options, exit codes, and no-mutation guarantee (`cli.py`)
  - Wire argparse (`--help`/`-h`, `--output`, `--no-ai`, `--sample`), dispatch Report/Sample/Help modes, exit codes 0/2/other, output-path==input guard, and read-only/no-mutation behavior end to end.
  - Integration tests: full run on `examples/`, exit codes, `--no-ai`, output file vs stdout, help precedence (19.21), overwrite guard.
  - _Requirements: 1.1–1.9, 15.1–15.5, 20.1–20.9_

- [x] 10. Bundled samples and `--sample` mode (`dq_assistant/samples/`, `cli.py`)
  - Add clean `sample.json` and `sample.csv` (all fields, an UNBRANDED record), read via `importlib.resources`; implement `--sample json|csv` writing to stdout or `--output`, Field_Guide to stderr, exclusive-create refusal, `--sample`+input rejection, bad-format rejection.
  - Tests: Req 21 criteria incl. sample fed back yields zero candidates.
  - _Requirements: 21.1–21.12_

- [ ] 11. Lower-priority: cross_system_duplicate heuristic (`heuristics.py`) — defer if time runs out
  - Implement `_cross_system_duplicates()` in isolation (low/0.6/heuristic, related lists, exclusivity with conflicting_source_values); keep the `cross_system_duplicate` count key at 0 and README next-step note if deferred.
  - Tests: match across systems, exclusivity property (19.20), deferral path.
  - _Requirements: 22.1–22.7_

- [ ] 12. Property-based tests (`tests/test_properties.py`)
  - Add hypothesis tests P1 no-mutation, P2 schema, P3 determinism, P4 Normalized_MPN, P5 exclusivity, each ≥100 examples, with a generator covering missing/invalid/UNBRANDED/mixed shapes and non-object entries.
  - _Requirements: 15.5, 19.3–19.5, 12.1–12.5, 13.2, 9.9, 22.5_

- [x] 13. Demo example inputs covering every Issue_Type (`examples/`)
  - Add `demo.json` and `demo.csv` that together trigger all 11 Issue_Types; assert in a test that the combined Reports cover each type (minus cross_system_duplicate if Req 22 deferred).
  - _Requirements: 18.8, 18.9_

- [-] 14. Documentation: README, ADRs, AI_USAGE, PROMPTS, spec copy
  - Write README (install, run, `python -m dq_assistant <input> [--output FILE] [--no-ai]`, `--sample`, sample I/O, UNBRANDED, header rule, assumptions, tradeoffs, known limitations incl. non-English + formula-injection caveat, next steps incl. Req 22 if deferred).
  - Add ADR-0001/0002/0003, `docs/AI_USAGE.md`, `docs/PROMPTS.md` (session + planned + production prompt template), and copy requirements/design/tasks into `docs/spec/`.
  - _Requirements: 17.6, 17.7, 17.8, 18.1–18.14_

- [ ] 15. Final verification and submission prep
  - Run `python -m pytest` (all green, no network), run the tool on both demo files with and without `--no-ai`, confirm byte-identical repeat output and an unchanged input file.
  - Confirm `docs/spec/` copies match the specs; ensure the working tree is clean and all task commits are present on `develop`. Report readiness; push only on user go-ahead.
  - _Requirements: 15.1, 19.10, 18.1_
