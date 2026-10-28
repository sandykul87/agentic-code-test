# Prompt Log

This is the Prompt Log for the Data Quality Assistant (Requirement 18, criteria
10 to 14). It records the prompts used to build the tool, the prompts planned for
future phases, and the production LLM prompt template for the category suggester.

**No secrets and no real data.** This log contains no API keys, tokens,
passwords, or connection strings, and no real customer or supplier data. All
example records are synthetic. Any prompt that originally contained such data is
recorded here as a summary with that data removed.

For a narrative summary of how AI was used, see
[`docs/AI_USAGE.md`](AI_USAGE.md).

Each entry records: date, actor (`human`, `agent`, or `sub-agent`), purpose,
prompt text or summary, output summary, and decision (accepted / changed /
rejected, with a one-line reason).

---

## 1. Completed prompts

### 1.1 Requirements drafting

- **Date:** 2024 spec session (build session date)
- **Actor:** human → agent
- **Purpose:** Turn the interview assignment ("a tool that reviews item master
  data and never changes it") into a structured requirements document.
- **Prompt (summary):** Draft an EARS-style requirements document for a
  command-line data quality assistant: read JSON/CSV item records, run a fixed
  set of checks, emit review candidates only, never modify input, standard
  library only, AI as a validated stub. Cover input loading, error handling,
  missing-value rules, the deterministic rules, the heuristics, the AI boundary,
  determinism, security, docs, and tests.
- **Output (summary):** `requirements.md` with the glossary and Requirements 1
  to 19.
- **Decision:** Accepted as the baseline, then refined (see 1.2–1.4).

### 1.2 Per-requirement refinement

- **Date:** spec session
- **Actor:** agent → sub-agent (requirement-detailer)
- **Purpose:** Sharpen individual requirements into testable acceptance criteria
  with explicit edge cases.
- **Prompt (summary):** For each requirement, enumerate acceptance criteria in
  EARS form, list the edge cases it must cover, and make severity/confidence/
  source explicit per issue type.
- **Output (summary):** Expanded acceptance criteria and "edge cases covered"
  notes throughout `requirements.md`, plus the Edge Case Index.
- **Decision:** Accepted; wording on the Unbranded sentinel and missing-value
  placeholders was tightened.

### 1.3 Added options and consistency fixes (Requirements 20–22)

- **Date:** spec session, second review round
- **Actor:** human → agent
- **Purpose:** Add `--help` (Requirement 20), offline `--sample` (Requirement
  21), and the lower-priority `cross_system_duplicate` heuristic (Requirement
  22) without disturbing existing cross-references.
- **Prompt (summary):** Append Requirements 20–22 after 19 so existing numbers
  stay stable; make Requirement 22 explicitly deferrable with a documented
  fallback (summary key stays at 0, README next-step note).
- **Output (summary):** Requirements 20, 21, 22 and their test criteria in
  Requirement 19.
- **Decision:** Accepted; Requirement 22 marked lower priority and deferrable.

### 1.4 Design document

- **Date:** spec session
- **Actor:** human → agent
- **Purpose:** Produce the design: architecture, trust boundaries, module
  responsibilities, constants, error precedence, security design, the five
  conditions for a real LLM, the testing strategy, tradeoffs, and ADR stubs.
- **Prompt (summary):** Write a design document for the requirements above:
  data-flow diagram with the two trust boundaries, package layout, per-module
  signatures, the constant tables (UoM allow-list, known categories, keyword
  map, severity/confidence table), the error-precedence table, and sections 9–13
  (real-LLM conditions, prompt template, testing, tradeoffs, ADRs).
- **Output (summary):** `design.md` sections 1 to 13.
- **Decision:** Accepted; it is the implementation contract.

### 1.5 Task breakdown

- **Date:** spec session
- **Actor:** human → agent
- **Purpose:** Break the design into ordered, committable tasks.
- **Prompt (summary):** Produce a dependency-ordered task plan where each task
  leaves the suite green and maps to one commit; trace each task to requirements.
- **Output (summary):** `tasks.md` tasks 1 to 15.
- **Decision:** Accepted; task 11 (Requirement 22) and task 12 (property tests)
  marked as deferrable / later.

### 1.6 Implementation (tasks 1–10, 13)

- **Date:** build session
- **Actor:** human → agent (per task)
- **Purpose:** Implement each task in order.
- **Prompt (summary):** For each task, implement the named modules per the design
  and write example-based tests; keep the runtime standard-library only; commit
  one logical change per task.
- **Output (summary):** The `dq_assistant/` package (loader, fields, models,
  rules, heuristics, ai_suggester, validator, report, cli, samples), the `tests/`
  suite, and the `examples/` demo inputs. `_cross_system_duplicates` left as a
  stub returning `[]` (task 11 deferred).
- **Decision:** Accepted; suite green (351 tests at the time of this doc task).

### 1.7 Documentation (task 14)

- **Date:** build session (this task)
- **Actor:** human → agent
- **Purpose:** Write the README, the three ADRs, `docs/AI_USAGE.md`, this Prompt
  Log, and copy the specs into `docs/spec/`.
- **Prompt (summary):** Write documentation matching the actual implementation;
  document `cross_system_duplicate` as deferred; produce the README sample output
  by running the tool on a demo file; copy the specs byte-for-byte.
- **Output (summary):** `README.md`, `docs/adr/ADR-0001..0003`,
  `docs/AI_USAGE.md`, `docs/PROMPTS.md`, `docs/spec/{requirements,design,tasks}.md`.
- **Decision:** Accepted; Requirement 22 documented as deferred, ADR-0003 notes
  property test P1 as planned rather than claiming a passing test.

---

## 2. Planned prompts

These are future phases. Date and decision are `planned` until the prompt is
used, at which point the entry moves to section 1 with the date, output summary,
and decision filled in.

### 2.1 Design (planned)

- **Date:** planned
- **Actor:** agent
- **Purpose:** Design any post-submission feature (for example wiring in
  Requirement 22 or a decision-recording store).
- **Prompt (summary):** Given a new feature request, extend the existing design
  with new modules and data flow while preserving the no-mutation and
  standard-library-only constraints.
- **Expected output:** A design delta that names the modules to add or change.
- **Decision:** planned

### 2.2 Tasks (planned)

- **Date:** planned
- **Actor:** agent
- **Purpose:** Break a new design delta into committable tasks.
- **Prompt (summary):** Produce a dependency-ordered task list for the design
  delta; each task leaves the suite green.
- **Expected output:** An ordered task list traced to requirements.
- **Decision:** planned

### 2.3 Implementation (planned)

- **Date:** planned
- **Actor:** agent
- **Purpose:** Implement the deferred `cross_system_duplicate` heuristic (task
  11) and the property-based tests (task 12).
- **Prompt (summary):** Implement `_cross_system_duplicates` per Requirement 22
  (low / 0.6 / heuristic, related lists, exclusivity with
  `conflicting_source_values`); add hypothesis property tests P1–P5.
- **Expected output:** Updated `dq_assistant/heuristics.py`, new
  `tests/test_properties.py`, summary `cross_system_duplicate` count that can
  exceed 0, and an updated README next-steps section.
- **Decision:** planned

### 2.4 Code review (planned)

- **Date:** planned
- **Actor:** sub-agent
- **Purpose:** Review a change for clarity, correctness, and scope.
- **Prompt (summary):** Review this diff against the design and requirements;
  flag behavior changes, missed edge cases, and anything that weakens the
  no-mutation or standard-library-only guarantees.
- **Expected output:** A review with a verdict and specific findings.
- **Decision:** planned

### 2.5 Security review (planned)

- **Date:** planned
- **Actor:** sub-agent
- **Purpose:** Confirm the attack surface stays minimal.
- **Prompt (summary):** Audit the code for network access, `eval`/`exec`/
  `pickle`/`subprocess`, error-message leakage of field values, the 5 MiB cap,
  strict UTF-8, and untrusted-AI-output validation; confirm Requirement 17.
- **Expected output:** A security assessment with any findings and fixes.
- **Decision:** planned

---

## 3. Production LLM prompt template

This is the future prompt for a real-LLM version of the category-mismatch
suggester. It is copied from the design document (section 10). Every response is
treated as **untrusted** and is validated by the `Suggestion_Validator`
(Requirement 11) before it can become a Review_Candidate; anything failing is
dropped and counted.

```
System: You classify an inventory item's category from its description. You never modify data.
Return ONLY JSON matching this schema; no prose.
Input (only these fields): {"item_id": str|null, "item_description": str, "category": str}
Output schema:
  {"issue_type": "category_mismatch_candidate",
   "confidence": number 0..1,
   "suggested_category": one of [Mechanical, Electrical, Plumbing, Electronics, Safety],
   "explanation": string (<=500 chars, must contain "candidate"/"potential"/"needs review"),
   "suggested_action": string (<=300 chars, must contain review/verify/confirm/check)}
Return an empty list if the recorded category already fits.
```

The allowed answers are exactly the Known_Category_List: `Mechanical`,
`Electrical`, `Plumbing`, `Electronics`, `Safety`.

### Example input message (minimal record view only)

```json
{"item_id": "1001", "item_description": "SKF deep groove ball bearing 6205 ZZ", "category": "Electrical"}
```

### Example expected output (passes the Suggestion_Validator rules)

```json
[
  {
    "issue_type": "category_mismatch_candidate",
    "confidence": 0.7,
    "suggested_category": "Mechanical",
    "explanation": "Candidate issue: the description mentions a bearing, which suggests category Mechanical, but the record lists Electrical.",
    "suggested_action": "Review the category assignment with the source owner before approval."
  }
]
```

This example passes validation: `issue_type` is exactly
`category_mismatch_candidate`; `confidence` is a finite number in `0.0`–`1.0`;
`suggested_category` is in the Known_Category_List and differs from the recorded
category; the `explanation` is within 500 characters and contains "Candidate";
the `suggested_action` is within 300 characters and contains "Review"; neither
field contains a forbidden term such as "fixed" or "auto-approved".
