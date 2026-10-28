# Requirements Document

**Feature:** Data Quality Assistant

## Introduction

The Data Quality Assistant is a small command-line tool for an internal enterprise team. A business user gives it a file of item master records. The tool reads the file, runs a fixed set of checks, and writes a JSON report of **review candidates**: records that a human data steward should look at.

The tool never changes the data. It does not fix, correct, merge, or approve anything. Every finding is a *candidate issue* that *needs review*, and each one explains what was detected, why, how severe it looks, how confident the tool is, what the steward could do next, and which kind of logic produced it (a deterministic rule, a heuristic, or an AI suggestion).

The AI layer is a stub in this version. It sits behind a narrow interface and its output goes through the same validation that a real LLM's output would need. That shows how a real model could be added later without trusting it blindly.

This is a time-boxed (about 2 hours) interview assignment. The scope is deliberately small: six core checks plus one lower-priority heuristic, one CLI, Python standard library only at runtime. Simplicity and security take priority over breadth.

The CLI also has a `--help` option (Requirement 20) and an offline `--sample` option that writes a built-in sample file a user can copy as a template (Requirement 21). Requirements 20 to 22 were added after the first review round and are numbered after Requirement 19 so that existing cross-references stay stable.

### Scope at a glance

| In scope | Out of scope (documented as next steps) |
|---|---|
| CLI: `python -m dq_assistant <input> [--output FILE] [--no-ai]` | HTTP API or web UI |
| CLI: `python -m dq_assistant --sample {json,csv} [--output FILE]` (offline, bundled samples) | Downloading samples or templates over the network |
| CLI: `python -m dq_assistant --help` / `-h` | Interactive prompts or a guided wizard |
| JSON (list of objects) and CSV (with header) input; CSV header names matched case-insensitively | Excel, XML, or streaming input |
| Six core checks (3 deterministic rules, 2 heuristics, 1 stubbed AI suggestion) | Normalized description suggestions |
| One lower-priority heuristic: `cross_system_duplicate` (Requirement 22; README next step if deferred) | Cross-system reconciliation or master-record selection |
| Review candidates with stable IDs and `needs_review` status | Recording steward decisions, audit log, apply step |
| Validation of AI output as untrusted data | Real LLM calls or any network access |
| Docs: spec copy, ADRs, AI usage notes, prompt log (`docs/PROMPTS.md`), README | Non-English language processing (known limitation) |

### Input record fields

Each input record may contain these fields: `item_id`, `item_description`, `manufacturer`, `manufacturer_part_number`, `category`, `unit_of_measure`, `source_system`. Any of them may be missing, blank, null, whitespace-only, malformed, duplicated, or inconsistent with other records.

**Required fields** (absence produces a candidate): `item_id`, `item_description`, `manufacturer`, `category`, `unit_of_measure`, `source_system`.
**Optional field**: `manufacturer_part_number`. It is optional on its own, but Requirement 6 flags a missing part number when a real manufacturer is recorded.

**Items without a manufacturer:** consumables, services, and generic stock often have no manufacturer. For these items the user sends the literal value `UNBRANDED` (the Unbranded_Sentinel, matched case-insensitively after trimming) in the `manufacturer` field. `UNBRANDED` is a present, valid value: it does not produce a `missing_required_field` candidate, it does not trigger the missing part number rule (Requirement 6), and it is left out of part-number duplicate grouping (Requirement 9). The README, `--help` text, and `--sample` field guide all explain this default.

## Glossary

- **DQ_Assistant**: The whole command-line tool described in this document, invoked as `python -m dq_assistant`.
- **CLI**: The command-line entry point of the DQ_Assistant. It parses arguments, calls the other components, writes output, and sets the exit code.
- **Report_Mode**: A CLI run that is given an Input_File and produces a Report (Requirements 1 to 16).
- **Sample_Mode**: A CLI run that is given the `--sample` option and writes a Bundled_Sample instead of producing a Report (Requirement 21).
- **Bundled_Sample**: One of two small, synthetic sample Input_Files (`sample.json` and `sample.csv`) stored as data files inside the `dq_assistant` package and written out by Sample_Mode. Distinct from the repository demo samples in Requirement 18.8.
- **Field_Guide**: The short plain-text explanation of the input fields and the Unbranded_Sentinel that Sample_Mode writes to standard error (Requirement 21).
- **Loader**: The component that reads the input file and turns it into a list of raw records. It does not change values.
- **Input_File**: The file path given to the CLI. Its format is chosen by extension: `.json` or `.csv` (case-insensitive).
- **Raw_Record**: One entry from the Input_File exactly as loaded (a JSON value, or a CSV row as a mapping of header to string).
- **Row_Index**: The zero-based position of a Raw_Record in the Input_File (for CSV, the first data row after the header is 0).
- **Field_Value_Reader**: The helper that reads a field from a Raw_Record for checking purposes and classifies the value as present, missing, or invalid type. It returns a trimmed copy and never writes back to the Raw_Record.
- **Missing_Value**: A field value that is absent, JSON `null`, an empty string, a whitespace-only string, or one of the placeholder strings `null`, `none`, `n/a` (compared case-insensitively after trimming). The Unbranded_Sentinel is not a Missing_Value.
- **Unbranded_Sentinel**: The literal value `UNBRANDED` in the `manufacturer` field, matched when the value trimmed with Python `str.strip()` equals `unbranded` case-insensitively (so `UNBRANDED`, `unbranded`, and ` Unbranded ` all match; `Unbranded Generic` does not). Users send it when an item has no manufacturer, for example consumables, services, or generic stock. It is a present, valid `manufacturer` value and has no special meaning in any other field.
- **Invalid_Type_Value**: A field value that is present but is not a string (for example a JSON number, boolean, list, or object).
- **Check**: One unit of detection logic that reads records and produces zero or more Review_Candidates. Each Check has exactly one Source.
- **Rule_Engine**: The set of deterministic Checks (Requirements 5, 6, 7).
- **Heuristic_Engine**: The set of heuristic Checks (Requirements 8, 9, 22).
- **Duplicate_Family**: The Issue_Types that point at a group of related records: `duplicate_item_id`, `conflicting_source_values`, `potential_duplicate`, and `cross_system_duplicate`. A "duplicate-family candidate" is a Review_Candidate with one of these Issue_Types.
- **AI_Suggester**: An interface that receives a minimal view of a record and returns zero or more raw suggestions. In this version the only implementation is the Stub_AI_Suggester.
- **Stub_AI_Suggester**: A deterministic, offline implementation of the AI_Suggester that uses a fixed keyword-to-category map. It makes no network calls.
- **AI_Suggestion**: A raw output object returned by an AI_Suggester before validation. Treated as untrusted data.
- **Suggestion_Validator**: The component that checks every AI_Suggestion against a fixed schema and either converts it into a Review_Candidate or rejects it.
- **Review_Candidate**: One structured finding in the output. Its fields are defined in Requirement 12.
- **Report**: The JSON document the DQ_Assistant writes: a `summary` object plus a `candidates` list.
- **Source**: Which kind of logic produced a Review_Candidate. One of `deterministic_rule`, `heuristic`, `ai_suggestion`.
- **Severity**: How much a candidate issue is likely to matter. One of `low`, `medium`, `high`.
- **Confidence**: A number from 0.0 to 1.0 (inclusive), rounded to two decimals, expressing how likely the candidate issue is real.
- **Issue_Type**: A fixed identifier for the kind of candidate issue. The complete allowed set has 11 values: `missing_required_field`, `invalid_field_type`, `invalid_record`, `missing_part_number`, `unsupported_unit_of_measure`, `weak_description`, `duplicate_item_id`, `conflicting_source_values`, `potential_duplicate`, `cross_system_duplicate`, `category_mismatch_candidate`. All 11 stay in the set even if Requirement 22 is deferred.
- **UoM_Allow_List**: The fixed list of supported unit-of-measure codes, defined in the design document (for example `EA`, `BOX`, `KG`, `M`).
- **Known_Category_List**: The fixed list of category names the Stub_AI_Suggester and Suggestion_Validator accept (for example `Mechanical`, `Electrical`, `Plumbing`), defined in the design document.
- **Normalized_MPN**: A manufacturer part number converted to upper case with spaces, hyphens, dots, slashes, and underscores removed. Example: `6205-ZZ` and `6205 zz` both become `6205ZZ`. Used only for comparison, never written to output as a replacement value.
- **Normalized_Text**: A string trimmed, with internal whitespace collapsed to single spaces, and compared case-insensitively. Used only for comparison.
- **Max_Input_Bytes**: The input size limit: 5 MiB (5,242,880 bytes).
- **Finding_ID**: A stable identifier for a Review_Candidate, derived deterministically from its content (defined in Requirement 13).
- **Data_Steward**: The human who reads the Report and decides what to do with each Review_Candidate.
- **Prompt_Log**: The file `docs/PROMPTS.md`, which records the prompts used to build the DQ_Assistant, the planned future prompts, and the future production LLM prompt template (Requirement 18 criteria 10 to 14).

---

## Requirements

### Requirement 1: Run from the command line

**User Story:** As a business user, I want to run one command against my file, so that I get a review report without setting up a server or installing packages.

**Why this matters:** A single command with no runtime dependencies is the simplest thing that can work, is easy for a reviewer to run, and removes supply-chain risk entirely.

#### Acceptance Criteria

1. WHEN the user runs `python -m dq_assistant <Input_File>` without the `--output` option, THE CLI SHALL write the Report to standard output as one valid JSON document, and SHALL write nothing else to standard output.
2. THE CLI SHALL write all error and diagnostic messages to standard error.
3. WHERE the `--output <path>` option is given in Report_Mode, THE CLI SHALL write the Report to that path as one valid JSON document, replacing any existing file at that path, and SHALL write nothing to standard output. (In Sample_Mode, `--output` refuses to replace an existing file; see Requirement 21 criterion 4.)
4. IF the `--output` path, after resolving relative paths and symbolic links, points to the same file as the Input_File, THEN THE CLI SHALL exit with a non-zero exit code, write an error message to standard error saying the output would overwrite the input, and leave the Input_File byte-for-byte unchanged without creating or changing any file.
5. IF the `--output` path cannot be written (for example, the parent directory does not exist or write permission is denied), THEN THE CLI SHALL exit with a non-zero exit code and write an error message to standard error naming the output path, without writing a partial Report to standard output.
6. IF neither an Input_File argument nor the `--sample` option is given, or an unrecognised option is given, THEN THE CLI SHALL exit with exit code 2, write a usage message to standard error, and not read any file or produce a Report.
7. WHERE the `--no-ai` option is given, THE DQ_Assistant SHALL not invoke the AI_Suggester, and the Report SHALL contain only Review_Candidates whose Source is `deterministic_rule` or `heuristic`.
8. WHEN the CLI has written the Report, THE CLI SHALL exit with exit code 0, whether the `candidates` list is empty or holds one or more Review_Candidates.
9. THE DQ_Assistant SHALL import only modules from the Python 3 standard library at runtime, so that it runs in a clean Python 3 environment with no packages installed.

**Edge cases covered:** an output path that points at the input file, including through a relative path or symbolic link, which would overwrite source data; an output path that cannot be written; a missing input argument (with no `--sample`) or an unknown option; a clean file with no candidates, which still exits 0 with an empty `candidates` list. `--help` is covered by Requirement 20 and `--sample` by Requirement 21.

---

### Requirement 2: Load JSON and CSV input safely

**User Story:** As a business user, I want to upload either JSON or CSV, so that I can use whatever my source system exports.

**Why this matters:** The input file is the main trust boundary. It is user-supplied and may be large, broken, or hostile. Reading it with strict limits and safe parsers prevents crashes and resource exhaustion.

#### Acceptance Criteria

1. WHEN the Input_File extension is `.json` (compared case-insensitively, so `.JSON` also matches), THE Loader SHALL parse the file as UTF-8 JSON using the standard `json` module and SHALL produce one Raw_Record per element of the top-level list, in list order, with the Row_Index equal to the element's zero-based list position.
2. WHEN the Input_File extension is `.csv` (compared case-insensitively), THE Loader SHALL parse the file as UTF-8 CSV with a header row using the standard `csv` module, SHALL accept an optional UTF-8 byte order mark without including it in the first header name, and SHALL treat a comma or line break inside a double-quoted cell as part of that cell's value.
3. WHEN a CSV file is loaded, THE Loader SHALL normalize each header name by removing any byte order mark, then stripping surrounding whitespace with Python `str.strip()`, then lower-casing with Python `str.lower()`, and SHALL represent each data row as a Raw_Record mapping each normalized header name to its cell string, in file order, and SHALL skip lines that contain no characters at all without assigning them a Row_Index. Header normalization changes only the header names, never the cell values.
4. THE Loader SHALL read the Input_File using only the standard `json` and `csv` data parsers, without `eval`, `exec`, `pickle`, or any other mechanism that executes file content.
5. THE Loader SHALL keep every Raw_Record value exactly as read: CSV cells as the original strings, including leading and trailing whitespace, and JSON values with their original JSON type (string, number, boolean, null, list, or object), without trimming or converting them.
6. WHEN a CSV row has more cells than header columns, THE Loader SHALL keep the row as a Raw_Record, map the first cells to the header names, and retain the extra cell values in that Raw_Record separately from the named fields, so that the Rule_Engine can report the row as an `invalid_record` candidate under Requirement 5 criterion 2.
7. WHEN a CSV row has fewer cells than header columns, THE Loader SHALL keep the row as a Raw_Record and the Field_Value_Reader SHALL classify each header column that has no cell in that row as a Missing_Value.
8. THE Rule_Engine, Heuristic_Engine, and AI_Suggester SHALL read only the seven known record fields (all lower-case), matched by exact field name against the Raw_Record keys, and SHALL produce no Review_Candidate based on any other field, while THE Loader SHALL leave those other fields in the Raw_Record unchanged. For CSV the keys are the header names after the normalization in criterion 3, so `item_id`, `Item_ID`, and ` ITEM_ID ` all match `item_id`. For JSON the keys are used exactly as written and matched case-sensitively, so a JSON key `Item_ID` is an unknown field.
9. IF two or more CSV header names are equal after the normalization in criterion 3 (for example `Item_ID` and `item_id`), THEN THE Loader SHALL keep the value from the last such column for that field name (Python `csv.DictReader` behavior), and THE DQ_Assistant SHALL produce no Review_Candidate for the collision. The README documents this as a known limitation.

**Why JSON keys stay case-sensitive:** JSON files usually come from programs with a fixed schema, and lower-casing keys inside one object would need its own collision rule. Keeping JSON exact is the simpler choice; the README states it.

**Edge cases covered:** UTF-8 BOM from Excel exports; ragged CSV rows; extra unknown columns; quoted CSV cells containing commas or newlines; mixed-case or padded CSV headers such as `Item_ID` and ` ITEM_ID `; duplicate CSV headers after lower-casing (last column wins, documented).

---

### Requirement 3: Reject unusable input with a clear error

**User Story:** As a business user, I want a clear message when my file cannot be processed, so that I know what to fix before trying again.

**Why this matters:** Silent failure or a stack trace would confuse a business user and can leak internal details. A short, specific message plus a non-zero exit code is safe and scriptable.

#### Acceptance Criteria

1. IF the Input_File path does not exist, points to a directory, or cannot be opened for reading, THEN THE CLI SHALL print an error message to standard error stating that the file could not be read and exit with exit code 2.
2. IF the Input_File extension, compared case-insensitively, is neither `.json` nor `.csv` (including a file with no extension), THEN THE CLI SHALL print an error message to standard error naming `.json` and `.csv` as the supported formats and exit with exit code 2.
3. IF the Input_File size exceeds Max_Input_Bytes (5,242,880 bytes), THEN THE CLI SHALL print an error message to standard error stating the 5 MiB limit and exit with exit code 2 without parsing the file. A file of exactly 5,242,880 bytes SHALL be accepted by this check.
4. IF the Input_File is zero bytes, or its decoded content consists only of spaces, tabs, carriage returns, and line feeds, THEN THE CLI SHALL print an error message to standard error stating that the file is empty and exit with exit code 2.
5. IF a JSON Input_File's content cannot be parsed as JSON (including truncated JSON), THEN THE CLI SHALL print an error message to standard error stating that the JSON could not be parsed and exit with exit code 2.
6. IF a JSON Input_File's top-level value is not a list (for example an object, string, number, boolean, or `null`), THEN THE CLI SHALL print an error message to standard error stating that a list of records is expected and exit with exit code 2.
7. IF the Input_File contains zero records (a JSON top-level empty list `[]`, or a CSV file with a header row and no data rows), THEN THE CLI SHALL print an error message to standard error stating that no records were found and exit with exit code 2.
8. IF any byte sequence in the Input_File is not valid UTF-8, THEN THE CLI SHALL print an error message to standard error stating that UTF-8 encoding is required and exit with exit code 2.
9. IF any input error in criteria 1 to 8, 10, or 11 occurs, THEN THE CLI SHALL write exactly one line to standard error, and that line SHALL contain no Python stack trace and no content read from the Input_File.
10. IF the first row of a CSV Input_File contains no column name that, after the header normalization in Requirement 2 criterion 3 (byte order mark removed, trimmed, lower-cased), exactly matches one of the seven field names listed under "Input record fields", THEN THE CLI SHALL print an error message to standard error stating that the header is missing or unrecognized and exit with exit code 2.
11. IF the Input_File meets more than one error condition in this requirement, THEN THE CLI SHALL report only the first failing condition, evaluated in this order: unreadable (1), unsupported extension (2), oversized (3), invalid UTF-8 (8), empty (4), unparseable JSON (5), JSON top-level value not a list (6), unrecognized CSV header (10), zero records (7).
12. IF any input error in this requirement occurs, THEN THE CLI SHALL write nothing to standard output, SHALL not create a Report file, and SHALL leave any existing file at the `--output` path unchanged.

**Edge cases covered:** empty input file; whitespace-only file; header-only CSV; `[]`; a JSON object instead of a list; truncated JSON; binary or Latin-1 file; oversized file; a `.txt` or `.xlsx` file.

---

### Requirement 4: Treat blanks, nulls, and placeholders consistently

**User Story:** As a data steward, I want empty-looking values to be treated the same way, so that `""`, `"   "`, `null`, and `"N/A"` do not slip past the checks.

**Why this matters:** Real exports encode "no value" in many ways. If each check handled this differently, results would be inconsistent and hard to explain. One shared reader gives one definition.

#### Acceptance Criteria

1. WHEN the Field_Value_Reader reads a field from a Raw_Record, THE Field_Value_Reader SHALL return exactly one of three classifications for that field: present, Missing_Value, or Invalid_Type_Value.
2. WHEN the Field_Value_Reader reads a field that is absent from the Raw_Record (including a column missing from the CSV header), is JSON `null`, or is a string that after Python `str.strip()` is empty or equals `null`, `none`, or `n/a` (case-insensitive, whole-value match), THE Field_Value_Reader SHALL classify the field as Missing_Value.
3. WHEN the Field_Value_Reader reads a field that is present, is not JSON `null`, and is not a string (a number, boolean, list, or object), THE Field_Value_Reader SHALL classify the field as Invalid_Type_Value and SHALL NOT convert the value to a string.
4. WHEN the Field_Value_Reader reads a field that is a string and is not a Missing_Value, THE Field_Value_Reader SHALL classify the field as present and return the value trimmed with Python `str.strip()`, keeping internal characters and letter case unchanged.
5. WHEN the Field_Value_Reader returns a classification or trimmed value, THE Field_Value_Reader SHALL leave the Raw_Record unchanged, so that the Raw_Record compares equal to a copy taken before the read.
6. WHEN the Field_Value_Reader reads the same field of the same Raw_Record more than once, THE Field_Value_Reader SHALL return the same classification and the same trimmed value each time.
7. THE Rule_Engine, Heuristic_Engine, and AI_Suggester input builder SHALL obtain field values only through the Field_Value_Reader, so that any field value classified as Missing_Value is treated as missing by every Check.
8. WHEN the Field_Value_Reader reads a `manufacturer` value that matches the Unbranded_Sentinel, THE Field_Value_Reader SHALL classify the field as present and return the trimmed value unchanged in letter case, and THE Rule_Engine and Heuristic_Engine SHALL apply the Unbranded_Sentinel test to that trimmed value with a case-insensitive comparison.

**Edge cases covered:** `UNBRANDED`, `unbranded`, and ` Unbranded ` as a manufacturer (present, not missing); whitespace-only strings; nulls; the literal text "NULL" from database exports; tabs and non-breaking spaces (trimmed via Python `str.strip()`); numeric `item_id` in JSON (Invalid_Type_Value); placeholder text inside a longer value, such as `"N/A bracket"`, which stays present because the placeholder match covers the whole value only; boolean `false` and number `0`, which are Invalid_Type_Value and not Missing_Value.

---

### Requirement 5: Deterministic rule — malformed or incomplete records

**User Story:** As a data steward, I want records with missing required fields or wrong data types flagged, so that I can ask the source owner to complete them.

**Why this matters:** Incomplete records break downstream processes such as purchasing and inventory. These checks are exact, so they are the most trustworthy findings in the Report.

#### Acceptance Criteria

1. WHEN a Raw_Record from a JSON Input_File is not a JSON object (a number, string, boolean, list, or null), THE Rule_Engine SHALL produce exactly one `invalid_record` candidate for that Row_Index, with Severity `high`, Confidence `1.0`, Source `deterministic_rule`, and candidate `item_id` set to JSON `null`, and SHALL run no other Check on that record.
2. WHEN a CSV row has more cells than the header has columns, THE Rule_Engine SHALL produce exactly one `invalid_record` candidate for that Row_Index, with Severity `high`, Confidence `1.0`, and Source `deterministic_rule`, and SHALL run no other Check on that row.
3. IF a CSV row has fewer cells than the header has columns, THEN THE Rule_Engine SHALL treat each absent cell as a Missing_Value and SHALL NOT produce an `invalid_record` candidate for that row.
4. WHEN one or more of the six required fields (`item_id`, `item_description`, `manufacturer`, `category`, `unit_of_measure`, `source_system`) of a Raw_Record is a Missing_Value, THE Rule_Engine SHALL produce one `missing_required_field` candidate per missing required field, naming that field. Each candidate SHALL have Severity `high` when the field is `item_id` and `medium` otherwise, Confidence `1.0`, and Source `deterministic_rule`. A single record SHALL therefore produce between 0 and 6 such candidates. A `manufacturer` that matches the Unbranded_Sentinel is present and SHALL NOT produce a `missing_required_field` candidate.
5. IF the optional field `manufacturer_part_number` is a Missing_Value, THEN THE Rule_Engine SHALL NOT produce a `missing_required_field` candidate for that field.
6. WHEN any of the seven input record fields (listed under "Input record fields") of a Raw_Record is an Invalid_Type_Value, THE Rule_Engine SHALL produce one `invalid_field_type` candidate per such field, naming the field and its observed JSON type as one of `number`, `boolean`, `list`, or `object`, with Severity `medium`, Confidence `1.0`, and Source `deterministic_rule`. A JSON `true` or `false` SHALL be reported as `boolean`, not `number`.
7. IF a Raw_Record contains a field name outside the seven input record fields, THEN THE Rule_Engine SHALL ignore that field and SHALL NOT produce any candidate for it.
8. WHEN a field is reported as `invalid_field_type`, THE Rule_Engine SHALL treat that field as unusable for all other Checks on that record and SHALL NOT produce a `missing_required_field` candidate for the same field.
9. WHEN a Raw_Record's `item_id` is a Missing_Value or an Invalid_Type_Value, THE DQ_Assistant SHALL identify every candidate for that record by its Row_Index and SHALL set the candidate `item_id` to JSON `null`, without writing the original invalid value into the candidate `item_id`.
10. WHEN the Rule_Engine produces a `missing_required_field` candidate for `manufacturer`, THE Rule_Engine SHALL set the suggested action to a step asking the Data_Steward to confirm the manufacturer with the source owner, or to confirm that the item has no manufacturer and should record `UNBRANDED`.

**Edge cases covered:** missing required fields, including a missing `manufacturer` (now required); `UNBRANDED` as the manufacturer (present, no candidate); nulls; whitespace-only values; non-object rows in a JSON list; `item_id: 1001` as a number; a record with every field blank (one candidate per missing required field, six in total, no crash); CSV rows with too many or too few cells; boolean values reported as `boolean`; unknown extra fields ignored.

---

### Requirement 6: Deterministic rule — missing manufacturer part number

**User Story:** As a data steward, I want to know when a manufacturer is recorded but its part number is not, so that I can request the part number and make the item purchasable.

**Why this matters:** A manufacturer without a part number is a common, exact, and actionable gap. This is the example given in the assignment. Unbranded items have no manufacturer part number by definition, so flagging them would only add noise.

#### Acceptance Criteria

1. WHEN the Field_Value_Reader classifies `manufacturer` as present, the `manufacturer` value does not match the Unbranded_Sentinel, and `manufacturer_part_number` is a Missing_Value, THE Rule_Engine SHALL produce exactly one `missing_part_number` candidate for that record, with `field` set to `manufacturer_part_number`, Severity `medium`, Confidence `0.95`, and Source `deterministic_rule`.
2. THE Rule_Engine SHALL set the `missing_part_number` candidate explanation to a statement beginning with "Candidate issue:" that says the manufacturer is present and the manufacturer part number is missing, and SHALL set the suggested action to a step asking the Data_Steward to confirm the manufacturer part number with the source owner.
3. WHEN `manufacturer` is a Missing_Value, THE Rule_Engine SHALL produce no `missing_part_number` candidate for that record, leaving the finding to the `missing_required_field` candidate under Requirement 5 criterion 4.
4. WHEN `manufacturer_part_number` is a non-missing string, THE Rule_Engine SHALL produce no `missing_part_number` candidate for that record.
5. IF `manufacturer` or `manufacturer_part_number` is an Invalid_Type_Value, THEN THE Rule_Engine SHALL produce no `missing_part_number` candidate for that record, leaving the field to be reported as `invalid_field_type` under Requirement 5.
6. THE Rule_Engine SHALL produce the `missing_part_number` candidate without modifying the Raw_Record and without writing any proposed part number value into the candidate.
7. WHEN `manufacturer` matches the Unbranded_Sentinel, THE Rule_Engine SHALL produce no `missing_part_number` candidate for that record, whatever the `manufacturer_part_number` value is.

**Example output:**

```json
{"item_id": "1001", "issue_type": "missing_part_number", "severity": "medium", "confidence": 0.95,
 "explanation": "Candidate issue: manufacturer is present but manufacturer part number is missing.",
 "suggested_action": "Confirm the manufacturer part number with the source owner.",
 "source": "deterministic_rule"}
```

**Edge cases covered:** part number blank or whitespace-only; part number `"N/A"`; both manufacturer and part number missing (no candidate from this rule; the missing manufacturer is reported as `missing_required_field` by Requirement 5 criterion 4); manufacturer `UNBRANDED` (any case, with surrounding spaces) and no part number (no candidate from this rule and no `missing_required_field`).

---

### Requirement 7: Deterministic rule — unsupported unit of measure

**User Story:** As a data steward, I want units of measure outside the approved list flagged, so that ordering and inventory quantities stay consistent.

**Why this matters:** A unit like `EACH`, `pcs`, or `bx` instead of the approved codes causes quantity errors downstream. An allow-list is exact, explainable, and easy to extend.

#### Acceptance Criteria

1. WHEN the Field_Value_Reader classifies `unit_of_measure` as present and its trimmed value does not equal any UoM_Allow_List entry under case-insensitive comparison, THE Rule_Engine SHALL produce exactly one `unsupported_unit_of_measure` candidate for that Raw_Record with Severity `medium`, Confidence `0.9`, and Source `deterministic_rule`.
2. WHEN the Rule_Engine produces an `unsupported_unit_of_measure` candidate, THE Rule_Engine SHALL include the trimmed observed value in the explanation, and SHALL set the suggested action to confirm the correct unit with the source owner and map the value to an approved code.
3. IF the trimmed observed value is longer than 50 characters, THEN THE Rule_Engine SHALL include only the first 50 characters of that value in the explanation.
4. WHEN the trimmed value of `unit_of_measure` equals a UoM_Allow_List entry under case-insensitive comparison (for example `ea` or `"EA "` for `EA`), THE Rule_Engine SHALL omit the `unsupported_unit_of_measure` candidate.
5. IF the Field_Value_Reader classifies `unit_of_measure` as a Missing_Value or an Invalid_Type_Value, THEN THE Rule_Engine SHALL omit the `unsupported_unit_of_measure` candidate for that Raw_Record, leaving the finding to the `missing_required_field` or `invalid_field_type` checks.
6. THE Rule_Engine SHALL leave the Raw_Record's `unit_of_measure` value unchanged and SHALL NOT output a replacement unit code.

**Edge cases covered:** unsupported UoM; lower-case approved codes; `"EA "` with trailing space; very long or garbage UoM strings (explanation truncates the observed value to 50 characters); missing or non-string UoM (handled by other checks, no duplicate candidate).

---

### Requirement 8: Heuristic — weak or vague description

**User Story:** As a data steward, I want very short or abbreviation-heavy descriptions flagged, so that I can ask for a description that identifies the item.

**Why this matters:** A description like "bearing" or "valve" cannot distinguish between thousands of items. This check is a heuristic, not an exact rule, so it reports lower confidence and says so.

#### Acceptance Criteria

1. WHEN the Field_Value_Reader classifies `item_description` as present and the trimmed value, with internal whitespace collapsed to single spaces, has fewer than 3 words or fewer than 10 characters, THE Heuristic_Engine SHALL produce a `weak_description` candidate with Severity `low`, Confidence `0.8`, Source `heuristic`, and an explanation stating that the description is too short, including its word count and character count. A value of exactly 3 words and exactly 10 characters does not meet this condition.
2. WHEN the Field_Value_Reader classifies `item_description` as present, the value has 3 or more words and 10 or more characters, and strictly more than half of its words are 3 characters or shorter, THE Heuristic_Engine SHALL produce a `weak_description` candidate with Severity `low`, Confidence `0.6`, Source `heuristic`, and an explanation stating that the description appears abbreviation-heavy, including the number of short words and the total word count.
3. IF a record meets the conditions of both criterion 1 and criterion 2, THEN THE Heuristic_Engine SHALL produce exactly one `weak_description` candidate for that record, using the criterion 1 Confidence (`0.8`) and explanation.
4. WHEN the Heuristic_Engine produces a `weak_description` candidate, THE Heuristic_Engine SHALL set the suggested action to a step asking the Data_Steward to check with the source owner and request a fuller description that includes the item type, the size, and the key attributes.
5. IF `item_description` is a Missing_Value or an Invalid_Type_Value, THEN THE Heuristic_Engine SHALL NOT produce a `weak_description` candidate for that record.
6. THE Heuristic_Engine SHALL define a word as one token from splitting the trimmed value on whitespace, define a word's length as the number of characters in that token (letters, digits, and punctuation all count), and count characters as Unicode characters, not bytes. This SHALL apply to descriptions that contain non-ASCII characters and SHALL not raise an error.

**Edge cases covered:** very short descriptions ("bearing", "valve"); abbreviation-heavy descriptions ("BRG BL 6205 ZZ SS": 5 words, 4 of them 3 characters or shorter, flagged by criterion 2); non-English descriptions (processed with the same counts; no translation or language detection, documented as a known limitation).

**Known limitation:** Word counting uses whitespace splitting. Languages without spaces between words (for example Chinese or Japanese) may be flagged as weak. The README documents this.

---

### Requirement 9: Heuristic — duplicates and conflicting source values

**User Story:** As a data steward, I want potential duplicates and conflicting copies of the same item flagged together, so that I can decide which record is authoritative.

**Why this matters:** Duplicates inflate inventory and split purchase history. The tool must not merge anything; it only points at the related records and lets the Data_Steward decide.

#### Acceptance Criteria

1. WHEN two or more Raw_Records share the same Normalized_Text `item_id` and the same Normalized_Text `source_system`, THE Heuristic_Engine SHALL produce exactly one `duplicate_item_id` candidate for each such record, with `field` `item_id`, Severity `high`, Confidence `0.95`, and Source `heuristic`. For this comparison, a `source_system` that is a Missing_Value or Invalid_Type_Value SHALL count as equal to any other Missing_Value or Invalid_Type_Value `source_system`, and as different from every non-missing string.
2. WHEN a Raw_Record shares its Normalized_Text `item_id` with one or more Raw_Records that have a different `source_system` value (compared as in criterion 1), and at least one compared field differs from at least one of those records, THE Heuristic_Engine SHALL produce exactly one `conflicting_source_values` candidate for that record, with `field` JSON `null`, Severity `medium`, Confidence `0.85`, and Source `heuristic`. The compared fields are `item_description`, `manufacturer`, `category`, and `unit_of_measure` (compared by Normalized_Text) and `manufacturer_part_number` (compared by Normalized_MPN).
3. THE Heuristic_Engine SHALL name every differing compared field in the explanation of each `conflicting_source_values` candidate, listing field names in the order given in criterion 2.
4. WHEN comparing a field for criterion 2, THE Heuristic_Engine SHALL treat two Missing_Values as equal, a Missing_Value and a non-missing string as different, and SHALL skip the field for any pair in which either value is an Invalid_Type_Value.
5. WHEN two or more Raw_Records share the same Normalized_Text `item_id`, have different `source_system` values, and no compared field differs, THE Heuristic_Engine SHALL produce no `conflicting_source_values` candidate for those records, and SHALL instead produce a `cross_system_duplicate` candidate for each such record as defined in Requirement 22 (or no candidate, if Requirement 22 is deferred under Requirement 22 criterion 7).
6. WHEN a group of Raw_Records shares the same Normalized_Text `item_id` and contains both records with the same `source_system` and records with a different `source_system`, THE Heuristic_Engine SHALL apply criteria 1 and 2 and Requirement 22 independently, so one record MAY receive a `duplicate_item_id` candidate together with either a `conflicting_source_values` candidate or a `cross_system_duplicate` candidate.
7. WHEN two or more Raw_Records with different Normalized_Text `item_id` values share the same Normalized_Text `manufacturer` and the same non-empty Normalized_MPN, THE Heuristic_Engine SHALL produce exactly one `potential_duplicate` candidate for each such record, with `field` `manufacturer_part_number`, Severity `medium`, and Source `heuristic`.
8. WHEN all records in a `potential_duplicate` group have identical `manufacturer_part_number` strings after trimming (case-sensitive), THE Heuristic_Engine SHALL set Confidence `0.9` on every candidate in that group.
9. WHEN the trimmed `manufacturer_part_number` strings in a `potential_duplicate` group are not all identical (for example `6205-ZZ` and `6205 ZZ`), THE Heuristic_Engine SHALL set Confidence `0.75` on every candidate in that group.
10. THE Heuristic_Engine SHALL set `related_item_ids` and `related_row_indexes` on each duplicate-family candidate to the trimmed `item_id` values and Row_Index values of the other records in the same group, excluding the candidate's own record, ordered by ascending Row_Index, with the two lists in matching order.
11. THE Heuristic_Engine SHALL exclude records whose `item_id` is a Missing_Value or Invalid_Type_Value from `item_id` grouping (criteria 1, 2, and 6, and Requirement 22), and SHALL exclude from part-number grouping (criterion 7) records whose `manufacturer` or `manufacturer_part_number` is a Missing_Value or Invalid_Type_Value, records whose Normalized_MPN is empty, and records whose `manufacturer` matches the Unbranded_Sentinel, because unbranded items do not share a manufacturer identity.
12. THE Heuristic_Engine SHALL set the suggested action of every `duplicate_item_id`, `conflicting_source_values`, and `potential_duplicate` candidate to a step asking the Data_Steward to review the related records and decide which one is authoritative, and SHALL NOT include an instruction to merge, delete, or overwrite any record in the suggested action of any duplicate-family candidate.
13. THE Heuristic_Engine SHALL leave every Raw_Record unchanged when producing duplicate-family candidates, so that `item_id` and other values in the Report match the input after trimming only.

**Edge cases covered:** duplicate `item_id` within one system; the same item from different source systems (conflicting values here, identical values in Requirement 22); conflicting source-system values; the same MPN in different formats (`6205-ZZ` vs `6205 ZZ`); `item_id` differing only in case or surrounding whitespace; groups of three or more records; two `UNBRANDED` items with the same part number under different IDs (not grouped as `potential_duplicate`).

---

### Requirement 10: AI suggestion (stubbed) — category mismatch candidate

**User Story:** As a data steward, I want a hint when the description suggests a different category than the one recorded, so that I can catch miscategorized items like "SKF Bearing 6205 ZZ" filed under Electrical.

**Why this matters:** Category mismatch is a judgment call that a language model could help with later. Putting it behind an interface now, with a deterministic stub, lets the design and tests be complete today and lets a real model be added later without changing the rest of the tool.

#### Acceptance Criteria

1. THE AI_Suggester SHALL accept a minimal record view containing exactly three fields, `item_id`, `item_description`, and `category`, and SHALL return a list of zero or more AI_Suggestions.
2. WHEN the DQ_Assistant calls the AI_Suggester for a record, THE DQ_Assistant SHALL build the minimal record view from the trimmed copies returned by the Field_Value_Reader, SHALL set `item_id` to JSON `null` if `item_id` is a Missing_Value or Invalid_Type_Value, and SHALL include no other fields of the Raw_Record.
3. WHEN `item_description` contains one or more keywords from the Stub_AI_Suggester keyword map, all matched keywords map to the same category, and that category differs from the record's `category` by Normalized_Text comparison, THE Stub_AI_Suggester SHALL return exactly one AI_Suggestion with Issue_Type `category_mismatch_candidate`, a suggested category spelled exactly as in the Known_Category_List, a Confidence of `0.7`, an explanation that names the matched keyword and the recorded category, and a suggested action that asks the Data_Steward to review the category.
4. THE Stub_AI_Suggester SHALL match a keyword only when it appears in `item_description` case-insensitively and is bounded on each side by the start or end of the string or by a character that is not a letter or digit.
5. IF no keyword matches, the matched keywords map to more than one distinct category, or the single mapped category equals the record's `category` by Normalized_Text comparison, THEN THE Stub_AI_Suggester SHALL return an empty list for that record.
6. IF `item_description` or `category` is a Missing_Value or Invalid_Type_Value, THEN THE DQ_Assistant SHALL not call the AI_Suggester for that record and SHALL produce no `category_mismatch_candidate` for that record, without changing `ai_suggestions_rejected` or `ai_errors` in the Report summary.
7. THE Stub_AI_Suggester SHALL return an identical list of AI_Suggestions each time it receives the same minimal record view, and SHALL make no network calls.
8. WHEN the AI_Suggester returns AI_Suggestions for a record, THE DQ_Assistant SHALL pass every AI_Suggestion through the Suggestion_Validator (Requirement 11) and SHALL label every resulting Review_Candidate with Source `ai_suggestion` and `field` set to `category`.

**Edge cases covered:** description with useful attributes but wrong category ("SKF Bearing 6205 ZZ" under Electrical); ambiguous descriptions matching several categories (no suggestion rather than a guess); keyword inside another word (e.g. "cable" should not match inside "cableway" if the map uses whole words); missing category.

---

### Requirement 11: Treat AI output as untrusted

**User Story:** As a security reviewer, I want every AI suggestion validated before it reaches the Report, so that a future real LLM cannot inject invalid, oversized, or misleading content.

**Why this matters:** LLM output is untrusted input. A model can return the wrong shape, an out-of-range number, an invented category, or text that claims an item was "fixed". Validating at this boundary now means swapping in a real model later does not weaken the guarantees.

#### Acceptance Criteria

1. THE Suggestion_Validator SHALL accept an AI_Suggestion only if the AI_Suggestion is a mapping that contains the keys `issue_type`, `confidence`, `suggested_category`, `explanation`, and `suggested_action`, and its `issue_type` value is exactly the string `category_mismatch_candidate`.
2. THE Suggestion_Validator SHALL accept an AI_Suggestion only if its `confidence` is an integer or floating-point number (not a boolean and not a string), is finite, and is from 0.0 to 1.0 inclusive.
3. THE Suggestion_Validator SHALL accept an AI_Suggestion only if its `suggested_category` is a string that exactly matches (case-sensitive) an entry in the Known_Category_List and is not equal, as Normalized_Text, to the record's current `category` value.
4. THE Suggestion_Validator SHALL accept an AI_Suggestion only if its `explanation` is a string of 1 to 500 characters containing at least one non-whitespace character, and its `suggested_action` is a string of 1 to 300 characters containing at least one non-whitespace character.
5. THE Suggestion_Validator SHALL accept an AI_Suggestion only if neither its `explanation` nor its `suggested_action` contains any of the terms listed in Requirement 14 criterion 4, matched case-insensitively as whole words (the same matching as Requirement 14 criterion 4).
6. THE Suggestion_Validator SHALL accept an AI_Suggestion only if its `explanation` contains at least one of "candidate", "potential", or "needs review" (case-insensitive) and its `suggested_action` contains at least one of "review", "verify", "confirm", or "check" (case-insensitive), matching Requirement 14 criteria 2 and 3.
7. IF an AI_Suggestion fails any check in criteria 1 to 6, THEN THE Suggestion_Validator SHALL drop that AI_Suggestion without producing a Review_Candidate, THE DQ_Assistant SHALL increment `ai_suggestions_rejected` in the Report summary by exactly 1, and THE DQ_Assistant SHALL continue processing the remaining suggestions, Checks, and records.
8. IF the AI_Suggester raises an exception for a record, or returns a value that is not a list, THEN THE DQ_Assistant SHALL discard all AI output for that record, increment `ai_errors` in the Report summary by exactly 1 for that record, and continue processing all other Checks and records to a complete Report.
9. WHEN the Suggestion_Validator accepts an AI_Suggestion, THE Suggestion_Validator SHALL build the Review_Candidate from only the validated `confidence` (rounded to two decimal places), `suggested_category`, `explanation`, and `suggested_action` values, ignoring any other keys in the AI_Suggestion.
10. WHEN the Suggestion_Validator builds a Review_Candidate from an AI_Suggestion, THE Suggestion_Validator SHALL set `item_id` (from the Raw_Record via the Field_Value_Reader, or JSON `null` if missing), `row_index` (the record's Row_Index), `field` (`category`), `severity` (`low`), and `source` (`ai_suggestion`) itself, and SHALL NOT copy these values from the AI_Suggestion.
11. IF the AI_Suggester returns more than one AI_Suggestion that passes criteria 1 to 6 for the same record, THEN THE Suggestion_Validator SHALL accept only the first one in returned order and SHALL count each additional one in `ai_suggestions_rejected`.

**Edge cases covered:** wrong type returned (a suggestion that is not a mapping, or a return value that is not a list); missing keys; confidence `1.5`, `-0.1`, `"0.9"`, `true`, or `NaN`; invented category; suggested category equal to the current category; whitespace-only or 10,000-character explanation; text containing "auto-approved"; extra keys such as `severity` or `item_id` in the suggestion; two valid suggestions for one record; the suggester raising an exception.

---

### Requirement 12: Review candidate structure

**User Story:** As a data steward, I want every finding in the same shape, so that I can sort, filter, and act on them consistently.

**Why this matters:** A fixed schema makes the Report easy to read, test, and feed into a later review tool. Required fields like `explanation` and `source` make every finding traceable to the logic that produced it.

#### Acceptance Criteria

1. THE DQ_Assistant SHALL include in every Review_Candidate exactly the fields `finding_id`, `item_id`, `row_index`, `issue_type`, `field`, `severity`, `confidence`, `explanation`, `suggested_action`, `source`, `status`, and `allowed_actions`, plus only the conditional fields defined in criteria 9 and 10.
2. THE DQ_Assistant SHALL set `status` to the string `needs_review` on every Review_Candidate.
3. THE DQ_Assistant SHALL set `allowed_actions` to the list `["approve", "reject", "investigate"]`, in that order, on every Review_Candidate.
4. THE DQ_Assistant SHALL set `issue_type` to a value in the Issue_Type set, `severity` to a value in the Severity set, and `source` to a value in the Source set on every Review_Candidate.
5. THE DQ_Assistant SHALL set `confidence` to a JSON number (not a boolean or string) from 0.0 to 1.0 inclusive, rounded to two decimal places, on every Review_Candidate.
6. THE DQ_Assistant SHALL set `item_id` to the trimmed string value of the record's `item_id`, or to JSON `null` when that `item_id` is a Missing_Value or Invalid_Type_Value (as stated in Requirement 5), and SHALL set `row_index` to the integer Row_Index (0 or greater) of the record the candidate concerns.
7. THE DQ_Assistant SHALL set `field` to the name of one of the seven input record fields when the candidate concerns a single field, and to JSON `null` when the candidate concerns the whole record (`invalid_record`, `conflicting_source_values`, or `cross_system_duplicate`).
8. THE DQ_Assistant SHALL set `explanation` to a non-empty string of at most 500 characters and `suggested_action` to a non-empty string of at most 300 characters on every Review_Candidate.
9. WHERE a candidate's `issue_type` is in the Duplicate_Family (`duplicate_item_id`, `conflicting_source_values`, `potential_duplicate`, or `cross_system_duplicate`), THE DQ_Assistant SHALL include `related_item_ids` (the `item_id` values, or JSON `null` for a missing one, of the other records in the same group) and `related_row_indexes` (the Row_Indexes of those same records), both listed in ascending Row_Index order with matching positions, and SHALL omit both fields on all other candidates.
10. WHERE a candidate's `issue_type` is `category_mismatch_candidate`, THE DQ_Assistant SHALL include `suggested_category` set to a value in the Known_Category_List, and SHALL omit `suggested_category` on all other candidates.
11. WHEN an explanation includes an observed input value longer than 50 characters, THE DQ_Assistant SHALL include only the first 50 characters of that value in the explanation.

**Edge cases covered:** candidates for records without an `item_id` (identified by `row_index`); whole-record issues (`field: null`).

---

### Requirement 13: Stable, deterministic output

**User Story:** As a data steward, I want the same file to produce the same report every time, so that I can compare runs and refer to findings by ID.

**Why this matters:** Deterministic output makes the tool testable and lets a future decision log reference a `finding_id` across runs.

#### Acceptance Criteria

1. THE DQ_Assistant SHALL derive each `finding_id` as the first 16 lowercase hexadecimal characters of the SHA-256 hash of the UTF-8 string formed by joining the candidate's `issue_type`, `row_index` (as a base-10 integer), `item_id`, and `field` with the `|` character, in that order, where a JSON `null` `item_id` or `field` is written as an empty string.
2. WHEN the same Input_File is processed twice with the same CLI options, THE DQ_Assistant SHALL produce byte-identical Reports, regardless of the time of the run, the current working directory, or the path used to reference the Input_File.
3. THE DQ_Assistant SHALL exclude from the Report any value that varies between runs on identical input, including timestamps, durations, random values, and absolute file paths.
4. THE DQ_Assistant SHALL write the Report as UTF-8 JSON with the same key order in every object on every run.
5. THE DQ_Assistant SHALL order candidates by `row_index` ascending, then `issue_type` ascending, then `field` ascending, with a JSON `null` `field` sorted before any named field.
6. THE DQ_Assistant SHALL produce at most one Review_Candidate per combination of `issue_type`, `row_index`, and `field` within one Report, so that every `finding_id` in the Report is unique.

**Edge cases covered:** repeated runs; two candidates of different types on the same record; records with null `item_id`; whole-record candidates with `field: null`; the same Input_File referenced by relative and absolute paths.

---

### Requirement 14: Review-oriented language

**User Story:** As a data steward, I want the Report to describe findings as candidates, so that nobody mistakes a suggestion for a completed change.

**Why this matters:** The tool has no authority to change data. Wording like "fixed" or "auto-approved" would mislead users into skipping review. A test enforces the wording so it cannot drift.

#### Acceptance Criteria

1. THE DQ_Assistant SHALL set the status of every Review_Candidate in the Report to `needs_review`, regardless of Source, Severity, or Confidence.
2. THE DQ_Assistant SHALL produce, for every Review_Candidate, an explanation that contains at least one of the phrases "candidate", "potential", or "needs review" (case-insensitive).
3. THE DQ_Assistant SHALL produce, for every Review_Candidate, a suggested action that contains at least one of the words "review", "verify", "confirm", or "check" (case-insensitive), so the action is phrased as a step for the Data_Steward to take.
4. THE DQ_Assistant SHALL produce Reports in which no explanation, suggested action, or summary text contains the terms "fixed", "corrected", "auto-approved", "auto-fixed", or "resolved" as whole words (case-insensitive). Field values copied verbatim from Raw_Records into that text are excluded from this check.
5. THE DQ_Assistant SHALL include in the Report summary a notice stating that all findings are candidate issues that need human review by a Data_Steward and that no input data was modified.
6. WHEN the DQ_Assistant produces a Report with zero Review_Candidates, or runs with the `--no-ai` option, THE DQ_Assistant SHALL still include the notice defined in criterion 5 in the Report summary.

---

### Requirement 15: Never modify input data

**User Story:** As a data owner, I want proof that the tool never changes my records, so that I can run it on production exports without risk.

**Why this matters:** "Never auto-modify data" is the core promise of the assignment. It must be guaranteed by design (read-only input, no write path) and proven by a test, not just stated.

#### Acceptance Criteria

1. WHEN the CLI exits, with either a zero or a non-zero exit code, THE DQ_Assistant SHALL leave the Input_File with the same byte content, the same byte length, and the same modification time it had before the CLI started.
2. WHEN all Checks have run, including the AI_Suggester and the Suggestion_Validator, THE DQ_Assistant SHALL leave every in-memory Raw_Record equal to a deep copy of that Raw_Record taken before the first Check ran.
3. THE DQ_Assistant SHALL copy any record field value it places in the Report verbatim from the Raw_Record, and SHALL NOT include any corrected, normalized (Normalized_MPN or Normalized_Text), or merged version of a record or field value in the Report.
4. IF the `--output` path resolves to the same file as the Input_File, THEN THE CLI SHALL exit with a non-zero exit code, write an error message to standard error indicating that the output path would overwrite the input, and leave the Input_File unchanged, as specified in Requirement 1 criterion 4.
5. FOR ALL generated record lists of 0 to 50 records, whose field values include Missing_Values, Invalid_Type_Values, duplicates, and non-ASCII strings, running all Checks SHALL leave the record list equal to its pre-run deep copy (property-based test, at least 100 generated cases).

---

### Requirement 16: Report summary

**User Story:** As a data steward, I want a short summary at the top of the report, so that I can see the size of the cleanup job at a glance.

**Why this matters:** Counts by type and severity let the steward prioritize, and AI rejection counts make the AI boundary visible.

#### Acceptance Criteria

1. WHEN processing completes, THE DQ_Assistant SHALL include in the Report summary exactly these entries: `records_read`, `candidates_total`, a count map per `issue_type`, a count map per `severity`, a count map per `source`, `ai_enabled`, `ai_suggestions_rejected`, `ai_errors`, and the notice from Requirement 14.
2. THE DQ_Assistant SHALL set `records_read` to the number of Raw_Records loaded from the Input_File, counting every Raw_Record, including those that produced an `invalid_record` candidate.
3. THE DQ_Assistant SHALL set `candidates_total` equal to the length of the `candidates` list.
4. THE DQ_Assistant SHALL include in the per-`issue_type` count map one key for each of the 11 Issue_Type values (including `cross_system_duplicate`, which stays at 0 if Requirement 22 is deferred), in the per-`severity` count map one key for each of the 3 Severity values, and in the per-`source` count map one key for each of the 3 Source values. Each value SHALL be a non-negative integer equal to the number of Review_Candidates in the `candidates` list with that value, and SHALL be 0 when no candidate has that value.
5. THE DQ_Assistant SHALL set each per-`issue_type`, per-`severity`, and per-`source` count map so that its values sum to `candidates_total`.
6. THE DQ_Assistant SHALL set `ai_suggestions_rejected` and `ai_errors` to non-negative integers equal to the number of increments made under Requirement 11 during the run.
7. WHERE the `--no-ai` option is given, THE DQ_Assistant SHALL set `ai_enabled` to `false`, `ai_suggestions_rejected` to 0, `ai_errors` to 0, and the `ai_suggestion` count in the per-`source` map to 0.
8. WHERE the `--no-ai` option is not given, THE DQ_Assistant SHALL set `ai_enabled` to `true`.

---

### Requirement 17: Security and privacy constraints

**User Story:** As a security reviewer, I want the tool to have a minimal attack surface, so that it is safe to run on internal data.

**Why this matters:** Item master data can include supplier names and internal identifiers. The tool should not send data anywhere, should not execute anything from the input, and should not leak data through errors or logs.

#### Acceptance Criteria

1. THE DQ_Assistant SHALL open no network sockets and make no DNS lookups during any run, including runs where the AI_Suggester is enabled (verifiable by running the full test suite with socket creation disabled and observing no failures caused by blocked network access).
2. THE DQ_Assistant source code SHALL contain no calls to `eval`, `exec`, `compile`, `pickle`, `marshal`, or `subprocess`, and no `importlib`/`__import__` call whose module name comes from the Input_File, a Raw_Record, or a CLI argument.
3. THE DQ_Assistant SHALL write only to standard output, standard error, and, when `--output` is given, the file at the `--output` path; it SHALL NOT modify the Input_File or create temporary, cache, or log files.
4. IF the DQ_Assistant reports an error (invalid arguments, unreadable or oversized Input_File, malformed input, or output write failure), THEN THE CLI SHALL print to standard error a message that may name the Input_File path, Row_Index, and field names, but that contains no field values from any Raw_Record and no Python traceback text.
5. IF an unexpected internal exception occurs, THEN THE CLI SHALL print to standard error a single generic error message with no field values and no Python traceback text, and exit with a non-zero exit code.
6. THE DQ_Assistant SHALL serialize the Report with the Python standard `json` module, so that any control character (U+0000 to U+001F) in a value appears in the Report as a JSON escape sequence and never as a raw byte.
7. THE README SHALL state that values in the Report are not sanitized for spreadsheet formula injection (values starting with `=`, `+`, `-`, or `@`) and that any future CSV or Excel export must escape such values.
8. THE design document SHALL list all five conditions for introducing a real LLM: data minimization (Requirement 10.2), schema validation (Requirement 11), a request timeout, no secrets in code, and an explicit approval step before sending data to an external service.

---

### Requirement 18: Documentation deliverables

**User Story:** As the interviewer, I want the plan, decisions, and AI usage written down in the repository, so that I can review the reasoning as well as the code.

**Why this matters:** The assignment evaluates planning and judgment, not only code. Short, honest documents make tradeoffs and limitations visible. The Prompt_Log shows exactly how AI was used to build the tool and what a human accepted or rejected, which `docs/AI_USAGE.md` only summarizes.

#### Acceptance Criteria

1. THE repository SHALL contain a `docs/spec/` directory holding exactly three Markdown files (requirements, design, and tasks), each with content identical to the corresponding spec document at the time of submission.
2. THE repository SHALL contain a `docs/adr/` directory holding one ADR file per decision for these three decisions: the deterministic-versus-heuristic split, the AI stub boundary (Stub_AI_Suggester behind the AI_Suggester interface, with output checked by the Suggestion_Validator), and the no-mutation guarantee. Each ADR SHALL contain a title, a status, a context section, a decision section, and a consequences section that names at least one tradeoff.
3. THE repository SHALL contain `docs/AI_USAGE.md` with three sections: work delegated to AI, work verified by hand, and AI output rejected or changed. Each section SHALL list at least one concrete item that names the affected file, component, or requirement number. `docs/AI_USAGE.md` SHALL link to the Prompt_Log (`docs/PROMPTS.md`) for the full list of prompts.
4. THE README SHALL contain one section for each of these topics: installing dev dependencies, running the DQ_Assistant, getting a sample file with `--sample`, running the tests, sample input and output, assumptions (including that `manufacturer` is required and that items without a manufacturer use the Unbranded_Sentinel `UNBRANDED`), tradeoffs, known limitations, and next steps.
5. THE README installation, run, and test sections SHALL each give at least one exact shell command, and the run section SHALL show the CLI invocations `python -m dq_assistant <input> [--output FILE] [--no-ai]`, `python -m dq_assistant --sample {json,csv} [--output FILE]`, and `python -m dq_assistant --help`.
6. THE README known-limitations section SHALL state that non-English item descriptions are processed with the same whitespace-based word and character counts as English descriptions, with no translation or language detection, and that this is a known limitation (Requirement 8). It SHALL also state that JSON keys are matched case-sensitively while CSV header names are matched case-insensitively, and that CSV headers that collide after lower-casing keep the last column (Requirement 2 criterion 9). THE README next-steps section SHALL list these four items: decision recording and audit trail, normalized description suggestions, real LLM integration, and an HTTP API, plus cross-system duplicate detection when Requirement 22 is deferred.
7. THE README sample output SHALL be an unedited excerpt of a Report produced by running the DQ_Assistant on one of the repository's demo sample input files (criterion 8), and SHALL name the sample file and command used to produce it.
8. THE repository SHALL contain at least one demo sample Input_File with a `.json` extension and at least one with a `.csv` extension, each no larger than Max_Input_Bytes. These demo samples deliberately contain data quality problems and are separate from the clean Bundled_Samples in Requirement 21. At least one demo sample SHALL contain a record whose `manufacturer` is `UNBRANDED`.
9. WHEN the DQ_Assistant is run with AI enabled (without `--no-ai`) on each demo sample Input_File, THE DQ_Assistant SHALL complete and write a Report, and the combined Reports SHALL contain at least one Review_Candidate for each of the 11 Issue_Types in the Glossary, except `cross_system_duplicate` when Requirement 22 is deferred.
10. THE repository SHALL contain the Prompt_Log `docs/PROMPTS.md` with four sections: completed prompts, planned prompts, the production LLM prompt template, and a link back to `docs/AI_USAGE.md`.
11. THE Prompt_Log completed-prompts section SHALL contain one entry for every prompt used in building the solution: (a) each prompt the user gave in the spec and build sessions, and (b) each prompt the agent sent to an AI sub-agent, including requirements drafting, per-requirement refinement, and consistency fixes. Each entry SHALL record the date, the actor (`human`, `agent`, or `sub-agent`), the purpose, the prompt text or a summary of it, a summary of the output, and the decision (what was accepted, changed, or rejected, with a one-line reason).
12. THE Prompt_Log planned-prompts section SHALL contain one entry for each of these future phases: design, tasks, implementation, code review, and security review. Each entry SHALL record the actor, the purpose, the prompt text or summary, and the expected output, with the date and decision fields set to `planned`. WHEN a planned prompt is used, THE author SHALL move that entry to the completed-prompts section and fill in the date, output summary, and decision.
13. THE Prompt_Log production-template section SHALL contain the future prompt for a real LLM version of the category-mismatch AI_Suggester, with: a system prompt; an input message that contains only the minimal record view (`item_id`, `item_description`, `category`, per Requirement 10 criterion 1) and the Known_Category_List as the allowed answers; the required JSON output schema with the keys from Requirement 11 criterion 1 and the limits from Requirement 11 criteria 2 to 6; and one example expected output that passes those Suggestion_Validator rules. The section SHALL state that every response is treated as untrusted and is validated by the Suggestion_Validator (Requirement 11) before it can become a Review_Candidate.
14. THE Prompt_Log SHALL contain no secrets (API keys, tokens, passwords, connection strings) and no real customer or supplier data. Example records SHALL be synthetic, and any prompt that contained such data SHALL be recorded as a summary with that data removed.

---

### Requirement 19: Tests

**User Story:** As the interviewer, I want tests that prove the edge cases are handled, so that I can trust the behavior without reading every line.

**Why this matters:** Tests are the evidence that the requirements are met. Property-based tests cover input shapes that hand-written examples miss.

#### Acceptance Criteria

1. THE test suite SHALL include, for each of the 11 values in the Issue_Type set (excluding `cross_system_duplicate` only when Requirement 22 is deferred), at least one example-based test whose input produces at least one Review_Candidate with that Issue_Type, and SHALL assert that candidate's `severity`, `confidence`, and `source` values against the values stated in Requirements 5 to 11 and 22.
2. THE test suite SHALL include, for each input error in Requirement 3 (criteria 1 to 8 and 10), at least one example-based test that runs the CLI and asserts exit code 2, a non-empty one-line message on standard error, no Python stack trace in standard error, and no Report written to standard output or to the `--output` path.
3. THE test suite SHALL include property-based tests using `hypothesis`, each run with at least 100 generated examples, for: no mutation of input records (Requirement 15.5), valid candidate schema per Requirement 12 criteria 1 to 5 for arbitrary records, byte-identical Reports from two runs on the same input (Requirement 13.2), and equal Normalized_MPN values for formatting variants of the same part number (Glossary Normalized_MPN / Requirement 9.9).
4. THE property-based tests for arbitrary records SHALL generate record lists of 1 to 20 entries in which each of the seven known record fields is independently absent, JSON `null`, an empty or whitespace-only string, a placeholder string from the Missing_Value definition, the Unbranded_Sentinel in varying letter case and padding, a non-empty string, a number, a boolean, a list, or an object, and SHALL include non-object entries in the list.
5. THE property-based test for Normalized_MPN SHALL generate alphanumeric part numbers of 1 to 20 characters and SHALL assert that changing letter case and inserting spaces, hyphens, dots, slashes, or underscores produces the same Normalized_MPN as the original.
6. THE test suite SHALL include, for each Suggestion_Validator acceptance rule in Requirement 11 criteria 1 to 6, at least one test passing an AI_Suggestion that violates only that rule, and SHALL assert that no `ai_suggestion` candidate is produced and that `ai_suggestions_rejected` increases by exactly 1.
7. THE Suggestion_Validator tests SHALL cover at least these invalid shapes from Requirement 11: a non-mapping value, a wrong Issue_Type, Confidence values `1.5`, `-0.1`, `"0.9"`, and `true`, a category not in the Known_Category_List, an empty explanation, an explanation of 501 characters, a suggested action of 301 characters, an explanation containing "auto-approved", and an explanation lacking candidate wording.
8. THE test suite SHALL include a test in which the AI_Suggester raises an exception for one record and SHALL assert that the CLI exits with exit code 0, `ai_errors` equals 1, and candidates from the other Checks and records are still present in the Report.
9. THE test suite SHALL include a test that processes the JSON and CSV sample input files from Requirement 18.8, both with and without `--no-ai`, and SHALL assert that no explanation, suggested action, or summary text in the resulting Reports contains any forbidden term from Requirement 14.4 (case-insensitive, whole-word match).
10. WHEN `python -m pytest` is run with no network access, THE test suite SHALL complete with zero failed tests and zero errors.
11. THE test suite SHALL use `hypothesis` and `pytest` only as development dependencies, so the DQ_Assistant runtime still uses only the Python 3 standard library (Requirement 1.9).
12. THE test suite SHALL include a test that runs the CLI with `--help` and a test that runs it with `-h`, and SHALL assert exit code 0, empty standard error, and usage text on standard output that names `--output`, `--no-ai`, `--sample`, `UNBRANDED`, and the 5 MiB limit (Requirement 20).
13. THE test suite SHALL include, for each of `--sample json` and `--sample csv`, a test that writes the Bundled_Sample to a new `--output` path, then runs the CLI in Report_Mode on that file both with and without `--no-ai`, and SHALL assert exit code 0 and an empty `candidates` list in each run (Requirement 21 criterion 11). The same test SHALL assert that standard output of a `--sample` run without `--output` equals the bytes of the bundled file.
14. THE test suite SHALL include a test that runs the CLI with both `--sample json` and an Input_File argument, and SHALL assert exit code 2, a usage message on standard error, empty standard output, and no file created (Requirement 21 criterion 6).
15. THE test suite SHALL include a test that runs `--sample csv --output <path>` where `<path>` already exists, and SHALL assert a non-zero exit code, a one-line error on standard error, and that the existing file's bytes are unchanged (Requirement 21 criterion 4).
16. THE test suite SHALL include a test with records whose `manufacturer` is `UNBRANDED`, `unbranded`, and ` Unbranded ` and whose `manufacturer_part_number` is missing, and SHALL assert that none of these records produces a `missing_part_number` candidate or a `missing_required_field` candidate for `manufacturer` (Requirements 5.4, 6.7).
17. THE test suite SHALL include a test with a record whose `manufacturer` is missing, and SHALL assert one `missing_required_field` candidate with `field` `manufacturer`, Severity `medium`, and Confidence `1.0`, and no `missing_part_number` candidate for that record (Requirements 5.4, 6.3).
18. THE test suite SHALL include a test with two records that have different `item_id` values, `manufacturer` `UNBRANDED`, and the same `manufacturer_part_number`, and SHALL assert that no `potential_duplicate` candidate is produced (Requirement 9.11).
19. THE test suite SHALL include a CSV test whose header uses `Item_ID`, ` ITEM_ID `, and other mixed-case or padded field names, and SHALL assert that these columns are read as the known fields (Requirement 2 criteria 3 and 8). It SHALL also include a JSON test asserting that a key `Item_ID` is treated as an unknown field.
20. WHERE Requirement 22 is implemented, THE test suite SHALL include a test with the same `item_id` in two source systems with matching compared fields, and SHALL assert one `cross_system_duplicate` candidate per record with Severity `low`, Confidence `0.6`, Source `heuristic`, and correct `related_item_ids` and `related_row_indexes`, and a property-based test asserting that no record receives both `cross_system_duplicate` and `conflicting_source_values` (Requirement 22 criterion 5).
21. THE test suite SHALL include a test that runs the CLI with `-h` or `--help` together with other arguments — at least an Input_File path that does not exist, plus `--output <path>` and `--sample json` — and SHALL assert exit code 0, usage text on standard output, empty standard error, and that no file is created at the `--output` path and the non-existent Input_File is never opened, so that help takes precedence over all other arguments (Requirement 20 criterion 2).

---

### Requirement 20: Command-line help

**User Story:** As a business user, I want `--help` to tell me how to run the tool and what my file must contain, so that I can prepare a valid file without reading the source code.

**Why this matters:** Help text is the first documentation most users see. Putting the required fields, the `UNBRANDED` default, the size limit, and the exit codes there prevents the most common input mistakes. Python's standard `argparse` module provides this with almost no code.

#### Acceptance Criteria

1. WHEN the user runs `python -m dq_assistant --help` or `python -m dq_assistant -h`, THE CLI SHALL write the usage text to standard output, write zero bytes to standard error, and exit with exit code 0.
2. WHEN `-h` or `--help` appears among the command-line arguments together with any other arguments (for example an Input_File path that does not exist, `--output FILE`, `--no-ai`, or `--sample json`), THE CLI SHALL write the same usage text as criterion 1 to standard output and exit with exit code 0, without validating or acting on the other arguments.
3. WHEN the CLI prints the usage text, THE CLI SHALL open no Input_File, create, modify, or delete no file (including any path given with `--output`), and produce no Report and no Bundled_Sample.
4. THE CLI SHALL include in the usage text the positional Input_File argument and the option names `--output`, `--no-ai`, `--sample`, `-h`, and `--help`, each with a one-line description of its purpose, and SHALL list the two allowed `--sample` values `json` and `csv`.
5. THE CLI SHALL state in the usage text that the Input_File argument and the `--sample` option cannot be used in the same run.
6. THE CLI SHALL state in the usage text the supported input formats (`.json` containing a list of objects, and `.csv` with a header row), and SHALL name the six required fields `item_id`, `item_description`, `manufacturer`, `category`, `unit_of_measure`, and `source_system`, and the one optional field `manufacturer_part_number`.
7. THE CLI SHALL state in the usage text that items without a manufacturer use the value `UNBRANDED` in the `manufacturer` field.
8. THE CLI SHALL state in the usage text the 5 MiB input size limit (Max_Input_Bytes) and the exit codes: `0` when a Report or Bundled_Sample was written, `2` for usage and input errors, and a non-zero code other than `2` (for example `1`) when output cannot be written or an unexpected internal error occurs.
9. THE CLI SHALL state in the usage text that the DQ_Assistant only produces review candidates for a Data_Steward and never modifies the input data.

**Implementation note:** the standard `argparse` module is sufficient. Its default `-h`/`--help` handling meets criteria 1 to 3, and the content of criteria 4 to 9 can go in the argument help strings, the parser description, and the epilog.

**Edge cases covered:** `-h` and `--help` both work; help takes precedence over all other arguments, including invalid ones; help does not touch the file system; help output goes to standard output so it can be piped or paged.

---

### Requirement 21: Offline sample files (`--sample`)

**User Story:** As a business user, I want to get a correct sample file from the tool itself, so that I can copy its format without searching for documentation or downloading anything.

**Why this matters:** A working template is the fastest way to show the expected fields and the `UNBRANDED` default. Bundling the samples inside the package keeps the tool offline (Requirement 17.1), and refusing to overwrite an existing file prevents a user from losing data by mistake.

**Field guide choice:** JSON has no comments, and adding an explanation record to the JSON sample would make the sample itself produce candidates. The simplest clear option, used for both formats, is: the Bundled_Samples contain only item records, and Sample_Mode prints a short Field_Guide to standard error. Standard output stays a clean file that can be redirected. The README and the `--help` text (Requirement 20) explain the same fields and the `UNBRANDED` default.

#### Acceptance Criteria

1. WHEN the user runs `python -m dq_assistant --sample json` or `python -m dq_assistant --sample csv` without `--output`, THE CLI SHALL write to standard output exactly the bytes of the matching Bundled_Sample (`sample.json` for `json`, `sample.csv` for `csv`), with no bytes added, removed, or changed (including line endings), write the Field_Guide to standard error, create no file, and exit with exit code 0.
2. WHEN the user runs the CLI with `--sample json` or `--sample csv` and `--output <path>`, and no file, directory, or symbolic link exists at `<path>`, THE CLI SHALL create a file at `<path>` whose bytes equal the bytes of the matching Bundled_Sample, write nothing to standard output, write the Field_Guide to standard error, and exit with exit code 0.
3. THE CLI SHALL read the Bundled_Samples from data files inside the `dq_assistant` package. In Sample_Mode it SHALL make no network calls and read no other file.
4. IF `--output <path>` is given with `--sample` and a file, directory, or symbolic link already exists at `<path>`, THEN THE CLI SHALL exit with a non-zero exit code, write exactly one line to standard error stating that the output path already exists, write nothing to standard output, and leave the existing entry's bytes, type, and link target unchanged. (Opening the file in exclusive-create mode, Python `open(path, "x")`, satisfies this without a separate existence check.)
5. IF `--output <path>` is given with `--sample` and the path cannot be written for a reason other than criterion 4 (for example the parent directory does not exist or write permission is denied), THEN THE CLI SHALL exit with a non-zero exit code, write exactly one line to standard error naming the output path, write nothing to standard output, and leave no partly written file at `<path>`.
6. IF both `--sample` and an Input_File argument are given, THEN THE CLI SHALL exit with exit code 2, write a usage message to standard error, write nothing to standard output, and neither read the Input_File nor create any file.
7. IF the `--sample` value is not exactly `json` or `csv` (case-sensitive, so `JSON`, `Csv`, and `xml` are rejected), or `--sample` is given with no value, THEN THE CLI SHALL exit with exit code 2, write a usage message to standard error that names `json` and `csv` as the allowed values, write nothing to standard output, and create no file.
8. WHERE `--no-ai` is given with `--sample`, THE CLI SHALL produce standard output, standard error, any `--output` file, and an exit code that are byte-identical to the same command without `--no-ai`.
9. THE Bundled_Samples SHALL each be UTF-8 encoded and contain 3 to 10 synthetic records. Every record SHALL have all seven input record fields: for JSON, all seven keys in each object; for CSV, a header row with the seven lower-case field names and a value for every column in every row. At least one record SHALL have `manufacturer` set to `UNBRANDED` and `manufacturer_part_number` set to an empty string. At least one record SHALL have a `manufacturer` value that is neither a Missing_Value nor the Unbranded_Sentinel, with a `manufacturer_part_number` that is not a Missing_Value. The JSON Bundled_Sample SHALL be a top-level list that contains only record objects.
10. THE Field_Guide SHALL be plain text of 1 to 15 lines that names the six required fields and the one optional field (`manufacturer_part_number`), states that `UNBRANDED` is the `manufacturer` value to use when an item has no manufacturer, and shows a command of the form `python -m dq_assistant <file>`. When `--output` is given, `<file>` SHALL be the `--output` path. Otherwise it SHALL be a file name ending in `.json` or `.csv` to match the `--sample` value.
11. WHEN a Bundled_Sample written by Sample_Mode is processed in Report_Mode, with or without `--no-ai`, THE DQ_Assistant SHALL exit with exit code 0 and produce a Report whose `candidates` list is empty, so the sample shows a clean, valid file.
12. WHEN Sample_Mode runs more than once with the same `--sample` value and the same `--output` argument (or none), THE CLI SHALL write byte-identical standard output, standard error, and `--output` file content each time.

**Edge cases covered:** `--sample` together with an input file (rejected); an existing output file, directory, or symbolic link (refused, unchanged); an unwritable output path (no partial file); an unknown or wrongly cased sample format such as `xml` or `JSON`; `--sample` with no value; `--no-ai` given with `--sample` (no effect); a JSON template that needs an explanation but cannot hold comments (Field_Guide on standard error instead).

---

### Requirement 22: Heuristic — same item in several source systems (lower priority)

**User Story:** As a data steward, I want to know when the same item is kept in several source systems with matching values, so that I can check whether every copy is still needed.

**Why this matters:** Matching copies are not wrong data, but each extra copy is one more record to keep in sync. This is a low-severity, low-confidence hint, so it is the first item to drop if the 2-hour time box runs short.

**Priority:** Lower priority than Requirements 1 to 21. Implement after the core checks pass their tests. If the time box runs out, criterion 7 applies.

#### Acceptance Criteria

1. WHEN a Raw_Record shares its Normalized_Text `item_id` with one or more other Raw_Records whose `source_system` differs from its own (compared as in Requirement 9 criterion 1, so a Missing_Value or Invalid_Type_Value `source_system` counts as different from every non-missing string), and none of the five compared fields (Requirement 9 criterion 2) differs between this record and any of those other records (compared as in Requirement 9 criterion 4, with fields holding an Invalid_Type_Value skipped for that pair), THE Heuristic_Engine SHALL produce exactly one `cross_system_duplicate` candidate for that record, with `field` JSON `null`, Severity `low`, Confidence `0.6`, and Source `heuristic`.
2. THE Heuristic_Engine SHALL set the explanation of each `cross_system_duplicate` candidate to a string that begins with "Candidate issue:" and states that the same `item_id` appears in more than one source system with matching values in all compared fields.
3. THE Heuristic_Engine SHALL set the suggested action of each `cross_system_duplicate` candidate to a step asking the Data_Steward to review whether the record is needed in each source system, and the suggested action SHALL contain no instruction to merge, delete, or overwrite any record (Requirement 9 criterion 12).
4. THE Heuristic_Engine SHALL set `related_item_ids` and `related_row_indexes` on each `cross_system_duplicate` candidate to the trimmed `item_id` values and Row_Index values of every other record in the same Normalized_Text `item_id` group whose `source_system` differs from the candidate's own record, excluding records with the same `source_system`, ordered by ascending Row_Index, with the two lists in matching order (Requirement 9 criterion 10).
5. THE Heuristic_Engine SHALL produce at most one candidate per Raw_Record across the Issue_Types `conflicting_source_values` and `cross_system_duplicate`: a record that differs in at least one compared field from at least one record with a different `source_system` SHALL receive only `conflicting_source_values` (Requirement 9 criterion 2), and all other records that meet criterion 1 SHALL receive only `cross_system_duplicate`.
6. IF a Raw_Record's `item_id` is a Missing_Value or Invalid_Type_Value, THEN THE Heuristic_Engine SHALL produce no `cross_system_duplicate` candidate for that record and SHALL leave it out of every other record's `related_item_ids` and `related_row_indexes` for this check (Requirement 9 criterion 11).
7. WHERE Requirement 22 is deferred because the time box runs out, THE DQ_Assistant SHALL produce zero `cross_system_duplicate` candidates for any input, THE Report summary SHALL still contain the `cross_system_duplicate` key with value 0 in the per-`issue_type` count map (Requirement 16 criterion 4), and THE README next-steps section SHALL list cross-system duplicate detection as a future improvement (Requirement 18 criterion 6).

**Edge cases covered:** the same item replicated to two or three systems with identical values (each record gets one `cross_system_duplicate` candidate); `item_id` differing only in case or surrounding whitespace across systems; one record with a missing `source_system` and one with a named system, identical values otherwise (treated as different systems); compared fields that are Invalid_Type_Value in one copy (skipped for that pair, not counted as a difference); a group where one system copy differs (each record that differs from at least one cross-system copy gets `conflicting_source_values` and no `cross_system_duplicate`); a group that also has a same-system duplicate (a record may get `duplicate_item_id` and `cross_system_duplicate`, Requirement 9 criterion 6).

---

## Edge Case Index

Each assignment edge case and where it is handled:

| Edge case | Requirement(s) | Behavior |
|---|---|---|
| Empty input file | 3.4, 3.7 | Error, exit 2 |
| Missing required fields (including `manufacturer`) | 5.4 | `missing_required_field`, one per field, 0 to 6 per record |
| Item with no manufacturer (`UNBRANDED`, any case) | 4.8, 5.4, 6.7, 9.11 | Present value: no `missing_required_field`, no `missing_part_number`, excluded from part-number grouping |
| Whitespace-only strings | 4.2, 5.4 | Treated as Missing_Value |
| Nulls (JSON `null`, "NULL", "N/A") | 4.2 | Treated as Missing_Value |
| Non-object rows / wrong types | 5.1, 5.6 | `invalid_record` / `invalid_field_type` |
| Mixed-case or padded CSV headers (`Item_ID`, ` ITEM_ID `) | 2.3, 2.8, 3.10 | Matched to known fields; JSON keys stay case-sensitive |
| CSV headers that collide after lower-casing | 2.9 | Last column wins; documented limitation |
| Duplicate `item_id` | 9.1 | `duplicate_item_id` |
| Same item from different source systems | 9.2, 9.5, 9.7, 22 | `conflicting_source_values` if values differ; `cross_system_duplicate` if values match; `potential_duplicate` for same manufacturer + MPN under different IDs |
| Same MPN in different formats | 9.7, 9.9 | `potential_duplicate`, confidence 0.75 |
| Very short descriptions | 8.1 | `weak_description`, confidence 0.8 |
| Useful attributes but wrong category | 10.3 | `category_mismatch_candidate` via AI stub |
| Unsupported UoM | 7.1 | `unsupported_unit_of_measure` |
| Conflicting source-system values | 9.2, 9.3 | `conflicting_source_values` naming differing fields |
| Abbreviation-heavy descriptions | 8.2 | `weak_description`, confidence 0.6 |
| Non-English descriptions | 8.6 | Processed without error; known limitation documented |
| Oversized / non-UTF-8 / unsupported format | 3.2, 3.3, 3.8 | Error, exit 2 |
| Output path equals input path | 1.4 | Error, no write |
| Untrusted / broken AI output | 11 | Dropped and counted |
| `--help` / `-h` | 20.1 | Usage on standard output, exit 0 |
| `--sample` together with an Input_File | 21.6 | Usage error, exit 2 |
| `--sample --output` to an existing file | 21.4 | Refused, existing file unchanged |
| Unknown `--sample` format | 21.7 | Usage error, exit 2 |
| Sample output fed back into the tool | 21.11 | Exit 0, no candidates |

## Open Assumptions (to confirm or adjust in review)

1. **Confirmed (changed in review):** `manufacturer` is required. Items without a manufacturer use the Unbranded_Sentinel `UNBRANDED`, which is a present value. Only `manufacturer_part_number` is optional.
2. **Confirmed:** Zero-record inputs (`[]`, header-only CSV) are errors rather than an empty report, matching the decision that empty input exits non-zero.
3. **Confirmed (changed in review):** The same `item_id` in different source systems with identical values is flagged as `cross_system_duplicate` (low severity, confidence 0.6), as a lower-priority requirement (Requirement 22) that may be deferred to the README next steps.
4. **Confirmed:** Duplicate-family checks emit one candidate per involved record (with related IDs) rather than one per group, so that every candidate maps to exactly one item.
5. **Confirmed:** The 5 MiB input cap is a fixed constant, not a CLI option.
6. Severity and confidence values above are fixed per check and explained in an ADR; they are reasonable defaults, not calibrated against real data.
7. **Confirmed (changed in review):** The Loader removes any byte order mark, trims surrounding whitespace, and lower-cases CSV header names, then matches them exactly against the seven lower-case field names, so `Item_ID` and ` ITEM_ID ` both match `item_id`. JSON keys are matched exactly and case-sensitively. Fully empty CSV lines are skipped and get no Row_Index.
8. If two CSV header names are equal after normalization (for example `Item_ID` and `item_id`), the last column with that name wins (Python `csv.DictReader` behavior). This is a known limitation and is not flagged as a candidate.
9. The Bundled_Samples are small, clean templates that produce no candidates. They are separate from the repository demo samples (Requirement 18.8), which deliberately contain problems so that every Issue_Type appears.
10. Sample_Mode explains the fields through a Field_Guide on standard error, plus the README and `--help`, rather than an explanation record inside the JSON sample.
11. `--sample` refuses to overwrite any existing `--output` path, while Report_Mode replaces an existing `--output` file (Requirement 1 criterion 3), because a Report is generated output and a sample is likely to be edited by the user.
