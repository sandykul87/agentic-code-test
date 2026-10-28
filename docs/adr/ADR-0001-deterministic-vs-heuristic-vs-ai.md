# ADR-0001: Split checks into deterministic rules, heuristics, and AI suggestions

## Status

Accepted.

## Context

The Data Quality Assistant runs a mix of checks over item master records. Some
checks are exact and leave no room for interpretation (a required field is either
present or it is not). Others are fuzzy judgments about data that is technically
valid but probably wrong (a description that looks too short, two records that
look like duplicates). A third kind is an outright judgment call that a language
model could help with later (does this description fit the recorded category?).

If every finding were presented the same way, a steward could not tell a certain
problem from a guess, and reviewers could not tell which findings are safe to act
on quickly. We also wanted the confidence number on each finding to mean
something consistent rather than being picked per check without a rule.

## Decision

Every check declares exactly one **source**, and the source determines how much
the finding is trusted:

- **`deterministic_rule`** — exact checks with no interpretation. These carry
  confidence `1.0` (or very close, e.g. `0.95` for missing part number where the
  gap is certain but the fix is a human confirmation). Examples: missing required
  field, invalid field type, invalid record, unsupported unit of measure. They
  live in `dq_assistant/rules.py`.
- **`heuristic`** — fuzzy checks on valid-but-suspect data. These carry
  confidence below `1.0` and say in their explanation why they are not certain.
  Examples: weak description, duplicate family (`duplicate_item_id`,
  `conflicting_source_values`, `potential_duplicate`). They live in
  `dq_assistant/heuristics.py`.
- **`ai_suggestion`** — judgment calls that sit behind the AI boundary. Today
  that is the `category_mismatch_candidate` produced by an offline stub, carrying
  confidence `0.7`. It lives in `dq_assistant/ai_suggester.py` and its output is
  validated by `dq_assistant/validator.py` (see ADR-0002).

The per-check severity and confidence values are fixed in the design document
(design section 6) so they cannot drift silently.

## Consequences

- A steward can triage by source and confidence: deterministic findings are safe
  to act on, heuristic and AI findings deserve a closer look.
- The three-way split maps cleanly onto three modules, so a reader can find any
  check quickly and reason about it in isolation.
- **Tradeoff:** the confidence numbers are reasonable fixed defaults, not
  statistically calibrated scores. A finding with confidence `0.9` is not
  measurably nine-tenths likely to be a real problem; it only ranks above a
  `0.6` finding. Calibrating these numbers against labeled data is a possible
  future improvement.
- **Tradeoff:** forcing each check into exactly one source means a borderline
  check (for example, one that is mostly exact but has a fuzzy edge) has to be
  classified one way, which can feel arbitrary. We accept this for the clarity it
  buys.
