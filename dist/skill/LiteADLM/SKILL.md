---
name: LiteADLM
description: >-
  The pain point of Vibe Coding: tasks only live in ephemeral chat logs — humans
  cannot see what the Agent is doing, cannot inject new requirements mid-flight,
  and new chat sessions start by guessing. This skill is the antidote: a structured
  task tree shared between humans and AI Agents. In one sentence: Agents create tasks,
  advance statuses (in-progress/blocked/done), attach source paths and evidence notes,
  and establish traceable links across five standard lists (Architecture arch /
  Features func / Testing test / Benchmarks & Acceptance exam / Bug tracking bug),
  while humans can inject tasks or review status anytime. The pure Python CLI has
  zero external dependencies; starting the Node service provides a real-time Kanban board.
  Use proactively: update the task tree whenever starting, finishing, or discovering tasks,
  instead of leaving loose notes in chat.
agent_created: true
---

# LiteADLM Project Management Skill

## Purpose

Drives a software project management system based on LiteTask, keeping an active task board synchronized with actual development work. The system models five fixed categories and supports cross-category traceability:

- **arch** —— Architecture & System Design tasks.
- **func** —— Core Feature development tasks.
- **test** —— Testing & QA tasks.
- **exam** —— Benchmark & Acceptance test cases (reusable standard test cases: problems with known answers, fixed inputs, or baseline scenarios — regression baselines, acceptance criteria, benchmarks). Unlike `test`, which represents an scheduled validation task, `exam` items are reusable reference scenarios. Test cases alone *cannot* close a `func-not-verified` gap — only actual executed `test` runs can. Adding categories is configuration-driven: add to `data/categories.json → categories` and restart; the server automatically pre-provisions missing list files.
- **bug** —— Bug tracking, defects, runtime issues, and technical debt.

Each task item carries: priority (`High`/`Medium`/`Low`), workflow status (`open`/`in-progress`/`blocked`/`verified`/`done`), optional `blockedReason`, `statusHistory`, due date, `createdByAgent` (specifying which AI Agent created/owns the task; displayed under **Creator · AI Agent** column), source paths (`localDirectory` for primary path/URL, `localDirectories` for multiple extra paths), rich-text `comment` (notes), nested `subTasks`, and `relatesTo` (typed links pointing to items in other categories). The legacy `isDone` field stays synchronized: true only when status is `done`.

## Project Goal (North Star & Governance)

> The project development Goal is defined in **`GOAL.md`**: "Turn AI development progress and conclusions into a traceable, structured memory: tasks on the board, evidence on the tasks, and gaps detected automatically — enabling the next chat session to resume immediately rather than guessing from scratch."
> **Always consult the Goal before making architectural or feature decisions.**

**Decision Criteria (derived from Goal):**
- **Criterion 1 (Foundations)**: File-system JSON + 5 standard categories + state machine + `relatesTo` traceability + archiving/backup + zero-gap checks are sufficient to manage tasks, evidence, and gaps without external databases.
- **Criterion 2 (Acceptance)**: A feature is complete if the next session can resume work simply by inspecting the board, and gaps are highlighted automatically by `gaps` / `integrity`.
- **Criterion 3 (Scoping)**: Any new requirement must first be judged on whether it serves "traceable structured memory"; otherwise, mark as "no enhancement needed".

## When to Use

In any coding or development session, call this skill whenever:

- Starting a planned task (record it or mark status as `in-progress`).
- Completing a task (mark status as `done`, with `isDone` set to `true`).
- Discovering a new task, defect, or subtask (add it to the proper category).
- Attaching source paths, logs, or recording conclusions in notes.
- Declaring that a feature originates from an architecture decision, or a test verifies a feature (cross-category `relatesTo`).
- Performing **Gap Analysis**: finding unverified features, architecture without implementations, or orphaned items (`gaps`).

Do not leave task statuses solely in chat history. The task tree is the single source of truth for your team and future sessions.

## Agent Session Protocol

The session protocol is mandatory: the value of this skill depends on consistent board synchronization. Follow these three beats:

### 1. Starting Up: Read the Task Tree First

Before doing anything, establish situational awareness:

```bash
python scripts/litetask_cli.py pending        # Open tasks assigned to me from human board
python scripts/litetask_cli.py list           # Full task tree across all categories
python scripts/litetask_cli.py gaps           # Unverified features, missing links
```

Never start work without inspecting the task tree. If `pending` contains items inserted by human teammates, review and prioritize them first.

### 2. In Progress: Update Immediately on Completion

Whenever you start, block on, or complete an item, update the board **on the spot** — never batch updates until the very end:

- Start work: `status --category <category> --title-or-id "<task>" --status in-progress`
- Blocked: `status ... --status blocked --reason "<specific reason>"`
- Completed: `status ... --status done` (or `verified` if QA verification step exists)
- Discovered new work: `add --category <category> ... --agent "<agent-name>"`

### 3. Wrapping Up: Check Unclosed Items

Before ending the session, verify this checklist:

- [ ] Every task touched during this session has an accurate terminal state (`done`, `verified`, or `blocked` with `--reason`).
- [ ] All new tasks/bugs discovered are recorded in the proper category (`arch`/`func`/`test`/`exam`/`bug`).
- [ ] Key findings and executable evidence are written into item `comment` fields.
- [ ] Ran `lint --strict` and `gaps`: no dangling relations or missing required links.
- [ ] Every numbered item in your summary exists as a task on the board.

**Acceptance criteria**: The next session (or human collaborator) can resume work seamlessly just by looking at the board.

## Execution Modes

### Two Operational Modes: Choose Before Starting

The core capability **does not depend on any service** — `litetask_cli.py` is pure Python (standard library), reading and writing `data/shared_lists/*.json` directly. The Node board is an **optional enhancement**. The CLI auto-detects: if `http://localhost:3000` responds, it enters **API mode**; otherwise, it operates in **Standalone File mode**.

**Standalone Mode (Zero dependencies, pure CLI)**:
All core task management is available: task creation, state transitions, relationship links, traceability, gap analysis, archiving, and unarchiving. First-time setup:

```bash
python scripts/litetask_cli.py --root . init   # One-time: generates 5 empty lists (idempotent)
python scripts/litetask_cli.py --root . add --category func --title "First Task" --agent "AI Agent"
```

**Collaborative Mode (Optional Enhancement)**:
Start the Node.js board in the repository root to enable real-time browser collaboration, human task injection, and multi-user login:

```bash
npm install        # Express, Socket.IO (first time only)
node server.js     # Starts board at http://localhost:3000
```

When the board is running, all CLI commands automatically talk to the REST API — synchronizing with the browser board in real time.

---

## Path A —— CLI (Recommended, Deterministic)

Global options precede subcommands: `--root <dir>` (file mode), `--url <base>` (API mode), `--force` (overwrite on conflict).

```bash
# View categories and relations dictionary
python scripts/litetask_cli.py categories

# List tasks in a category (or all categories)
python scripts/litetask_cli.py list --category func

# Add a feature task, link source path, and relate to architecture
python scripts/litetask_cli.py add --category func \
    --title "Implement Auth" --priority High \
    --local-directory "src/auth" \
    --extra-dir "tests/test_auth.py" \
    --extra-dir "https://jwt.io/introduction" \
    --agent "AI Agent" \
    --comment "JWT auth implementation" \
    --relates arch:task_arch_001:derives-from

# Manage paths for an existing task: add / remove / set primary
python scripts/litetask_cli.py path --category func \
    --title-or-id "Implement Auth" --add "docs/auth.md"
python scripts/litetask_cli.py path --category func \
    --title-or-id "Implement Auth" --primary "src/auth"
python scripts/litetask_cli.py path --category func \
    --title-or-id "Implement Auth" --remove 2

# Add nested subtask
python scripts/litetask_cli.py add --category func \
    --title "Token Refresh Logic" --parent "Implement Auth"

# Update status through workflow
python scripts/litetask_cli.py status --category func \
    --title-or-id "Implement Auth" --status in-progress
python scripts/litetask_cli.py status --category func \
    --title-or-id "Implement Auth" --status blocked --reason "Waiting on secret key config"
python scripts/litetask_cli.py status --category func \
    --title-or-id "Implement Auth" --status in-progress
python scripts/litetask_cli.py status --category func \
    --title-or-id "Implement Auth" --status verified
python scripts/litetask_cli.py status --category func \
    --title-or-id "Implement Auth" --status done

# Multi-hop traceability (forward / backward)
python scripts/litetask_cli.py trace --category func \
    --title-or-id "Implement Auth" --direction back --depth 3
python scripts/litetask_cli.py trace --category arch \
    --title-or-id "Core Arch" --direction both --depth 2

# Coverage gaps analysis
python scripts/litetask_cli.py gaps
python scripts/litetask_cli.py gaps --rule func-not-verified
python scripts/litetask_cli.py gaps --owner test --referrer func --relation verifies

# Check pending work assigned to agent
python scripts/litetask_cli.py pending
python scripts/litetask_cli.py pending -v

# List allowed status transitions
python scripts/litetask_cli.py statuses

# Change priority
python scripts/litetask_cli.py priority --category func \
    --title-or-id "Implement Auth" --priority Low

# Add cross-category relationship
python scripts/litetask_cli.py link --category func \
    --title-or-id "Implement Auth" --relates test:task_test_001:verifies

# Remove relationship edge
python scripts/litetask_cli.py unlink --category func \
    --title-or-id "Implement Auth" --target test:task_test_001

# Check board health
curl --noproxy '*' http://127.0.0.1:3000/api/health

# Unarchive completed tasks (dry-run first)
python scripts/litetask_cli.py unarchive --category arch --dry-run
python scripts/litetask_cli.py unarchive --category arch
python scripts/litetask_cli.py unarchive --category arch --item <itemId>

# Item-level operations (avoids full list overwrite)
python scripts/litetask_cli.py item get    --category func --id task_...
python scripts/litetask_cli.py item add    --category func --parent "Parent Task" --title "Subtask"
python scripts/litetask_cli.py item status --category func --id task_... --status verified
python scripts/litetask_cli.py item rm     --category func --id task_...

# Integrity linting (dangling relations and duplicate IDs)
python scripts/litetask_cli.py lint
python scripts/litetask_cli.py lint --strict
```

---

## Path B —— Direct JSON Editing (Batch / Structural Repairs)

> **⚠️ Rule of Direct Editing: Stop Instance → Edit JSON → Restart Service.**
> The server reads JSON files upon request, but file watcher events notify the browser without reloading in-memory server state. If the server has a stale copy, the next write will silently overwrite your manual edits. The only safe sequence is:
> 1. **Stop running instance**: Find the process on port 3000 (`Get-NetTCPConnection -LocalPort 3000 -State Listen` -> `Stop-Process -Id <pid>`). Never kill all `node` processes indiscriminately.
> 2. **Edit JSON**: Ensure valid JSON, UTF-8, pure LF, no BOM. `rev` is `sha256(JSON.stringify(items)).slice(0,16)`.
> 3. **Restart service**: `node server.js` to reload updated files from disk.
> 4. **Verify via API**: `curl --noproxy '*' http://127.0.0.1:3000/api/lists` to confirm in-memory state matches disk.

---

## Destructive Operations Require confirm=true

Four endpoints require explicit affirmative confirmation:

| Endpoint | Confirmation Mechanism |
|---|---|
| `POST /api/lists/:id/archive` | Request body `"confirm": true` |
| `POST /api/lists/:id/archive-restore` | Request body `"confirm": true` |
| `PUT /api/lists/:id` with `force` dropping items | Request body `"confirm": true` |
| `DELETE /api/lists/:id` | Query string `?confirm=true` |

Rejections return `400 CONFIRMATION_REQUIRED` detailing what items would be removed. Strings like `'true'` or `1` do not qualify — strictly boolean `true`.

---

## Graders (Re-derivable Verification Items)

`python tests/run_grade_checks.py` re-derives the recorded answer for every verification item in the `test` category. A grader fails if reality deviates from the standard claim. Individual graders (`grade_*.py`) test isolation, schemas, concurrency, and security boundaries.

---

## Item-level Writes, Incremental Sync, and Integrity Linting (P3)

* **Item-level writes**: `POST|PUT|DELETE /api/lists/:id/items[/:itemId]` and `litetask_cli.py item get|add|status|rm` modify a single task without shipping full list payloads.
* **Incremental sync**: `GET /api/lists` supports `If-None-Match` returning `304 Not Modified`.
* **Integrity linting**: `python scripts/litetask_cli.py lint` reports dangling relations and duplicate IDs.

---

## Unarchive: Recovering Archived Items (P1)

`POST /api/lists/:id/unarchive` and `litetask_cli.py unarchive` recover archived tasks back to active lists, ensuring that archiving is never a one-way destructive street.

---

## Operational Rules

1. **Never delete tasks from shared lists** without admin privileges. Use `--status done` instead.
2. **Follow legal status transitions** defined in `data/categories.json`. Never jump directly from `open` or `blocked` to `verified`.
3. **Priority** must be exactly `High`, `Medium`, or `Low` (case-sensitive).
4. **Link source paths** in `localDirectory` and `--extra-dir`. Record key findings in `comment`.
5. **Always tag AI Agent identity** via `--agent` (or `LITETASK_AGENT` environment variable).
6. **Task Completeness**: When a plan or review enumerates tasks, ensure **all** items are entered on the board, not just the ones currently being coded. The board is the single source of truth.
