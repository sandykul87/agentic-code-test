# AI usage

This document summarizes how AI was used to build the Data Quality Assistant and
how the tool's own AI layer works. The full, entry-by-entry record of prompts
lives in the Prompt Log: [`docs/PROMPTS.md`](PROMPTS.md).

## How the AI layer works inside the tool

The tool contains an AI layer, and it is deliberately small and contained:

- **Stub + validator boundary.** Category-mismatch suggestions come from an
  offline, deterministic stub (`StubAISuggester` in
  `dq_assistant/ai_suggester.py`), and every suggestion is checked by the
  `Suggestion_Validator` in `dq_assistant/validator.py` before it can become a
  report candidate. The stub sits behind the `AISuggester` protocol so a real
  model can replace it later without touching the rest of the tool (see
  `docs/adr/ADR-0002-ai-stub-boundary.md`).
- **Data minimization.** The suggester receives only a *minimal view* of each
  record — `item_id`, `item_description`, and `category` — never the whole
  record (Requirement 10.2). Nothing else about a record is ever handed to the
  AI layer.
- **Untrusted-output validation.** AI output is treated as untrusted. The
  validator enforces the correct shape and issue type, a finite in-range
  confidence, a category from the known list, length limits, required review
  wording, and the absence of misleading terms like "fixed" or "auto-approved"
  (Requirement 11). Anything failing is dropped and counted in
  `ai_suggestions_rejected`; a suggester that raises or returns a non-list is
  caught and counted in `ai_errors`. This satisfies the privacy and
  untrusted-output intent of Requirements 17.7 and 17.8.

## Work delegated to AI

- Drafting the requirements, design, and task breakdown for the
  `data-quality-assistant` spec (`docs/spec/requirements.md`,
  `docs/spec/design.md`, `docs/spec/tasks.md`).
- Implementing the package modules from the task plan, including the safe loader
  (`dq_assistant/loader.py`), the deterministic rules (`dq_assistant/rules.py`),
  the heuristics (`dq_assistant/heuristics.py`), the AI stub and validator
  (`dq_assistant/ai_suggester.py`, `dq_assistant/validator.py`), and the report
  assembly (`dq_assistant/report.py`).
- Writing the example-based test suite under `tests/` and the demo inputs under
  `examples/`.
- Writing this documentation set: the README, the three ADRs, this file, and the
  Prompt Log.

## Work verified by hand

- The full test suite was run with `python -m pytest` and confirmed green before
  this documentation task was committed (351 tests passing at the time of
  writing).
- The sample report excerpt in the README was produced by actually running
  `python -m dq_assistant examples/demo.json` and pasted unedited, rather than
  hand-written, so it matches real output (Requirement 18.7).
- The byte-for-byte match of the `docs/spec/` copies against the source spec was
  checked with `diff` (Requirement 18.1).
- The deferred status of `cross_system_duplicate` (Requirement 22) was confirmed
  by reading `dq_assistant/heuristics.py` — `_cross_system_duplicates` returns an
  empty list — before documenting it as a next step rather than claiming it is
  implemented.

## AI output rejected or changed

- **Requirement 22 claim corrected.** An early draft of the docs risked
  describing `cross_system_duplicate` as a working check. This was rejected after
  reading `dq_assistant/heuristics.py`: the function is a stub, so the docs
  instead record the check as deferred (Requirement 22 criterion 7), with the
  summary key held at `0` and a README next-step note.
- **ADR-0003 no-mutation proof softened to match reality.** The ADR was changed
  not to claim a passing property test P1, because `tests/test_properties.py`
  does not exist yet (property tests are planned under task 12). The ADR records
  the decision and the design that enforces it, and notes P1 as planned.
- Inside the tool, the AI layer's *own* output is continuously "rejected or
  changed": the `Suggestion_Validator` drops any suggestion that fails a rule and
  increments `ai_suggestions_rejected`, which is the built-in mechanism for not
  trusting AI output blindly (`dq_assistant/validator.py`, Requirement 11).

For the complete list of prompts — those already used and those planned — see
[`docs/PROMPTS.md`](PROMPTS.md).
