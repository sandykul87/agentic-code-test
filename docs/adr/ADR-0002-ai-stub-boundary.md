# ADR-0002: Put the AI layer behind an interface with a validated output boundary

## Status

Accepted.

## Context

One check — flagging a likely category mismatch from an item's description — is a
judgment call that a language model could help with later. But this is a
time-boxed assignment with a hard constraint: the tool must make no network
calls and must have no runtime dependencies. We cannot call a real model now.

At the same time, LLM output is untrusted input. A model can return the wrong
shape, an out-of-range confidence, an invented category, oversized text, or
wording that claims an item was "fixed" or "auto-approved". If we designed the
tool around a trusting integration now and bolted validation on later, the
guarantees would be weaker and the later change would be riskier.

## Decision

Define the AI layer as a narrow interface now, implement it with a deterministic
offline stub, and validate its output as untrusted data before it can reach the
report.

- **`AISuggester` protocol** (`dq_assistant/ai_suggester.py`) — the single swap
  point. It receives only a *minimal view* of a record (`item_id`,
  `item_description`, `category`) and returns a list of raw suggestions.
- **`StubAISuggester`** — the only implementation in this version. A fixed
  keyword-to-category map, whole-word and case-insensitive, fully offline and
  deterministic. It makes no network calls.
- **`Suggestion_Validator`** (`dq_assistant/validator.py`) — every raw suggestion
  is checked against a fixed schema (correct keys and issue type, numeric and
  in-range confidence, category from the known list, length limits, required
  review wording, no forbidden terms) before it can become a candidate. Anything
  that fails is dropped and counted in `ai_suggestions_rejected`; a suggester
  that raises or returns a non-list is caught and counted in `ai_errors`.

A real model can later replace the stub behind the same protocol, with its output
flowing through the unchanged validator, only after it satisfies the five
conditions in design section 9: (1) data minimization — send only the minimal
view; (2) schema validation — reuse the existing validator; (3) a bounded request
timeout; (4) no secrets in code — keys from the environment; (5) explicit opt-in
before any data leaves the machine, with the offline stub as the default.

## Consequences

- The design and the tests are complete today, with the stub behind the same
  boundary a real model would use. Swapping in a real model does not weaken any
  guarantee, because validation already sits at the boundary.
- The `--no-ai` flag cleanly disables the whole layer, and `ai_enabled`,
  `ai_suggestions_rejected`, and `ai_errors` make the boundary visible in the
  report summary.
- **Tradeoff:** the stub's accuracy is intentionally poor. It only catches
  categories whose keywords are in its small map, and it will miss or
  misclassify anything outside it. We accept this because the value of this
  version is the boundary and the validator, not the stub's hit rate.
- **Tradeoff:** maintaining a protocol, a stub, and a validator is more code than
  inlining a single keyword check would be. That extra structure is the price of
  being able to add a real model later without a rewrite.
