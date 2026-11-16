# LiteTask PM — System Guide

This is the reference documentation for the LiteTask-based software project management system located at `<REPO_ROOT>`. Read this document when you need exact field shapes, API contracts, or rules for direct data file editing.

## 0. Capability Index — Where Every Capability Lives

This guide has exceeded 110 KB and forty sections, which is precisely why an index is necessary: §23 records an incident where "a capability was assumed missing when it had already been implemented and documented all along." Please read this table first.

One line per capability: File, Section, and an Anchor — a distinctive string located **inside that section**. `scripts/check_doc_index.py` re-derives every row (file exists, heading occurs exactly once, anchor remains between that heading and the next), while `tests/grade_doc_index.py` fails the grading suite if any row breaks. An unverified index becomes a new source of misdirection, and the purpose of this index is to prevent exactly that.

Rows are keyed by heading **text**, never by section number: in this document §31 and §32 each occur twice. The mechanics and intentionally unmeasured parts are detailed in §37.

| Capability | File | Section | Anchor |
| --- | --- | --- | --- |
| Service Startup and Shutdown | references/system-guide.md | §2 Startup and Shutdown | `node server.js` |
| Categories (Fixed, Auto-provisioned) | references/system-guide.md | §3 Categories (Fixed, Auto-provisioned) | `data/categories.json` |
| Relation Vocabulary | references/system-guide.md | §4 Relation Vocabulary (categories.json -> relations) | `relations` |
| Data Model and Item Schema Validation | references/system-guide.md | §5 Data Model | `data/shared_lists/<listId>.json` |
| API Contract | references/system-guide.md | §6 API Contract | `http://localhost:3000` |
| Iron Rule of Direct JSON Editing (Stop -> Edit -> Restart) | references/system-guide.md | §7 Direct JSON Editing (Agent Path) | `file-changed` |
| Data File Editing Iron Rule (Skill Version) | SKILL.md | §Path B —— Direct JSON Editing (Batch / Structural Repairs) | `Stop Instance` |
| Agent Workflow | references/system-guide.md | §8 Recommended Agent Workflow | `python scripts/litetask_cli.py list` |
| Traceability UX and Relation Graph | references/system-guide.md | §9 Traceability UX (Cross-category Linking) — Built 2026-10-27 | `relatesTo` |
| Password Storage (scrypt) | references/system-guide.md | §10 Password Storage (B2 — scrypt) | `data/users.json` |
| Concurrent Write Protection (B3) | references/system-guide.md | §11 Concurrent Write Protection (B3) | `baseRev` |
| B3 Grader Fix (Out-of-Lock Existence Check) | references/system-guide.md | §31 PUT /api/lists/:id — Removing Out-of-Lock Existence Check | `grade_b3_concurrency_core.py` |
| Archiving (A1) and Hiding Completed (F5) | references/system-guide.md | §12 Hiding Completed (F5) and Archiving (A1) | `archive-preview` |
| Unarchive Recovery | SKILL.md | §Unarchive: Recovering Archived Items (P1) | `unarchive` |
| Workflow Status Flow (F1) | references/system-guide.md | §13 Workflow Status Flow (F1) | `statusHistory` |
| Multi-path Source Linking (F2) | references/system-guide.md | §14 Multi-path Source Linking (F2) | `localDirectories` |
| Reverse Traceability and Gap Analysis (F3) | references/system-guide.md | §15 Reverse Traceability Query and Gap Analysis (F3) | `depth` |
| Startup Backup | references/system-guide.md | §16 Startup Backup | `stamp` |
| Board Columns and Creator Field | references/system-guide.md | §17 Board Columns: Assignee Removed, Creator = AI Agent | `createdByAgent` |
| Save Conflict Diff and Force Overwrite | references/system-guide.md | §18 Save Conflict Diff and Force Overwrite (B3 Follow-up) | `PUT /api/lists/:id` |
| Traceability Matrix | references/system-guide.md | §19 Traceability Matrix — Current State and House Rules | `litetask_cli.py gaps` |
| Removing Erroneous Relation Edges | references/system-guide.md | §20 Removing Incorrect Relation Edges (unlink) | `unlink` |
| Benchmark Suite (exam) | references/system-guide.md | §21 Fourth Category: Benchmarks & Acceptance (exam) | `Benchmarks & Acceptance` |
| Browser Verification (M1) | references/system-guide.md | §22 M1: Making Mandatory Browser Checks Reusable | `public/index.html` |
| Agent Visibility and Pending Queue | references/system-guide.md | §23 Can the Agent See Tasks You Add in the Browser? | `litetask_cli.py pending` |
| Legacy File Cleanup (M2) | references/system-guide.md | §24 M2 Executed: Legacy File Cleanup | `legacy` |
| Exam 01 | references/system-guide.md | §25 Exam 01 Closed: Probe and Grader Are Separate Files | `exam_case_01_grade.py` |
| Grading System | references/system-guide.md | §26 Graders: Every Verification Item Can Be Re-derived | `run_grade_checks.py` |
| Graders (Skill Version) | SKILL.md | §Graders (Re-derivable Verification Items) | `grade_` |
| Destructive Confirmation Hard Gate (Skill Version) | SKILL.md | §Destructive Operations Require confirm=true | `confirm=true` |
| Item-level Writes / Incremental Sync / Integrity Lint (Skill Version) | SKILL.md | §Item-level Writes, Incremental Sync, and Integrity Linting (P3) | `litetask_cli.py item` |
| Exam 02 | references/system-guide.md | §27 Exam 02: Four Outlets for a Conflict, and Where Scenarios Live | `exam_case_02_grade.py` |
| Auto-archive Threshold and Protected Lists | references/system-guide.md | §28 Auto-archive Has Protected Lists, Threshold Is Declarative | `autoArchiveSweep` |
| Archived Work Remains in Graph | references/system-guide.md | §29 Archived Work Remains in the Graph | `buildLinkGraph()` |
| Exam 03 | references/system-guide.md | §30 Exam 03 — Archiving Moves Storage, Not Evidence | `exam_case_03_grade.py` |
| Idempotent Writes and Zero Side Effects | references/system-guide.md | §31 Idempotent Writes, and Zero-Side-Effect Grading (Testing Architecture P1) | `contentRev` |
| Pre-commit Gate | references/system-guide.md | §32 Pre-commit Gate (Continuous Integration P1) | `python tests/run_grade_checks.py --fast` |
| Local Passwordless Mode | references/system-guide.md | §32 Local Mode Passwordless (2026-10-29) | `LITETASK_DEV_LOGIN` |
| Honest Retirement of a Check | references/system-guide.md | §33 Honestly Retiring a Check (2026-10-29) | `retired` |
| Background Process Ownership | references/system-guide.md | §34 Who Owns a Background Process (2026-10-29) | `litetask_ensure.ps1` |
| Audit, Mode Banner, and Confirmation (Security Boundary P2) | references/system-guide.md | §35 Security Boundary P2 — Audit, Mode Banner, Destructive Second Confirmation | `writeAudit` |
| 1k / 5k Scale Baseline (Capacity and Performance P2) | references/system-guide.md | §36 Capacity P2 — 1k / 5k Baseline, and Where the Performance Inflection Point Is Not | `scale_probe.py` |
| Index Verification and Stale Check (Knowledge Entry P2) | references/system-guide.md | §37 Capability Index, and Why It Is Verified Rather Than Trusted | `check_doc_index.py` |
| Stale Snapshot on Reconnect (resync) | references/system-guide.md | §38 Blind Spot of the Iron Rule: Edits Made While Instance Is Stopped (2026-10-30) | `socket.emit('resync')` |
| Destructive Confirmation Hard Gate (confirm=true) | references/system-guide.md | §39 Destructive Confirmation Is Now a Hard Gate (2026-10-31) | `requireConfirm` |
| Incremental Sync (ETag / 304 / Change Event with Actor) | references/system-guide.md | §40 Incremental Sync P3-A — ETag, 304, and an Event Stating Actor | `listsETag` |
| Item-level Write Endpoint (P3-B) | references/system-guide.md | §41 Item-level Write Endpoint P3-B — One Item Without Shipping 32 Others | `itemWrite` |
| Integrity Report (Dangling Edges / Duplicate itemIds) | references/system-guide.md | §42 Integrity Report P3-D+E — Cheap Version, and What It Discovered | `indexAllItemIds` |
| DOM Rendering Baseline Measurement | references/system-guide.md | §43 DOM Rendering Baseline: The Honest Limitation in §36 Has Been Closed | `browser_render_baseline_check.js` |

## 1. What It Is

A Node.js (Express + Socket.IO) single-page task manager, adapted into a multi-category tracker for software projects. There is no database — state resides in JSON files on disk. The server reads lists from disk on every request and watches the directory, so direct file modifications are reflected in real time.

## 2. Startup and Shutdown

```bash
cd <REPO_ROOT>
npm install          # first time only
node server.js       # listens on http://localhost:3000
```

Default credentials: the super administrator configured in `config/site.json` during initialization (persisted as an scrypt hash, transmitted in plaintext over HTTP — **do not** expose publicly). This delivery bundle contains no real credentials.

## 3. Categories (Fixed, Auto-provisioned)

Defined in `data/categories.json`. The server creates missing list files on initial startup; it never overwrites existing lists.

| listId | listName           | category       | Purpose                       |
|--------|--------------------|----------------|-------------------------------|
| `arch` | Architecture & Design | architecture   | System architecture tasks    |
| `func` | Core Features      | function       | Feature development tasks     |
| `test` | Testing & QA       | test           | Testing & verification tasks  |

Ad-hoc lists created via the UI receive numeric IDs (`01`, `02`, ...).

## 4. Relation Vocabulary (categories.json -> relations)

Used inside an item's `relatesTo` array. The direction originates from the item holding the link.

| relation       | Typical Meaning                                   |
|----------------|---------------------------------------------------|
| `derives-from` | A **func** item derives from an **arch** item     |
| `verifies`     | A **test** item verifies a **func** item          |
| `depends-on`   | Current item depends on another item              |
| `blocks`       | Current item blocks another item                  |
| `related`      | Generic link (default when relation is omitted)   |

The `relatesTo` item shape (enforced by server `sanitizeRelatesTo`):

```json
{ "listId": "arch", "itemId": "task_arch_001", "relation": "derives-from" }
```

Entries missing `listId` or `itemId` are discarded; missing `relation` defaults to `"related"`.

## 5. Data Model

### List Files — `data/shared_lists/<listId>.json`

```json
{
  "listId": "func",
  "listName": "Core Features",
  "category": "function",
  "owner": "admin",
  "createdAt": "2026-10-27 21:21",
  "items": [ /* item objects */ ]
}
```

### Item Objects

All fields below exist on top-level items and nested `subTasks`.

| Field            | Type    | Description                                        |
|------------------|---------|----------------------------------------------------|
| `itemId`         | string  | Unique key, e.g. `task_<ms><rand>`                  |
| `title`          | string  | Task title                                         |
| `isDone`         | bool    | Legacy completion flag; true only when `done`      |
| `status`         | string  | `open` \| `in-progress` \| `blocked` \| `verified` \| `done` |
| `statusHistory`  | array   | Recent 20 transitions: `{from,to,at,by}`           |
| `blockedReason`  | string  | Optional reason, displayed next to blocked tasks   |
| `dueDate`        | string  | `YYYY-MM-DD` or `""`                               |
| `priority`       | string  | **Must be exactly** `High` \| `Medium` \| `Low`    |
| `assignedTo`     | string  | Legacy username (no longer displayed — Assignee column removed) |
| `createdBy`      | string  | Username (fallback display when `createdByAgent` is absent) |
| `createdByAgent` | string  | AI Agent that created/owns the task (Creator · AI Agent column) |
| `createdById`    | string  | `user_admin` / `user_1791622363912`                |
| `createdAt`      | string  | `YYYY-MM-DD HH:MM`                                 |
| `closedBy`       | string\|null | Set when closed; cleared when reopened        |
| `closedById`     | string\|null |                                                    |
| `closedAt`       | string\|null |                                                    |
| `localDirectory` | string  | **Primary** source path or URL (first of path list) |
| `localDirectories` | array | **F2**: Additional source paths/URLs (unique, max 20) |
| `comment`        | string  | Rich text HTML (Quill), e.g. `<p>notes</p>`        |
| `subTasks`       | array   | Nested items (same shape)                          |
| `relatesTo`      | array   | `[{listId, itemId, relation}]`                     |

## 6. API Contract

Base URL: `http://localhost:3000`

### Unauthenticated Endpoints

- `POST /api/login` — `{ username, password }` -> `{ token, user }` (Token is `Bearer <token>`).
- `GET /api/categories` -> Returns `categories.json` (categories, relations, statuses, statusFlow).

### Core List Endpoints (Requires Bearer Token)

- `GET /api/lists` -> Array of lists (each carrying `listId`, `listName`, `category`, `rev`, `items`).
- `POST /api/lists` -> Creates a list.
- `PUT /api/lists/:id` — `{ type: "UPDATE_ITEMS", items, baseRev }` -> Saves list items (guarded by `baseRev` optimistic lock, see §11).
- `PUT /api/lists/:id/items/:itemId` — Item-level write (P3-B, see §41).
- `DELETE /api/lists/:id` — Requires `confirm=true` query or body parameter.
- `GET /api/links` — Returns global relation graph (`nodes` + `edges`).
- `GET /api/gaps` — Returns traceability coverage gaps.
- `GET /api/integrity` — Integrity report (dangling edges, duplicate itemIds, see §42).

## 7. Direct JSON Editing (Agent Path)

When modifying data files directly, follow the **Stop Instance -> Edit JSON -> Restart Instance** sequence.

Key rules:
- **Concurrency:** API writes use `baseRev` optimistic locking, per-file queues, and atomic renames. Direct editing bypasses `baseRev`; prefer API/CLI while the service is running, and avoid concurrent manual edits.
- **Validity:** Keep JSON valid and parseable; an extra trailing comma will crash list loading.
- **Case Sensitivity:** `priority` must be `High` / `Medium` / `Low`; `status` must be one of the five configured workflow values.
- **Never delete items** from shared lists; close them using `status = done`.
- **An open browser will stay on a stale snapshot across restarts.** The file watcher only triggers while the process is alive, and the whole point of this sequence is to edit while the instance is stopped — so those edits will never emit `file-changed`. Since 2026-10-30, the server emits a `resync` event to every socket on connection, so surviving pages reload automatically (§38). A hard browser refresh achieves the same.
- For programmatic writes, `scripts/litetask_cli.py` uses atomic `os.replace` with retries to handle transient locks from Windows antivirus and file indexing.

## 8. Recommended Agent Workflow

1. At session start: `python scripts/litetask_cli.py list` to inspect pending work.
2. Starting a planned task: Ensure it exists in the correct category; if missing, add it with `add` (attach `localDirectory`, append additional paths with `--extra-dir`, pass `--agent`, record findings in `comment`), then transition with `status --status in-progress`.
3. When blocked: `status --status blocked --reason "<reason>"`; resume with `--status in-progress` (or `open`). When verified, use `--status verified`; when complete, use `--status done`.
4. Discovering new tasks/bugs: `add` to the matching category; if it belongs to an existing task, nest it with `--parent`.
5. Establish cross-category links with `--relates` (`derives-from` / `verifies` / ...) to keep the Architecture -> Feature -> Test chain fully traceable.

## 9. Traceability UX (Cross-category Linking) — Built 2026-10-27

Relations exist as structured `relatesTo` fields on each item/subtask: `[{ listId, itemId, relation }]`. Three UX layers make them intuitive:

1. **Inline chips (always visible).** Every task card displays clickable chips directly below its row for each forward relation (`derives-from / verifies / depends-on / blocks / related`), colored by target category. Clicking a chip jumps to the target list and highlights/scrolls to the target item. Any task referenced by other tasks displays a **gray "<- Referenced" chip** (reverse traceability).
2. **Relation Drawer** remains available for editing: it now includes a **keyword quick-link** search box — type a substring of a task title, pick from matches, instead of browsing multiple dropdowns.
3. **Relation Overview Modal** (header button): Displays the complete cross-category graph (`A -> relation -> B`), where every task name is clickable to jump and highlight. Completed endpoints are struck through with a green checkmark icon, and the overview respects the header Show/Hide Closed toggle: when closed items are hidden, edges touching completed tasks are filtered out. Jumping to a closed task from the graph automatically toggles the switch to make the target visible.

### `GET /api/links`
Returns the server-calculated global graph:
```json
{ "nodes": [ { "itemId","listId","listName","title","isDone","priority" } ],
  "edges": [ { "from": {"listId","itemId"}, "to": {"listId","itemId"}, "relation" } ] }
```
Use it (or CLI) to enumerate every cross-category dependency.

### CLI `links` Command
```bash
python scripts/litetask_cli.py links        # API mode (server up)
python scripts/litetask_cli.py --url http://127.0.0.1:9 links   # file mode
```
Prints each edge as ` [listName] title --[relation]--> [listName] title `, with titles resolved from the node list. Available in both API and file backends.

## 10. Password Storage (B2 — scrypt)

`data/users.json` no longer stores recoverable passwords.

- Canonical format: `scrypt$<N>$<r>$<p>$<saltB64>$<hashB64>`
  (`N=16384, r=8, p=1`, 16-byte random salt, 64-byte key, compared via `timingSafeEqual`).
- On server startup, legacy records (plaintext base64 or malformed `scrypt$$...` strings) are **automatically upgraded/repaired** and rewritten to `users.json`.
- `GET /api/admin/users` returns only `passwordScheme` (`scrypt` / `legacy`) and `passwordRecoverable: false` — **no plaintext, no hashes**.
- `/api/login`, `/api/admin/reset-password`, and `/api/admin/users` (creation) all write scrypt hashes.

**Rule for Agents:** Never write plaintext or base64 values into `users.json`. If seeding a credential is required, generate it using `crypto.scryptSync` per the documented format, or create the account via `POST /api/admin/users` to let the server hash it.

## 11. Concurrent Write Protection (B3)

Writes are no longer last-write-wins. Three defense layers:

1. **`rev` (Optimistic Concurrency Token)** — `GET /api/lists` returns a `rev` for each list, derived from the SHA-256 of item content (first 16 hex chars). Pass it back as `baseRev` in `PUT /api/lists/:id` (`type: UPDATE_ITEMS`). If stored items changed since you loaded them, the server responds with **409 `REV_CONFLICT`** along with current `items` — your write is rejected rather than overwriting theirs. Omitting `baseRev` retains legacy behavior but loses concurrency protection. Because `rev` is content-derived, **direct file edits by Agents are also detected**, unlike stored sequence counters.
2. **Per-file Asynchronous Write Lock** — Each read-modify-write cycle is serialized (`withLock`), preventing interleaved parallel requests.
3. **Atomic Writes** — Temporary files with rename retries (surviving NTFS/antivirus locks); `users.json` uses the same protected `saveUsers()`.

**CLI Behavior:** In API mode, the CLI automatically sends `baseRev`. On conflict, it prints a field-level diff and exits with:
`ERROR: REV_CONFLICT — '<list>' changed since this command loaded it …`
Rerun the command, or add `--force` to overwrite (see §18). In file mode (server stopped), this protection does not apply; avoid manual edits while the service is running.

**UI Behavior:** On 409, the UI retains your version in memory and opens a conflict diff modal — it never silently discards your edits (see §18).

## 12. Hiding Completed (F5) and Archiving (A1)

**F5 — Closed work is hidden by default.** The board displays only active items (`open`, `in-progress`, `blocked`, `verified`); the header toggle `Show Closed (N)` / `Hide Closed` switches visibility, stored in `localStorage` (`lt_show_closed`). Selecting a specific workflow status chip overrides the default hiding rule. Subtasks follow the same rule. `N` recursively counts closed items.

**A1 — Archiving keeps active files lean.**
- **Whole-tree rule (P1-2):** A top-level item is archived only when its *entire* subtree is closed (the item itself and every descendant have `isDone: true`). If the parent or any child is open, the **entire** subtree remains in the active list — closed subtasks are *not* orphaned. Only fully closed subtrees are moved.
- **Selective archiving (P1-3):**
  - `GET /api/lists/:id/archive-preview` (Admin) returns candidate fully-closed top-level subtrees (`candidates`, each with `itemId/title/level/isTop`) and excluded partially-closed items (`excluded`, with `reason`), allowing the UI to display exactly what will move before committing.
  - `POST /api/lists/:id/archive` (Admin, body `{userId, itemIds?}`) moves specified candidates, or **all** candidates if `itemIds` is omitted. Returns `{ moved, remaining, archiveCount }`. Idempotent (second call returns `moved: 0`).
- `GET /api/archive/:id` returns `{ listId, listName, items, lastArchivedAt }`.
- **Pre-archive snapshot (P1-4):** Before altering any files, `archiveList` writes `data/archive-snapshots/<listId>-<stamp>.snapshot.json`, capturing pre-modification state of **both** active and archive files. This makes archiving auditable and reversible.
  - `GET /api/lists/:id/archive-snapshots` (Admin) lists the audit trail (newest first): `{ count, snapshots: [{ file, stamp, listName, activeItemCount, archiveItemCount }] }`.
  - `POST /api/lists/:id/archive-restore` (Admin, body `{userId, stamp}`) reverses **one** archive action by writing captured state back to both files.
  - Snapshots are trimmed per list to the latest `MAX_ARCHIVE_SNAPSHOTS` (**20**).
- **Server Startup Auto-sweep:** When a list holds `>= LITETASK_AUTO_ARCHIVE_MIN_CLOSED` (default **25**) fully-closed top-level subtrees, it is automatically archived; disable with `LITETASK_AUTO_ARCHIVE=0`. Pre-archive snapshots are written here as well.

**CLI:**
```bash
python scripts/litetask_cli.py archive --category arch --dry-run   # preview only
python scripts/litetask_cli.py archive --category arch             # execute
```

**Rule for Agents:** Closed tasks you create disappear from the default view (this is expected — they remain on disk and are counted). **Do not** archive simply to tidy up: archiving is an administrative operation. Every move takes a snapshot, so accidental archives can be rolled back via `POST /api/lists/:id/archive-restore`, but keep tasks in place unless the user requests it or the auto-threshold triggers.

## 13. Workflow Status Flow (F1)

`data/categories.json` is the single source of truth for both `statuses` and `statusFlow`. The five statuses are:

| status | UI Label | Closed | Typical Usage |
|--------|----------|--------|---------------|
| `open` | Open | No | Planned but not yet started |
| `in-progress` | In Progress | No | Actively being implemented |
| `blocked` | Blocked | No | Stalled on dependencies/questions |
| `verified` | Verified | No | Implementation verified |
| `done` | Done | Yes | Completed |

Transition validation runs on `PUT /api/lists/:id` (and item endpoint §41). If an item attempts an illegal transition (e.g. `open -> verified`), the server returns `400 INVALID_TRANSITION` and names the allowed set:
`Invalid status transition 'open -> verified' (item title). Allowed: in-progress / blocked / done`

Every valid status change appends a record to `statusHistory`: `{ from, to, at: "YYYY-MM-DD HH:MM", by: "username" }`, keeping the latest 20 transitions.

## 14. Multi-path Source Linking (F2)

An item often relates to multiple source files or directories. F2 adds `localDirectories: string[]` (max 20 entries, deduplicated) alongside the primary `localDirectory`.

- `localDirectory` is always the first element of `localDirectories`.
- Setting `localDirectories` updates `localDirectory` automatically; setting `localDirectory` prepends it to `localDirectories`.
- The CLI supports `--dir <primary>` and `--extra-dir <path>` (repeatable).
- In the UI, clicking the folder icon opens a paths management dialog supporting multiple paths with primary path designation.

## 15. Reverse Traceability Query and Gap Analysis (F3)

The traceability engine analyzes relationships between items across categories:

### API Endpoints
- `GET /api/gaps` — Evaluates rules defined in `categories.json -> traceability`:
  1. `func-not-verified`: Feature items without verifying test items (`verifies`).
  2. `arch-not-derived`: Architecture items without derived feature items (`derives-from`).
  3. `orphan`: Items with zero incoming or outgoing relations.
- `GET /api/trace/:listId/:itemId?direction=back|forward&depth=3` — Traverses the relation graph recursively up to specified `depth`.

### CLI
```bash
python scripts/litetask_cli.py gaps
python scripts/litetask_cli.py trace --category func --title-or-id "<id>" --direction back
```

## 16. Startup Backup

On every server startup, `lib/backup.js` creates a full timestamped backup of the `data/` directory under `backup/backup-<stamp>/`.

Key mechanisms:
- Backup directory names use formatted timestamps: `backup-YYYYMMDD-HHmmss`.
- Rotation policy: Retains the latest `LITETASK_BACKUP_KEEP` (default 5) backups; older backups are automatically pruned.
- Startup logs output: `[Backup] Created startup backup: backup/backup-<stamp>`.

## 17. Board Columns: Assignee Removed, Creator = AI Agent

The Kanban board no longer assigns work to human users:
- The legacy `assignedTo` field is deprecated and no longer displayed in the UI.
- New tasks record the creating agent in `createdByAgent` (e.g. `antigravity`, `claude`, `human`).
- The board displays `Creator · AI Agent` in task cards and inspector headers.

## 18. Save Conflict Diff and Force Overwrite (B3 Follow-up)

When a concurrent write conflict (409) occurs, the server returns a detailed diff between client and server items.

### Conflict Diff Shape
```json
{
  "code": "REV_CONFLICT",
  "serverRev": "a1b2c3d4e5f60718",
  "diff": {
    "added": [ /* items added by server */ ],
    "removed": [ /* items removed by server */ ],
    "changed": [ /* items modified by both, with field-level diffs */ ],
    "counts": { "added": 0, "removed": 0, "changed": 1 }
  }
}
```

### Resolution Options in UI
1. **Keep All Server**: Discard client changes and reload server state.
2. **Apply Selected Merge**: Apply field-level selections and write with fresh `baseRev`.
3. **Overwrite with My Version**: Force overwrite using current client state via PUT /api/lists/:id with force: true.

In CLI:
```bash
python litetask_cli.py status --category func --title-or-id "..." --status done
# If conflict occurs:
python litetask_cli.py --force status --category func --title-or-id "..." --status done
```

## 19. Traceability Matrix — Current State and House Rules

The matrix (`litetask_cli.py gaps`) is the acceptance surface; here are the conventions that keep it honest.

**Current State (2026-10-28):**

| Rule | Before | Now |
| --- | --- | --- |
| `func-not-verified` | 2 | **1** — Only `Clean up legacy files (M2 Core Features)` remains, as M2 itself is `open` |
| `arch-not-derived` | 7 | **0** |
| `orphan` | 7 | **0** |

Graph edges increased from 11 -> 29, then stabilized at 28 after F4->B2 cleanup (§20).

**Items marked `... (Core Features)` are retrospective alignments, not new work.** B1/B2/B3/M3/A1 and startup backup were initially created only as `arch` items; their functional counterparts were never established. A corresponding `func` item was added for each, declaring `derives-from -> <arch>`, marked `done` (M2 remains `open`), with comments noting: `Retrospective entry: same implementation as arch '...', described from feature perspective.` Do not interpret these as newly scoped work — they have no separate implementation.

**Two downstream effects and their respective rules:**
1. Connecting `arch -> func` immediately exposes those new `func` items as `func-not-verified`. **Do not** create separate verification tasks for each synthetic entry — reuse existing verification tasks (a test item can `verifies` multiple targets).
2. Unfinished work must remain unverified. M2 is `open`, so its functional counterpart **intentionally** remains the sole `func-not-verified` item — creating verification for unbuilt work amounts to faking coverage.

**ID Hygiene:** Always link by `itemId`, never by title similarity.

## 20. Removing Incorrect Relation Edges (unlink)

`link` is **append-only**, meaning it can never fix a bad edge — previously the only remedy was full list `PUT` or manual JSON surgery. `litetask_cli.py unlink` is its inverse and the preferred way to remove an edge.

```bash
# remove one edge by target
python litetask_cli.py --url http://localhost:3000 unlink     --category func --title-or-id task_func_f4 --target arch:task_17931398547122b65eb

# drop every edge of one relation type (no --target)
python litetask_cli.py unlink --category func --title-or-id "..." --relation related
```

Semantics:
- `--target <list>:<itemId>` — Repeatable, removes specific edges.
- `--relation <type>` — When used alone, drops all edges of that relation type; combined with `--target`, narrows match.
- **A target or relation must be specified.** Bare `unlink` refuses to clear all edges.
- Unmatched or unknown tasks return non-zero errors, never silent success.

## 21. Fourth Category: Benchmarks & Acceptance (exam)

The home for **reusable, standardized benchmarks and golden test scenarios** with known answers, fixed inputs, and reference outputs (regression baselines, acceptance suites). It sits alongside `arch`, `func`, and `test`.

**It is distinct from `test`.**

| Aspect | `test` Testing & QA | `exam` Benchmarks & Acceptance |
| --- | --- | --- |
| Role | A scheduled verification run | A reusable standard benchmark scenario |
| Example | Verify F2 multi-path linking | Re=100 Cylinder Wake flow benchmark |
| Lifecycle | open -> verified -> done, then archived | Retained indefinitely as reference |

Adding a category is configuration, not code: append to `data/categories.json -> categories` (`listId`, `type`, `name`, `color`, `description`) and restart. `initCategories()` provisions `data/shared_lists/<listId>.json` if missing, without overwriting existing data.

Empty `exam` lists do not contribute to `orphan` counts (no nodes, no edges).

### Golden Case 01 — Five-state Machine Flow Matrix (25 cells)
Validates all 25 `(from -> to)` pairs across the five workflow statuses.
- **Recorded answer: 22 accepted / 3 rejected.**
- The three rejections are `open -> verified`, `blocked -> verified`, and `verified -> open`.
- Executable answer: `python tests/exam_case_01_status_flow.py` prints the matrix, declared vs observed divergences, outputs `ANSWER_JSON`, and restores the list to pre-run snapshot.

## 22. M1: Making Mandatory Browser Checks Reusable

Every change to `public/index.html` (Vue templates, script bindings, CSS classes) must be verified in a real headless Chrome browser. Reading code is not proof; a passing HTTP curl response is not proof.

**Run all browser checks with one command:**
```bash
node tests/run_browser_checks.js            # all checks
node tests/run_browser_checks.js --only exam # filter by name
```

**Writing a new check** — `tests/browser_lib.js` provides the harness:
```javascript
const lib = require('./browser_lib');
const { check, finish } = lib.createChecker('my-check');
// navigate, interact, assert, finish()
```

## 23. Can the Agent See Tasks You Add in the Browser?

The honest answer has two halves:
1. **Visibility:** A task entered by a human in the browser lands in the same JSON file the Agent reads, and `python scripts/litetask_cli.py pending` surfaces it as unclaimed human work.
2. **Attribution:** A task created by an Agent is stamped with `createdByAgent: "<name>"`, so it is excluded from `pending` (otherwise the queue would be flooded with Agent self-generated tasks).

## 24. M2 Executed: Legacy File Cleanup

Legacy prototype files, temporary dumps, and unused scripts have been systematically removed and archived.
- Deleted obsolete legacy files and prototype code.
- Consolidated documentation into `docs/` and `references/`.
- Verified no broken imports or references remain across all test suites.

## 25. Exam 01 Closed: Probe and Grader Are Separate Files

Separation of concerns between execution and evaluation:
- Probe (`tests/exam_case_01_status_flow.py`): Exercises the target system, produces raw measurements and answers.
- Grader (`tests/exam_case_01_grade.py`): Compares measurements against the recorded gold standard, checks byte-level isolation, and asserts reproducibility.

## 26. Graders: Every Verification Item Can Be Re-derived

The test suite is structured around re-derivable graders rather than one-off test scripts:
- Each grader in `tests/grade_*.py` evaluates a specific architectural property or regression boundary.
- `python tests/run_grade_checks.py` runs the entire suite, reporting passing checks and timing breakdowns.
- Graders assert properties, run mutations, and verify zero side-effects.

## 27. Exam 02: Four Outlets for a Conflict, and Where Scenarios Live

When a concurrent write conflict arises, four valid resolution paths exist:
1. Adopt My Version (force write with client state).
2. Keep Server Version (discard client edits).
3. Apply Selected Merge (field-by-field merge with fresh `baseRev`).
4. Cancel (exit without saving, keeping unsaved edits in client memory).

Evaluated by `tests/exam_case_02_grade.py` against isolated test lists.

## 28. Auto-archive Has Protected Lists, Threshold Is Declarative

Automatic archiving safeguards active list sizes while preventing accidental archival of critical lists:
- Configured via `archive.protected` in `data/categories.json`: lists `arch`, `func`, `test`, `exam`, `bug` are protected from auto-archive.
- Auto-archive threshold (`minClosed: 25`) triggers during `server.js` startup sweep `autoArchiveSweep()`.
- Protected lists are never archived automatically, regardless of closed item count.

## 29. Archived Work Remains in the Graph

Archiving moves storage, not evidence:
- `buildLinkGraph()` reads both `data/shared_lists/` and `data/archive/`.
- Archived items retain their relations and are marked with `archived: true`.
- Traceability queries continue to resolve through archived nodes so coverage gaps are not falsely reported when tasks are archived.

## 30. Exam 03 — Archiving Moves Storage, Not Evidence

Standard benchmark verifying that archiving completed tasks preserves the traceability graph:
- A verified feature whose verifying test item is archived does NOT become a `func-not-verified` gap.
- Grader: `tests/exam_case_03_grade.py` (40 checks) verifies graph connectivity across archive boundaries.

## 31. Idempotent Writes, and Zero-Side-Effect Grading (Testing Architecture P1)

Writing identical content to a list must not mutate `updatedAt` or increment `rev`:
- Server compares `contentRev(items)` before writing.
- If identical, returns 200 without modifying disk or metadata.
- Graders verify zero-side-effect execution across test runs.

## 32. Pre-commit Gate (Continuous Integration P1)

Local pre-commit hook runs the fast subset of graders before allowing a commit:
- Fast subset runs in ~19 seconds: `python tests/run_grade_checks.py --fast`.
- Install via: `python scripts/install_precommit_hook.py`.
- Allows explicit bypass only with documented reason: `LITETASK_SKIP_GRADES=1 LITETASK_SKIP_REASON="<reason>"`.

## 31. PUT /api/lists/:id — Removing Out-of-Lock Existence Check

Fixed race condition where list existence was checked before acquiring the list mutex lock:
- Existence check moved inside `withLock(listId)` to prevent concurrent deletion/creation races.
- Verified by `tests/grade_b3_concurrency_core.py`.

## 32. Local Mode Passwordless (2026-10-29)

For local development convenience, passwordless authentication can be enabled:
- Controlled solely via environment variable: `LITETASK_DEV_LOGIN=1`.
- When active, logging in as admin bypasses password verification.
- Server displays an explicit security warning banner on startup when active.

## 33. Honestly Retiring a Check (2026-10-29)

When an architectural invariant changes or a legacy constraint is superseded:
- Do not silently delete or comment out tests.
- Formally mark the check as `retired` with documented rationale and historical context.

## 34. Who Owns a Background Process (2026-10-29)

Process management and lifecycle governance for background services:
- `scripts/litetask_ensure.ps1` checks for active server instances on port 3000.
- If not running, launches server in background and records PID.
- Provides status, health verification, and clean shutdown capabilities.

## 35. Security Boundary P2 — Audit, Mode Banner, Destructive Second Confirmation

Comprehensive security boundary hardening:
- **Audit Logging**: `writeAudit` logs all administrative, authentication, and destructive actions to `data/audit.log`.
- **Mode Banner**: UI clearly indicates whether the server is operating in production, local, or dev mode.
- **Destructive Confirmation**: Hard gate requiring explicit `confirm=true` on all destructive operations (list deletion, batch archival, force overwrite).

## 36. Capacity P2 — 1k / 5k Baseline, and Where the Performance Inflection Point Is Not

Scale profiling up to 5,000 items:
- Benchmark script: `tests/scale_probe.py`.
- Evaluates JSON serialization, read latency, memory consumption, and disk I/O under 1,000 and 5,000 items.
- Server-side read/write scales near-linearly; server CPU/memory is not the bottleneck at these scales.

## 37. Capability Index, and Why It Is Verified Rather Than Trusted

Documentation must remain synchronised with code reality:
- `scripts/check_doc_index.py` verifies every row in the §0 index table.
- Confirms referenced files exist, section headings match uniquely, and distinctive anchor strings appear within the section boundary.
- Automated gate ensures no documentation link goes stale.

## 38. Blind Spot of the Iron Rule: Edits Made While Instance Is Stopped (2026-10-30)

When edits occur while the server is stopped, file watchers cannot emit change events:
- Open browser tabs would retain stale state after server restart.
- Resolution: Server emits `socket.emit('resync')` upon every new client WebSocket connection.
- Clients receiving `resync` refresh their cached state immediately.

## 39. Destructive Confirmation Is Now a Hard Gate (2026-10-31)

Destructive endpoints enforce strict confirmation:
- Requests omitting `confirm=true` are rejected with `400 DESTRUCTIVE_CONFIRMATION_REQUIRED`.
- Enforced on `DELETE /api/lists/:id`, `POST /api/lists/:id/archive-restore`, and force overwrites.
- Verified by `tests/grade_destructive_confirm.py` using `requireConfirm`.

## 40. Incremental Sync P3-A — ETag, 304, and an Event Stating Actor

Optimizing client-server synchronization:
- Server computes `listsETag` across list contents.
- Supports conditional HTTP requests returning `304 Not Modified`.
- Broadcasts change events carrying the acting actor identity to prevent unnecessary client re-fetches.

## 41. Item-level Write Endpoint P3-B — One Item Without Shipping 32 Others

Fine-grained updates without transmitting entire lists:
- Endpoint: `PUT /api/lists/:id/items/:itemId`.
- Handles status changes, title edits, or comment updates for a single item.
- Falls back to full list write only when structural hierarchy changes occur (`itemWrite`).

## 42. Integrity Report P3-D+E — Cheap Version, and What It Discovered

Integrity validation for relation graphs and item identity:
- `indexAllItemIds` scans all active and archived lists.
- Detects duplicate item IDs and dangling relation edges pointing to non-existent tasks.
- Reported via `GET /api/integrity` and `litetask lint`.

## 43. DOM Rendering Baseline: The Honest Limitation in §36 Has Been Closed

Full browser rendering performance benchmark:
- Real headless browser automation via `tests/browser_render_baseline_check.js`.
- Evaluates first contentful paint (FCP), DOM node count, and render completion time.
- Identifies browser DOM rendering limits at 5,000 items, motivating future virtual scrolling.

### 38.1 Derived Reads: No Caching Implemented (P2-6)

P2-6 deliberately avoids caching derived endpoints (`/api/links`, `/api/integrity`, `/api/health`). Direct file parsing remains sufficiently fast (< 35 ms) and guarantees immediate consistency without cache invalidation risks. Vendored same-origin assets in `public/vendor` comply with strict `CSP` policies.
