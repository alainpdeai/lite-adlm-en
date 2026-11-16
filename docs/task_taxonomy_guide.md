# ADLM Hierarchical Task Taxonomy Implementation Guide

> Scope: You have completed ADLM initialization according to `install.md` (dependencies installed, `config/site.json` renamed, server started once).
> This guide addresses three things:
> 1. Explains the three-tier task taxonomy model in ADLM;
> 2. Explains how to **purge** legacy or demo task data from target instances;
> 3. Guides you to **rebuild a clean hierarchical task JSON structure** for your own project.
>
> Accompanying specification: [`docs/references/taxonomy_specification_template.md`](./references/taxonomy_specification_template.md) (neutral specification template without proprietary project content). This guide is the hands-on implementation companion.
>
> **Neutrality of the Deliverable**: ADLM contains no proprietary project names, domain subdomains, task contents, or historical data. All project-specific definitions are written to `config/taxonomy.json` during initialization.

---

## 0. One-Sentence Mental Model

ADLM separates a task's **lifecycle phase** and **technical subsystem** into two layers of tags, using **nested subtasks** to represent the module-to-micro-unit hierarchy:

- **L1 (Level 1) = Five Fixed Lists**: `arch` / `func` / `test` / `exam` / `bug`. These are ADLM's 5 shared lists (stored in `data/shared_lists/arch.json`, etc.), which are **system invariants -- strictly and permanently 5**.
- **L2 (Level 2) = Business Subdomains**: Technical architecture boundaries defined by `config/taxonomy.json` as a **project-specific controlled allowlist** (e.g. `core-arch`, `feature`, `unit` in the placeholder dictionary). Determines board swimlanes.
- **L3 (Level 3) = Atomic Components**: Fine-grained algorithms or module units, **activated on-demand across project stages**, inheriting from their parent Level 2 by default.

> Key takeaway: **L2 and L3 are not separate lists or files; they are suffix namespaces written in task titles** (`[func:feature:jwt]`). ADLM's data structure is flat -- hierarchy is expressed across three dimensions: "title namespace + subTasks nesting + relatesTo links".

---

## 1. Three-Tier Taxonomy Model (Core Concepts)

| Level | Concept | Question Answered | Change Constraint | Board Presentation |
|---|---|---|---|---|
| **L1** | Fixed Business List | Which core phase of the software lifecycle does this task belong to? | **Strictly Fixed** (only 5) | 5 Main Boards / Category Tabs |
| **L2** | Business Subdomain | Which technical subsystem does this task belong to? | **Strictly Controlled** (governed by `config/taxonomy.json`) | Main filtering axis & swimlanes |
| **L3** | Atomic Component | Which specific algorithm, module, or unit does this task act upon? | **Activated On-Demand** | Card prefix badges, searchable |

> **L2 has no hardcoded count**. The count, naming, and list mapping of subdomains are governed entirely by `config/taxonomy.json`; the 10 L2 subdomains shipped with the repository are neutral placeholders (`placeholder: true`) for generic software projects.

### 1.1 Project Taxonomy (Single Source of Truth)

`config/taxonomy.json` is the machine-readable dictionary generated during initialization and serves as the single whitelist source for L2/L3. The `l1` categories are marked with `fixed: true` and cannot be modified; each `l2` entry carries `listId`, `pathPrefix`, and a `placeholder` flag; each `l3` entry's `parent` must point to a registered L2.

The repository ships with an uninitialized generic placeholder dictionary (`initialized: false`). During initialization, you replace it with your project's subdomains via one of three paths:

1. Interactive `npm run init`: input L2 subdomains formatted as `arch:id=Name,func:id=Name,…`; the script replaces placeholders and sets `initialized: true`;
2. Agent-driven: follow [`docs/templates/init_agent_prompt.md`](./templates/init_agent_prompt.md) to feed `GOAL.md` and your file tree to an AI/Agent to generate the dictionary;
3. Manual editing of `config/taxonomy.json`.

`npm run validate` checks L1 invariants, L2 mappings, L3 parent relationships, and namespaces in task titles; placeholder dictionaries emit warnings without breaking builds.

---

## 2. Namespace Syntax `[Kind: Domain (: Component)]`

To avoid cluttering card titles in the UI, ADLM uses **postfix strong-typed namespaces** (backward-compatible with historical prefix formats):

- **Standard 2-tier**: `<Module> boundary definition and data contracts[arch:core-arch]`
- **Extended 3-tier**: `Implement authentication middleware[func:feature:jwt]`
- **Exam ground-truth**: `<Standard Scenario> baseline[exam:scenario]`

**House Rules:**

1. **L3 is strictly optional**: When L3 is omitted (e.g. `[func:feature]`), the task inherits its parent L2 subdomain;
2. **Activation threshold**: Do not enforce L3 until an L2 subdomain accumulates approximately 10 tasks, avoiding sparse labels;
3. **Board aggregation limit**: High-level views and swimlanes aggregate only up to L2 to prevent visual fragmentation;
4. **No 4th tier**: Four-part namespaces (`[Kind:Domain:Comp:Sub]`) are strictly forbidden; fine-grained details (incident IDs, function names) belong in titles or `comment`.

---

## 3. ADLM JSON Data Structures

### 3.1 List File Format

Each L1 list is an independent JSON file at `data/shared_lists/<listId>.json`:

```json
{
  "listId": "func",
  "listName": "Core Features",
  "category": "function",
  "owner": "user_admin",
  "createdAt": "<ISO-8601>",
  "items": [ /* Array of task items, see §3.2 */ ],
  "rev": 1,
  "updatedAt": "<ISO-8601>",
  "updatedBy": "user_admin"
}
```

### 3.2 Task Item Schema

Each object inside the `items` array represents a task item:

| Field | Type | Description |
|---|---|---|
| `itemId` | string | Globally unique identifier (recommended: `task_<prefix>_<number>`, e.g., `task_func_200`) |
| `title` | string | **Title with namespace**: `<Module>: Implementation[func:feature]` |
| `isDone` | bool | Completion flag (synchronized with `status`) |
| `status` | string | `open` / `in-progress` / `blocked` / `verified` / `done` |
| `priority` | string | `Low` / `Medium` / `High` |
| `assignedTo` | string | Assignee username |
| `localDirectory` / `localDirectories` | string / string[] | Linked codebase paths (soft-validated, see §6 directory mapping) |
| `comment` | string | Details; **exam ground-truth metadata is recorded here** (HTML or plaintext) |
| `subTasks` | array | **Hierarchical nesting**: Identical structure to item, holding child tasks |
| `relatesTo` | array | **Cross-list traceability**: `{ "listId": "exam", "itemId": "task_exam_400", "relation": "compares-to" }` |

Audit fields (`statusHistory`, `createdBy/At`, `closedBy/At`) are maintained automatically at runtime. During manual seeding, leave them as empty strings or `null`.

### 3.3 Mapping Concept to JSON

| Dimension | JSON Implementation | Example |
|---|---|---|
| L1 List | `data/shared_lists/<listId>.json` file | `arch.json`, `func.json`, `test.json`, `exam.json`, `bug.json` |
| L2 Subdomain | Task `title` postfix `:Domain` | `...[func:feature]` |
| L3 Component | Task `title` postfix `:Component` (optional) | `...[func:feature:jwt]` |
| Module-Unit Hierarchy | Nested `item.subTasks[]` | Parent `task_func_200` containing `task_func_201` |
| Cross-list Traceability | `item.relatesTo[]` (`derives-from` / `verifies` / `compares-to` / `blocks` / `related`) | Test `verifies` function, `exam` referenced by `compares-to` |
| Exam Truth Anchors | `truth_source` / `tolerance` / `truth_hash` in `exam` item's `comment` | See §7 |

---

## 4. Step 1: Purging Legacy / Demo Data (3-Step Safety Gate)

The ADLM deliverable package contains no runtime tasks (`data/` only contains `categories.json` seed; runtime lists are excluded by `.gitignore`). If deploying against a pre-existing instance with historical data, purge legacy data before registering project tasks.

### 4.1 3-Item Safety Gate

| Check | Requirement | Pass Criteria |
|---|---|---|
| **1. Knowledge Extraction** | Valuable engineering findings from old tasks are extracted to `GOAL.md` / `SKILL.md` / `references/system-guide.md` | Architect sign-off |
| **2. Dependency Audit** | New tasks do not reference deprecated legacy item IDs in `relatesTo` | 0 dangling references |
| **3. Authorized Purge** | Perform atomic purge once authorized | See §4.2 |

### 4.2 Execution: Two Purge Methods

**Method A -- Delete files and let system bootstrap empty lists from `categories.json` (Recommended):**

```bash
# Execute while the service is stopped
cd ADLM
rm -f data/shared_lists/arch.json data/shared_lists/func.json \
      data/shared_lists/test.json data/shared_lists/exam.json \
      data/shared_lists/bug.json
# Restart via npm start -> provisions 5 empty lists according to categories.json
```

**Method B -- Retain list files and clear `items` array:**
Set `items: []` in each `*.json` file and restart.

> ⚠️ **Never invoke archive for purges**: Perform physical deletion to prevent generating orphaned archive files.
> ⚠️ Run `npm run snapshot` before purging to preserve an auditable baseline.

### 4.3 Validation

```bash
curl http://localhost:3000/api/integrity
# Expected: counts: { "dangling": 0, "duplicates": 0 }
```

---

## 5. Step 2: Constructing JSON for Your Project

A neutral structural reference is provided at:

📄 [`docs/examples/blank_seed.example.json`](./examples/blank_seed.example.json)

It demonstrates all 5 lists with minimal representative tasks:

- `arch`: Architecture task + `relatesTo` links (`derives-from` / `related`);
- `func`: Parent task + `subTasks` nesting, with L3 component in title;
- `test`: `verifies` feature task, `compares-to` exam truth (no hardcoded truth in tests);
- `exam`: Truth metadata (`truth_source` / `tolerance` / `truth_hash`) in `comment`;
- `bug`: Standalone bug item (relationships optional).

### 5.1 Deployment Steps

1. Inspect `blank_seed.example.json` to understand list objects;
2. Initialize project taxonomy (§1.1), then write JSON files into `data/shared_lists/<listId>.json`;
3. Replace `<angle_bracket_placeholders>` with your project's data;
4. Use semantic IDs: `task_arch_100`, `task_func_200`, `task_exam_400`;
5. Restart the server and verify the task tree at `http://localhost:3000`.

---

## 6. Physical Directory Mapping (Soft Hint)

Rather than enforcing rigid 1:1 file isomorphisms, ADLM uses soft prefix validation defined in `config/taxonomy.json` (`l2[].pathPrefix`) and `config/file-anchors.json`:

| Task Category | Physical Directory Prefix | Typical Artifact |
|---|---|---|
| `[arch:*]` | `docs/` | Architecture specs & designs |
| `[func:*]` | `src/` | Source code implementation |
| `[test:*]` | `tests/` | Unit & acceptance test scripts |
| `[exam:*]` | `docs/records/` | Baseline evidence & standard scenarios |
| `[bug:*]` | `src/` or `tests/` | Defect fixes and regressions |

Paths in `item.localDirectories` should be relative to `projectRoot` rather than absolute machine paths.

---

## 7. Exam Truth Verification Gate

Any item written to the `exam` list must include three metadata keys in its `comment` field:

1. `truth_source`: Path or reference to original specification or evidence;
2. `tolerance`: Numeric or string equality tolerance (`in (None, "")` for empty checks);
3. `truth_hash`: Immutable hash (SHA-256 or commit ID) to prevent silent drift.

Example:

```text
truth_source: <spec document or baseline path>
tolerance: <numeric tolerance>
truth_hash: sha256:<SHA-256 of baseline artifact>
```

> Design principle: **exam holds ground truths and hashes; test holds execution and assertion logic**. Tests reference exams via `compares-to` rather than hardcoding constants.

---

## 8. Validation and Regression

### 8.1 Specification Checks

Configured in `config/taxonomy.json` / `config/task-notes.json`:

- **L1 & L2 Whitelist**: Unrecognized namespaces are rejected;
- **L3 Recommendations**: Unregistered L3 triggers warnings in dev, errors in `--strict` mode;
- **Exam Truth Triple**: `truth_source` / `tolerance` / `truth_hash` required;
- **Dangling Edges**: References to non-existent `itemId` are flagged.

### 8.2 Runtime Self-Check

```bash
curl http://localhost:3000/api/integrity
# Expected: counts: { "dangling": 0, "duplicates": 0 }
```

### 8.3 CLI Validator

`npm run validate` (`scripts/validate_init.js`) executes these checks in read-only mode:

```bash
npm run validate            # FAIL => exit code 1; placeholders emit WARN
npm run validate -- --strict # Strict mode: warnings treated as failure
```

---

## 9. Relationship Between Documents and Configurations

| Document | Role | When to Read |
|---|---|---|
| `docs/task_taxonomy_guide.md` | Implementation guide: concepts, schemas, purge/rebuild steps | Getting started and operational tasks |
| [`docs/references/taxonomy_specification_template.md`](./references/taxonomy_specification_template.md) | Specification template: rules, constraints, gates | Extending rules or conducting audits |
| `config/taxonomy.json` | Project whitelist source of truth (machine-readable) | Writing task titles, running validators |
| `config/task-notes.json` + [`docs/templates/task_note_template.md`](./templates/task_note_template.md) | Task note standards and templates | Writing or updating task notes |
| `config/file-anchors.json` + [`docs/records/README.md`](./records/README.md) | File anchor registry and snapshots | Audits and milestone retrospectives |
| [`docs/examples/blank_seed.example.json`](./examples/blank_seed.example.json) | Neutral structural reference | Rebuilding initial task trees |
