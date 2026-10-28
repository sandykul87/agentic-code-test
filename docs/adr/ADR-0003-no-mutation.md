# ADR-0003: Never modify input data (read-only, no write-back)

## Status

Accepted.

## Context

"Never auto-modify data" is the core promise of this tool. It reads production
item master exports, which may contain supplier names and internal identifiers.
A data owner needs to trust that running the tool cannot change, corrupt, or lose
a single byte of the source file, and that no finding quietly rewrites a value.

Stating this in prose is not enough. A normalizer (for example `Normalized_MPN`
or `Normalized_Text`, used to compare records) could accidentally leak a
rewritten value into the output, or a careless edit could mutate an in-memory
record that a later check then reads. The promise has to be guaranteed by the
design, not just asserted.

## Decision

The tool is read-only end to end:

- The input file is opened for reading only. There is no apply, merge, correct,
  or write-back step anywhere in the codebase.
- The `Field_Value_Reader` (`dq_assistant/fields.py`) returns a *trimmed copy* of
  each value and never writes back to the record. All checks read field values
  only through it.
- Normalized forms (`normalize_mpn`, `normalize_text`) are used **only for
  comparison**. No normalized or merged value is ever placed in the report; any
  record value in the report is copied verbatim (trimmed only) from the input.
- Duplicate-family findings point at related records via `related_item_ids` and
  `related_row_indexes`; they never combine or rewrite records.
- Every finding carries `status: needs_review` and
  `allowed_actions: [approve, reject, investigate]`. There is no "apply" action.
- If `--output` resolves to the input file, the run is refused before anything is
  written, so the tool cannot overwrite its own source.

This decision is intended to be proven by property test **P1** (no mutation):
arbitrary generated record lists compare equal to a deep copy taken before any
check ran, across at least 100 generated cases (design section 11, Requirement
15.5).

## Consequences

- A data owner can run the tool on production exports without risk to the source
  file or the in-memory records.
- Keeping normalized values strictly internal means the report always shows the
  steward the original value, which is what they need to act on.
- **Tradeoff:** the tool can only *suggest*. It cannot apply even an obviously
  correct fix, so every finding still needs a human step. That is the intended
  design, but it does mean the tool does not reduce manual work to zero.
- **Status note:** property test P1 is planned under task 12 and is **not yet
  present** in the test suite (`tests/test_properties.py` does not exist at the
  time of writing). This ADR records the no-mutation *decision* and the design
  that enforces it; the property-based proof will land with task 12. Example
  tests in the existing suite already assert that specific records are unchanged
  after checks run.
