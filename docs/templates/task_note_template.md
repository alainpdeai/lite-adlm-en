# Task Note Template

> Purpose: Copy the scaffold below into `item.comment` when creating or updating tasks (accessible via the "Notes" button in the frontend).
> Single source of truth: [`config/task-notes.json`](../../config/task-notes.json). This document is the ready-to-use copyable reference.
> Core Principle: **All development activities must be recorded in ADLM so they can be re-calculated, verified, and audited by future reviewers.**

---

## 1. Minimal Scaffold (4 Required Sections)

```text
[Scenario]
(Why does this task exist, and what fact does it anchor? State boundaries in one sentence. E.g.: Confirm that the core module workflow satisfies data contracts as the foundation for downstream verification.)

[Conclusion / Verdict]
(Quantified conclusion with numbers and qualifiers, preserving contextual constraints. E.g.: N/N assertions passed; M known exceptions are documented and non-defective.)
(Narrative "GREEN" claims without verifiable evidence are rejected.)

[Evidence]
(Reproducible commands, script paths, path:line references, hashes, or verbatim server responses. E.g.: python tests/<script>.py -> RESULT: PASS; HTTP status codes and response bodies on error paths.)

[File Anchors]
Primary: tests/<verification_script>
Related: src/<implementation_file>, server.js, data/categories.json
(Primary anchor is stored in item.localDirectory; related paths in item.localDirectories, ordered by evidence chain.)
```

## 2. Complete Scaffold (Recommended for Exam / Acceptance / Contentious Decisions)

```text
[Scenario] ...

[Fixed Inputs]
(Inputs, prerequisite state, and environment required for reproduction to eliminate guesswork. E.g.: Purge existing lists first to avoid polluted baselines.)

[Conclusion / Verdict]
(Quantified verdict + qualifiers. E.g.: N passed / M rejected with 4xx and specific error codes.)

[Boundaries]
(What is omitted, known divergences, differences between spec and implementation. E.g.: Boundary paths not covered by specs are permitted if semantically no-op.)

[Evidence] ...

[Executable Answer]
(Single command to re-derive the verdict, including exit code semantics. E.g.: python tests/<script>.py; exit code 0 = verdict holds.)

[File Anchors]
Primary: ...
Related: ...

[Measurement Record YYYY-MM-DD HH:mm]
(Append a timestamped section after each verification run: verdict, assertion counts, critical values, ID set stability before and after run.)
(E.g.: Verification -> RESULT: PASS (N assertions); list ID set unchanged, no lingering probes.)

[Correction YYYY-MM-DD HH:mm]
(Append when previous conclusions become obsolete or are refuted, explaining why. Never silently overwrite earlier sections.)
```

> `exam` items require an additional **Ground-Truth Triple** in `comment`:
> `truth_source` (spec origin), `tolerance` (numeric tolerance), `truth_hash` (immutable SHA-256 or Git Commit ID).
> Default policy is defined in `config/task-notes.json` -> `examTruth`; see [`docs/task_taxonomy_guide.md`](../task_taxonomy_guide.md) §7.

## 3. Three Invariant Rules

1. **Append, Never Overwrite**: New measurements, corrections, and divergences are always appended as separate sections; historical sections remain immutable.
2. **Numbers Require Context**: Whenever citing numbers, retain qualifications, implicit assumptions, and applicability conditions.
3. **Verifiable Conclusions**: Every verdict must point to a command, script, path, or hash. If evidence is unavailable, explicitly state "currently observed, not verified".

## 4. Division of Responsibility Between Fields

| Information | Storage Field |
|---|---|
| Narrative, verdicts, evidence, correction history | `item.comment` (this template) |
| Primary anchor file | `item.localDirectory` (single path, primary) |
| Related files / URLs | `item.localDirectories` (capped at 20 additional items by `lib/schema.js`) |
| Cross-list traceability | `item.relatesTo[]`: `{listId, itemId, relation}` (arbitrary relation string; extraneous keys stripped) |
| Status transition audit | `item.statusHistory` (server-managed, bounded by `STATUS_HISTORY_LIMIT`) |
| Long-term audit trail | `npm run snapshot` -> `docs/records/` (see [`docs/records/README.md`](../records/README.md)) |

## 5. Architectural Origin

Derived from ADLM's built-in task note specification (`config/task-notes.json`), generalizing standard answers into "conclusions / verdicts" for broad applicability across lists.
