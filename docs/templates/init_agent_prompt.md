# Initialization Agent Prompt (Reusable Prompt for AI Knowledge Generation)

> Purpose: `npm run init` collects branding and project root info, but **project-specific subdomain dictionaries** require understanding `GOAL.md` and repository artifacts.
> Provide this prompt to an AI / Agent (together with `GOAL.md`, the neutral structural template, and your project file tree) to generate the three configuration files, then run `npm run validate` to verify.
> This codifies the standard workflow: **Investigate mechanisms and boundaries first, persist to disk, then validate**.

---

## 1. Reusable Prompt

```text
Please perform "Project Knowledge Initialization" for the current ADLM instance, generating three configuration files and completing validation.

Input Materials:
- Project GOAL.md (the North Star governing evaluation criteria)
- Structural Template: docs/examples/blank_seed.example.json (neutral JSON reference)
- Project file tree / Key deliverable manifest
- Existing configs: config/site.json, config/taxonomy.json, config/task-notes.json, config/file-anchors.json

Tasks:
1) Taxonomy Dictionary: Reference the neutral template's hierarchy and project Goal to generate L2 subdomains and L3 components tailored to this project.
   Write to config/taxonomy.json, set initialized to true, and remove placeholder flags.
   Note: The L1 categories (arch/func/test/exam/bug) are system invariants; do not alter them.
   Replace generic placeholder subdomains with actual project subdomains.
2) Task Notes: Adopt the standard note structure (Scenario / Fixed Input / Conclusion / Boundary / Executable Answer / Test Archive / Corrections) and redefine the exam truth policy according to project risks.
   Update config/task-notes.json (project-specific sections may be added, but required sections must be preserved).
3) File Anchors: Scan the project root, establish primary anchors and related file lists for key tasks,
   and register them in config/file-anchors.json under anchors (relative path + SHA-256 + byte size + mtime + recommended L2).
4) Audit Trail: Verify that docs/records/ snapshot mechanism functions correctly (npm run snapshot executes cleanly).

Core Principle: All development activities must leave a traceable record in ADLM for future retrospectives.

Delivery Requirements:
- Modify only the three config files mentioned and docs/records/; do not touch runtime code (server.js / lib/ / public/), nor data/categories.json.
- Every assertion must be supported by verifiable evidence (path:line, command output, hashes); narrative "GREEN" claims are unacceptable.
- Append new content as distinct paragraphs/fields without rewriting existing sentences.
- Finally, execute npm run validate and return the raw output.
```

## 2. Pre-flight Checklist (Verify Each Item)

| # | Checklist Item | Rationale |
|---|---|---|
| 1 | L1 categories are fixed; L2/L3 belong in title namespaces, not separate files | ADLM data structure is flat; hierarchy is expressed via `title` suffixes + `subTasks` + `relatesTo` |
| 2 | `config/taxonomy.json` is the sole whitelist source; system has no built-in domain subdomains | Avoid treating third-party domain taxonomies as system constraints |
| 3 | `relatesTo.relation` is an arbitrary string; `sanitizeRelatesTo` retains only `listId`, `itemId`, and `relation` keys | Extra fields are silently stripped; `data/categories.json` relations only govern UI dropdowns |
| 4 | Additional `localDirectories` are capped at 20 items by `slice(0, 20)` | Overflow items are silently dropped; 21 total paths including primary anchor |
| 5 | `item.comment` is a string; unknown fields are tolerated, but known field schemas are enforced | Avoid placing structured data into custom top-level fields; prefer `comment` |
| 6 | `data/shared_lists/` is excluded by `.gitignore`; task data is not committed | Use `docs/records/` snapshots for version-controlled audit trails |
| 7 | Server reads/writes files at runtime; confirm no running instances before editing JSON | Avoid overwriting manual edits with in-memory server state |
| 8 | Use system clock (shell `date` / Node `Date`), not session-injected timestamps | Traceability of hashes and mtime requires real system clocks |
| 9 | Ground-truth policy must match project's highest risk profile | Generic evidence standards may not satisfy project-specific verification |
| 10 | Run `npm run validate` and `npm run snapshot`, returning raw outputs | Ensure standards are enforced by executable code gates |

## 3. Acceptance Criteria

```bash
npm run validate          # Must PASS; placeholder dictionaries / missing sections emit WARN
npm run validate -- --strict   # Strict mode: WARN treated as failure
npm run snapshot          # Creates snapshot in docs/records/<timestamp>/
```

Configuration Responsibilities:

| File | Role | Read By |
|---|---|---|
| `config/taxonomy.json` | Taxonomy dictionary (sole whitelist source) | `scripts/validate_init.js`, human / Agent author |
| `config/task-notes.json` | Note specification and truth policy | `scripts/validate_init.js`, `docs/templates/task_note_template.md` |
| `config/file-anchors.json` | File anchor registry (hashes / timestamps) | `scripts/validate_init.js`, `scripts/init.js` |

> These files are **initialization-time assets** and are not read by `server.js` at runtime -- runtime task data resides in `data/shared_lists/*.json`.
