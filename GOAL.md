# Project Development Goal (North Star)

> **This document is the authoritative North Star / Primary Goal for this project, and the template goal document for any AI development project using this system.**
> Any engineering decision must refer back to this Goal before taking action. The criteria here are synchronized with **`SKILL.md` → Project Goal**.

---

## 1. Primary Goal

```
Solidify AI development progress and conclusions into a traceable, structured memory:
tasks written on the board, evidence attached to tasks, and gaps detected automatically —
allowing the next session to resume immediately rather than guessing from scratch.
```

---

## 2. Positioning

| Dimension | Definition |
|---|---|
| **Product Positioning** | A local, deployable task manager and structured memory for AI development teams (human + Agent collaboration). |
| **Core Objective** | Capture task states, decision rationales, evidence paths, and cross-category traceability into queryable structured data. |
| **Background & Problem** | Crucial task details previously scattered across chat logs, scratchpad notes, and disjointed repositories, leaving future sessions unable to reconstruct context. |
| **Delivery Form** | Single-page web board (5 categories: arch/func/test/exam/bug) + REST/Socket.IO APIs + deterministic Python CLI + auto-archiving local JSON files. |
| **Scope Boundaries** | No multi-tenancy, no cloud databases, no bloated enterprise features (Gantt charts, time tracking, approvals), no frontend build chains. |

---

## 3. Decision Criteria (Derived from Goal; Synchronized with SKILL.md)

- **Criterion 1 (Foundations)**: Local filesystem JSON + five standard categories + state machine + `relatesTo` traceability + archiving/backup + zero-gap checks are sufficient to support task/evidence/gap read-write workflows without external storage layers.
- **Criterion 2 (Acceptance)**: A milestone is sufficient if the next session can continue work simply by reviewing the board, and gaps are highlighted automatically by `gaps` / `integrity`.
- **Criterion 3 (Scoping)**: Any new feature request must directly serve the core purpose of "traceable structured memory"; otherwise, classify as "no enhancement needed".

---

## 4. Relationship with Other Documents

| Document | Purpose |
|---|---|
| `config/site.json` → `goal` | One-sentence summary exposed via `/api/config` for API / UI clients |
| `GOAL.md` (this file) | Complete narrative for human collaborators and AI Agents |
| `SKILL.md` → Project Goal | Synchronized mirror of entry guidance and decision criteria |
| `references/reviewer_goal_alignment.md` | Executable review steps converting criteria into decisions |
| `FROZEN.md` | Baseline status records and change logs |
