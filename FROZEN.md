# Project Status Declaration

> **This document is the authoritative record of project lifecycle status changes** (freeze / unfreeze / milestone acceptance / decommission / archive) and acts as the template for projects using this system.
> **Current state: Delivery Baseline v1**: The working tree is a clean deployable system with **no project-specific freeze history yet recorded**. The tables below and §7 are templates to be populated during initialization and ongoing project operations.
> The delivery package omits proprietary evolution history, timelines, runtime instance information, or individual identities.

---

## 0. Current Status (Populate After Initialization)

| Field | Value |
|---|---|
| Project Status | `<Unset / In-Development / Frozen / Archived>` |
| Decided By | `<Role or Account Placeholder>` |
| Effective Timestamp | `<Local Clock YYYY-MM-DD HH:MM ±ZZZZ>` |
| Scope | `<This repository / specific directory or instance scope>` |
| Status Declaration Version | `v1 (Delivery Baseline)` |

> Timestamps must reference the **local machine clock with explicit timezone offset**; do not rely on session-injected timestamps or filesystem mtimes.

---

## 1. Rationale for Status Changes (Template)

A status change must specify three elements before adoption:

- **Rationale**: Objective trigger (Goal attained, milestone verified, external directive);
- **Evidence**: Verifiable test results (commands, return codes, assertion counts, file hashes);
- **Scope**: Explicit list of directories and capabilities affected.

---

## 2. Meaning of Status (Scope)

Taking "Frozen" as an example, five standard rules apply:

1. **No new feature development**: No new features or UI embellishments;
2. **Existing capabilities remain locked**: Core backend engine and frontend views remain intact;
3. **System remains operational**: Data is preserved for runtime inspection;
4. **Methodological assets retained as reusable templates**: `GOAL.md` + `SKILL.md` + `references/reviewer_goal_alignment.md`;
5. **Maintenance modifications permitted** (**§2.5 "Maintenance"**): Documentation corrections, test hygiene, and link repairs that preserve runtime behavior are classified as maintenance.

> §2.5 is referenced across multiple test annotations; this section numbering is preserved for reference stability.

---

## 3. Unfreeze / Modification Conditions

Status changes are considered only when:

- A **verified new requirement** emerges and is determined by `references/reviewer_goal_alignment.md` to directly serve the core North Star Goal;
- Project stakeholders **explicitly direct** a status transition.

---

## 4. Verifiable Status Snapshot (Template)

| Endpoint / Item | Expected | Measured |
|---|---|---|
| `GET /api/health` | `ok:true` | `<Fill in>` |
| `GET /api/integrity` | `dangling=0, duplicates=0` | `<Fill in>` |
| Runtime Data Directory | Contains only seeds and project-specific data | `<Fill in>` |
| Working Tree | `<Clean / List uncommitted items>` | `<Fill in>` |

---

## 5. Approved Changes Post-Declaration (Register Table)

| # | Timestamp (Local Clock + Offset) | Authorization | Changes | Verification | Impact on Status |
|---|---|---|---|---|---|
| -- | -- | -- | `<No records yet>` | -- | -- |

---

## 6. Associated Documents

- `GOAL.md` -- Project North Star and governance truth policy
- `SKILL.md` -- Skill entry point and operational protocols
- `references/reviewer_goal_alignment.md` -- Reusable rules for evaluating proposed tasks against the Goal
- `references/system-guide.md` -- Technical architecture reference
- `install.md` -- Installation and setup guide; §11 covers delivery neutrality

---

## 7. Status Change Log (Empty Template)

> Delivery Baseline v1: **This log is empty**. The section below illustrates the required format.

```text
### 7.N <Change Title> (<Local Clock YYYY-MM-DD HH:MM ±ZZZZ>)

- **Decided By**: <Role or Account Placeholder>
- **Rationale**: <Which condition in §3>
- **Scope**: <Affected directories / capabilities>
- **Actions**: <Enumerate items, categorizing as maintenance vs. development>
- **Verification**: <Commands + outputs + assertion counts / hashes>
- **Conclusion**: <Status impact, Goal evaluation impact>
```
