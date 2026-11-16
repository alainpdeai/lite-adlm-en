# ADLM Hierarchical Task Taxonomy Specification Template

> This document is a **specification template**, not a domain dictionary for any specific project.
> The ADLM deliverable deliberately omits proprietary project names, subdomains, task contents, or historical data; all project-specific elements are populated in `config/taxonomy.json` during initialization.
> Practical implementation steps: [`docs/task_taxonomy_guide.md`](../task_taxonomy_guide.md); machine-readable source of truth: `config/taxonomy.json`.

---

## 1. System Invariants: L1 Five Fixed Lists

| listId | Name | Description |
|---|---|---|
| `arch` | Architecture & Design | Architecture designs, module boundaries, technical selections, interface contracts |
| `func` | Core Features | Business features, interface implementations, core code modules |
| `test` | Testing & QA | Unit, integration, and regression verification tasks |
| `exam` | Benchmarks & Acceptance | Reusable benchmark scenarios, acceptance baselines, and ground truths |
| `bug` | Bug Tracking | Defects discovered via static analysis, code reviews, or runtime testing |

**Rule**: `arch / func / test / exam / bug` are defined by `data/categories.json` as permanent system invariants; all `l1` entries in `config/taxonomy.json` are marked with `fixed: true`. L1 determines physical files at `data/shared_lists/<listId>.json`.

---

## 2. Extensible Layers: L2 / L3 Project-Defined

| Level | Concept | Question Answered | Governed By |
|---|---|---|---|
| **L2** | Business Subdomain | Which technical subsystem does this task belong to? | Written to `config/taxonomy.json` (`l2` whitelist) **at initialization** |
| **L3** | Atomic Component | Which algorithm / module / micro-unit does it act upon? | Same as above; `l3.parent` must reference a registered L2; on-demand |

**Rules**:
- L2/L3 are **not** new list files; they are postfix namespaces written in task titles.
- The system has no hardcoded domain subdomains. Shipped L2 entries are neutral placeholders (`placeholder: true`, `initialized: false`).
- Hierarchy is three-dimensional: `title` namespace + `subTasks` nesting + `relatesTo` links.

---

## 3. Namespace Syntax

```text
<Task Title>[Kind:Domain]              # 2-Tier: L1 Category + L2 Subdomain
<Task Title>[Kind:Domain:Component]   # 3-Tier: Plus L3 Component
```

- `Kind` ∈ `arch|func|test|exam|bug`, matching the parent list;
- `Domain` must exist in `config/taxonomy.json` -> `l2`;
- `Component` is optional; if present, its `parent` must point to the specified L2;
- Legacy prefix formats (`[Kind:Domain] <Title>`) are backward-compatible, though postfix is recommended.

**House Rules**:
1. **L3 is optional**: Omitting L3 defaults to inheriting the parent L2;
2. **Threshold**: Do not enforce L3 until an L2 accumulates roughly 10 tasks;
3. **Aggregation Limit**: High-level views aggregate up to L2; L3 acts as badges and search terms;
4. **No 4th tier**: Four-part namespaces (`[Kind:Domain:Comp:Sub]`) are prohibited.

---

## 4. JSON Schema Mapping

| Dimension | Schema Location |
|---|---|
| L1 | `data/shared_lists/<listId>.json` file |
| L2 | `:Domain` in `item.title` |
| L3 | `:Component` in `item.title` (optional) |
| Module-Unit Hierarchy | `item.subTasks[]` (recursive) |
| Traceability | `item.relatesTo[]`: `{listId, itemId, relation}` |
| File Anchors | `item.localDirectory` (primary) + `item.localDirectories` (additional) |
| Notes / Evidence / Truth | `item.comment` (string) |

`relatesTo.relation` accepts arbitrary strings, but `sanitizeRelatesTo` retains only `listId`, `itemId`, and `relation`; `sanitizeLocalDirectories` enforces `slice(0, 20)`.

---

## 5. Physical Directory Soft Mapping (Optional)

Projects may define "L2 -> Directory Prefix" hints in `config/taxonomy.json` (`l2[].pathPrefix`) and `config/file-anchors.json`. The system does not enforce strict 1:1 filename isomorphisms.

---

## 6. Exam Ground-Truth Gate (The Truth Triple)

Items in `exam` must carry the following keys in `comment`:

| Key | Meaning |
|---|---|
| `truth_source` | Ground-truth source (specification text, evidence path, baseline file) |
| `tolerance` | Numeric tolerance or equality comparator |
| `truth_hash` | Immutable hash of evidence (SHA-256 or Git Commit ID) |

**Design Principle**: `exam` holds truths, thresholds, and hashes; `test` holds assertions and execution logic. Tests reference exams via `compares-to` instead of hardcoding constants.

---

## 7. Dual Validation Tracks

| Track | Tool | Scope |
|---|---|---|
| Specification Track | `npm run validate` (`scripts/validate_init.js`, read-only) | L1 invariants, L2/L3 whitelist, namespaces, required note sections, truth triples, anchor hash drift, dangling edges |
| Runtime Track | `GET /api/integrity` | `dangling = 0`, `duplicates = 0` |

`npm run validate -- --strict` treats warnings as errors for release certification.

---

## 8. Immutability & Audit Trail

- Once initialized (`initialized: true`), changes to L2/L3 must be audited;
- Task notes follow "append, never overwrite";
- Runtime data in `data/shared_lists/` and `data/archive/` is excluded by `.gitignore`; use `npm run snapshot` to generate versioned snapshots under `docs/records/`.
