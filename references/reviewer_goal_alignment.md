# Reviewer Rule: Evaluating Proposed Tasks Against Goal (P3 / Enhancements)

> This document is the **executable operational procedure** for the `SKILL.md` -> "Project Goal" **evaluation criteria**, transforming "all decisions must re-align with the Goal before implementation" into a structured reviewer workflow.
>
> **Scope**: Any proposed item labeled "enhancement / presentation / optimization / future / P3" must pass this gate before implementation; also applicable when users ask "Does X still align with the Goal / is it worth keeping?".

---

## 1. Triggers (When to Activate This Rule)

Activated when any of the following conditions occur:

- Encountering an `open` / `blocked` task whose value proposition is described as "enhancement / charts / virtual scroll / search UI / grouped views / optimization / future possibility / P3";
- A user asks "Does X still align with the Goal / is it worth keeping / should we implement it?";
- Performing a milestone batch audit of all `P3` or "enhancement" items.

**Non-triggers**: Direct bug fixes or maintenance of core backend foundations already designated for retention in the Goal (hard gates, incremental sync, item-level writes, integrity linting).

---

## 2. Inputs

- The project's **`GOAL.md`** (North Star + authoritative criteria);
- Proposed task item (JSON object from any list: `arch`, `func`, `test`, `exam`).

---

## 3. Reviewer Procedure

### Step 1 -- Load the Goal
Read the **core purpose** and **three evaluation criteria** from `GOAL.md`:
1. Core backend capabilities (hard gate, incremental sync, item-level writes, integrity linting) are in place, serving as the foundation for the "Structured Memory";
2. The frontend is evaluated on "readability, writability, and immediate visibility" -- **not gratuitous visual enhancements**;
3. Any new requirement must re-align with the core purpose: Does it serve "development progress / unexpected tasks -> structured memory"? If not, classify as "no further enhancement needed".

### Step 2 -- Classify Task into Four Types
| Type | Meaning | Typical Examples |
|---|---|---|
| **A. Backend Foundation** | Read/write & security foundation for structured memory | Hard gates, incremental sync, item-level writes, integrity linting |
| **B. Frontend UI Enhancement** | Making the UI "prettier" rather than "more readable/writable" | Drag-and-drop boards, virtual scrolling, charts, grouped views, global search UI |
| **C. Speculative Framework** | Frameworks for "hypothetical / future scenarios" | Schema versioning/migration, idempotency keys (guarding hypothetical retries) |
| **D. Direct Core Service** | Directly anchors progress or unexpected tasks into structured memory | New lists, item-level write endpoints, cross-category traceability, conflict diff preservation |

### Step 3 -- Verdict
- **Retain & Implement**: Only if the task belongs to **D**, or belongs to **A and is not yet implemented**.
- **Analyze & Defer (Close)**: Belongs to **B** or **C** (no immediate plan or empirical evidence) -- this matches what the Goal explicitly excludes.

### Step 4 -- Boundary Condition Handling
If an item has a **plausible future trigger condition** (e.g., idempotency keys are only needed if duplicate tasks actually occur), mark upon closing: **"Reopen if empirical evidence emerges"**, preserving an auditable path.

### Step 5 -- Execution & Closure
> ⚠️ Rule: **Stop the instance** before modifying JSON on disk; **keep the instance running** when committing (pre-commit gate connects to `http://localhost:3000`).

1. Stop running instance (`Stop-Process -Id <pid>`);
2. Edit target JSON item:
   - `isDone: true`
   - `status: "done"`
   - `statusHistory`: append `{ from: <previous_status>, to: "done", at: "<YYYY-MM-DD HH:MM>", by: "user_admin" }`
   - `closedBy: "admin"`, `closedById: "user_admin"`, `closedAt: "<YYYY-MM-DD HH:MM>"`
   - `comment`: append `[Closed: Analyzed & Deferred]` + rationale mapping to the Goal;
3. **Restart instance** -> query `GET /api/integrity` to confirm `ok:true / dangling=0 / duplicates=0`;
4. Verify no remaining `open`/`blocked` P3 items in target list;
5. Keep instance online and commit.

### Step 6 -- Audit Record
Append a summary to the audit record in `docs/records/` documenting classified items, actions taken, and integrity results.

---

## 4. Verification of This Rule

- Closed items in JSON have all required fields populated: `isDone`/`status`/`statusHistory`/`closedBy`/`closedById`/`closedAt`;
- `GET /api/integrity` returns `ok:true`, `dangling:0`, `duplicates:0`;
- If the goal is "zero P3", the count of `open`/`blocked` tasks containing `P3` in their title must reach zero.

---

## 5. Reusability

- This rule decouples from any specific codebase: it relies solely on `GOAL.md` and its three evaluation criteria. When bootstrapping a new AI project, adopting this workflow requires only adapting the project Goal.
