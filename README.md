# Data Quality Assistant (`dq_assistant`)

A small command-line tool that reads a file of item master records (JSON or CSV),
runs a fixed set of data quality checks, and writes a JSON **report of review
candidates** for a human data steward.

The tool never changes your data. Every finding is a *candidate issue* that
*needs review*. Each one records what was detected, why, how severe it looks,
how confident the tool is, what a steward could do next, and which kind of logic
produced it: a deterministic rule, a heuristic, or an AI suggestion. The AI layer
is an offline stub in this version; its output is validated as untrusted data, so
a real model could be added later without trusting it blindly (see
[Next steps](#next-steps) and `docs/adr/ADR-0002-ai-stub-boundary.md`).

## Table of contents

- [Requirements](#requirements)
- [Install dev dependencies](#install-dev-dependencies)
- [Running the tool](#running-the-tool)
- [Getting a sample file with `--sample`](#getting-a-sample-file-with---sample)
- [Running the tests](#running-the-tests)
- [Sample input and output](#sample-input-and-output)
- [The `UNBRANDED` convention](#the-unbranded-convention)
- [CSV header handling](#csv-header-handling)
- [Assumptions](#assumptions)
- [Tradeoffs](#tradeoffs)
- [Known limitations](#known-limitations)
- [Next steps](#next-steps)

## Requirements

- **Python 3** (3.10 or newer; the code uses `X | Y` type syntax).
- **Runtime dependencies: none.** The tool imports only the Python 3 standard
  library at runtime, so it runs in a clean Python environment with no packages
  installed.
- `pytest` and `hypothesis` are **development-only** dependencies, used for the
  test suite. They are listed in `requirements.txt` and are not needed to run the
  tool.

## Install dev dependencies

You only need these to run the tests. To run the tool itself, plain Python 3 is
enough.

```sh
python3 -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running the tool

Report mode reads an input file and writes a JSON report. By default the report
goes to standard output and all diagnostics go to standard error.

```sh
# Report to stdout
python -m dq_assistant <input>

# Report to a file (replaces an existing file at that path)
python -m dq_assistant <input> --output report.json

# Report without the AI layer (only deterministic_rule and heuristic candidates)
python -m dq_assistant <input> --no-ai
```

The full report-mode invocation is:

```sh
python -m dq_assistant <input> [--output FILE] [--no-ai]
```

- `<input>` — path to a `.json` or `.csv` file (extension chosen case-insensitively).
- `--output FILE` — write the report to `FILE` instead of standard output. The
  tool refuses to run if `FILE` resolves to the same file as the input.
- `--no-ai` — skip the AI suggester entirely.

Exit codes: `0` when a report (or sample) was written, `2` for usage and input
errors, and a non-zero code other than `2` (for example `1`) when output cannot
be written or an unexpected internal error occurs.

See every option and the required-field reference with:

```sh
python -m dq_assistant --help
```

## Getting a sample file with `--sample`

`--sample` writes a clean, bundled template you can copy and fill in. It is fully
offline; the samples live inside the package. Standard output is the file bytes
only (so you can redirect it), and a short field guide is written to standard
error.

```sh
# Print a JSON template to stdout, field guide to stderr
python -m dq_assistant --sample json

# Write a CSV template to a new file (refuses to overwrite an existing path)
python -m dq_assistant --sample csv --output template.csv
```

The full sample-mode invocation is:

```sh
python -m dq_assistant --sample {json,csv} [--output FILE]
```

`--sample` and an input-file argument cannot be used in the same run. Feeding a
bundled sample back into report mode yields a report with an empty `candidates`
list, so the template is a known-clean example.

## Running the tests

```sh
python -m pytest
```

The suite runs with no network access and uses only the development
dependencies. Runtime behavior still depends on the standard library alone.

## Sample input and output

The report below is an unedited excerpt produced by running the tool on the
repository demo file `examples/demo.json`:

```sh
python -m dq_assistant examples/demo.json
```

`examples/demo.json` and `examples/demo.csv` are demo inputs that deliberately
contain data quality problems; together they trigger every active issue type.
They are separate from the clean templates produced by `--sample`.

Report excerpt (the summary and the first two candidates):

```json
{
  "summary": {
    "records_read": 11,
    "candidates_total": 14,
    "by_issue_type": {
      "category_mismatch_candidate": 2,
      "conflicting_source_values": 2,
      "cross_system_duplicate": 0,
      "duplicate_item_id": 2,
      "invalid_field_type": 1,
      "invalid_record": 1,
      "missing_part_number": 1,
      "missing_required_field": 1,
      "potential_duplicate": 2,
      "unsupported_unit_of_measure": 1,
      "weak_description": 1
    },
    "by_severity": {
      "high": 3,
      "low": 3,
      "medium": 8
    },
    "by_source": {
      "ai_suggestion": 2,
      "deterministic_rule": 5,
      "heuristic": 7
    },
    "ai_enabled": true,
    "ai_suggestions_rejected": 0,
    "ai_errors": 0,
    "notice": "All findings are candidate issues that need human review by a data steward. No input data was modified."
  },
  "candidates": [
    {
      "finding_id": "ad842f4ee07fceba",
      "item_id": "D-1001",
      "row_index": 0,
      "issue_type": "category_mismatch_candidate",
      "field": "category",
      "severity": "low",
      "confidence": 0.7,
      "explanation": "Candidate issue: description keyword 'bearing' suggests category Mechanical, recorded as Electrical.",
      "suggested_action": "Review the category assignment with the source owner before approval.",
      "source": "ai_suggestion",
      "status": "needs_review",
      "allowed_actions": [
        "approve",
        "reject",
        "investigate"
      ],
      "suggested_category": "Mechanical"
    },
    {
      "finding_id": "ecbdba54fab6131d",
      "item_id": "D-1001",
      "row_index": 0,
      "issue_type": "missing_part_number",
      "field": "manufacturer_part_number",
      "severity": "medium",
      "confidence": 0.95,
      "explanation": "Candidate issue: manufacturer is present but manufacturer part number is missing.",
      "suggested_action": "Confirm the manufacturer part number with the source owner.",
      "source": "deterministic_rule",
      "status": "needs_review",
      "allowed_actions": [
        "approve",
        "reject",
        "investigate"
      ]
    }
  ]
}
```

Note that `cross_system_duplicate` is present in the summary with a count of `0`.
That check is deferred in this version (see [Next steps](#next-steps)); the key
stays in the map so the report shape is stable.

## The `UNBRANDED` convention

Consumables, services, and generic stock often have no manufacturer. For these
items, set the `manufacturer` field to the literal value `UNBRANDED` (the
Unbranded sentinel). It is matched case-insensitively after trimming, so
`UNBRANDED`, `unbranded`, and ` Unbranded ` all match; `Unbranded Generic` does
not.

`UNBRANDED` is a **present, valid** manufacturer value. For a record whose
manufacturer is `UNBRANDED`:

- it does **not** produce a `missing_required_field` candidate for `manufacturer`;
- it does **not** trigger the missing-part-number rule, whatever the part number
  value is;
- it is **left out of part-number duplicate grouping**, because unbranded items
  do not share a manufacturer identity.

Use it only in the `manufacturer` field; it has no special meaning anywhere else.

## CSV header handling

For CSV input the header row is normalized before fields are matched:

1. a UTF-8 byte order mark is removed (common in Excel exports),
2. surrounding whitespace is trimmed,
3. the name is lower-cased.

So `Item_ID`, ` ITEM_ID `, and `item_id` all match the field `item_id`. Only the
header names are normalized; cell values are kept exactly as read.

**JSON keys are matched case-sensitively.** JSON files usually come from programs
with a fixed schema, so a JSON key `Item_ID` is treated as an unknown field, not
as `item_id`. This difference between CSV and JSON is intentional.

**Duplicate CSV headers (known limitation).** If two header names are equal after
normalization (for example `Item_ID` and `item_id`), the value from the last such
column wins and no candidate is produced for the collision. This follows Python's
`csv.DictReader` behavior.

## Assumptions

- **`manufacturer` is a required field.** A missing manufacturer produces a
  `missing_required_field` candidate. Items that genuinely have no manufacturer
  use the `UNBRANDED` sentinel described above.
- The six required fields are `item_id`, `item_description`, `manufacturer`,
  `category`, `unit_of_measure`, and `source_system`. `manufacturer_part_number`
  is optional on its own, but a missing part number is flagged when a real
  manufacturer is recorded.
- Empty-looking values are all treated as missing: absent, JSON `null`, empty or
  whitespace-only strings, and the placeholders `null`, `none`, and `n/a`
  (case-insensitive, whole-value match).
- Severity and confidence are reasonable fixed defaults per check, not calibrated
  scores.
- Each finding maps to one record (identified by `item_id` when present, else by
  `row_index`); duplicate findings point at related records rather than merging
  them.

## Tradeoffs

- **Keyword-map AI stub vs real NLP.** The AI suggester is a deterministic,
  offline keyword-to-category map. It is intentionally naive: the point of this
  version is the untrusted-output boundary and validator, not the stub's
  accuracy. A real model can be swapped in behind the same interface.
- **One candidate per record vs per group** for duplicates — chosen per-record so
  each finding maps to a single item.
- **JSON keys case-sensitive, CSV headers normalized** — the simplest consistent
  rule, documented above.
- **Standard library only** — no framework and no runtime dependencies, which
  removes supply-chain risk and keeps every module readable in a few minutes, at
  the cost of writing a little more code by hand.

## Known limitations

- **Non-English / whitespace-free descriptions.** The weak-description heuristic
  counts words and characters using whitespace splitting, with no translation or
  language detection. Non-English item descriptions are processed with the same
  whitespace-based word and character counts as English ones. Languages that do
  not put spaces between words (for example Chinese or Japanese) may be flagged
  as weak descriptions. This is a known limitation.
- **JSON vs CSV key matching.** JSON keys are matched case-sensitively, while CSV
  header names are matched case-insensitively. CSV headers that collide after
  lower-casing keep the last column (see [CSV header handling](#csv-header-handling)).
- **Spreadsheet formula injection.** Values in the report are **not** sanitized
  for spreadsheet formula injection. The output is JSON in this version, so this
  is not an issue today, but any future CSV or Excel export must escape values
  that begin with `=`, `+`, `-`, or `@` before writing them to a spreadsheet.
- **Severity and confidence** are fixed defaults, not statistically calibrated.

## Next steps

- **Cross-system duplicate detection (deferred).** The `cross_system_duplicate`
  heuristic (Requirement 22) is **not implemented** in this version. It is the
  lowest-priority check and is deferred under its own criterion 7: the tool
  produces zero such candidates, and the `cross_system_duplicate` key stays in
  the summary count map at `0`. Wiring it in is a next step.
- **Decision recording and audit trail** — capture each steward's approve/reject/
  investigate decision per finding.
- **Normalized description suggestions** — propose fuller descriptions, not just
  flag weak ones.
- **Real LLM integration** — replace the stub category suggester with a real
  model. It must satisfy the five conditions in `docs/adr/ADR-0002-ai-stub-boundary.md`
  and design section 9: data minimization, schema validation through the existing
  `Suggestion_Validator`, a request timeout, no secrets in code, and an explicit
  opt-in before any data leaves the machine.
- **An HTTP API** — expose the same checks over a service interface.
