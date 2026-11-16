# Core Concepts

Lite ADLM is built on four architectural pillars: a structured **Task Tree**, an **Enforced State Machine**, **Cross-Category Relationship Edges**, and **Optimistic Concurrency Control**.

---

## 1. The Task Tree

Tasks are organized across five standard lists representing the essential stages of engineering:

| Category | List ID | Engineering Purpose | Example Task |
|---|---|---|---|
| **Architecture** | `arch` | System design, data schemes, interface contracts | "Design matrix-free PCG memory layout" |
| **Core Features** | `func` | User-facing features, core algorithms, domain logic | "Implement Mazars damage constitutive model" |
| **Testing & QA** | `test` | Unit tests, mock suites, regressions, CI checks | "Add Brazilian disc splitting validation test" |
| **Benchmarks** | `exam` | Convergence tests, performance baselines, acceptance criteria | "Verify L2 error norm < 1e-4 against analytical solution" |
| **Defects** | `bug` | Bug fixes, regression patches, numerical instability issues | "Fix Newton-Raphson non-convergence at yield point" |

### Storage & Concurrency Boundaries
- Each list maps to a single JSON file (`data/shared_lists/<listId>.json`).
- Each list acts as an independent concurrency boundary.
- The list-level revision (`rev`) is a deterministic content hash of its items.

---

## 2. Enforced State Transitions

Unlike generic todo lists that permit arbitrary toggling, Lite ADLM enforces a status transition model (`STATUS_FLOW`). Illegal transitions (such as jumping straight from `open` to `verified`) are rejected by both the CLI and HTTP API with `400 INVALID_TRANSITION`:

```
               ┌───────────────┐
               │     open      │───────┐
               └───────┬───────┘       │
                       │               │
         ┌─────────────┴─────────────┐ │
         ▼                           ▼ │
┌─────────────────┐         ┌──────────┴──────┐
│   in-progress   │ ◄─────► │     blocked     │
└────────┬────────┘         └──────────┬──────┘
         │                             │
    ┌────┴────┐                        │
    ▼         ▼                        │
┌─────────┐ ┌──────────────────────────▼──────┐
│verified │ │              done               │
└────┬────┘ └──────────────────▲──────────────┘
     │                         │
     └─────────────────────────┘
```

### Legal Transitions Matrix

| From State | Allowed Target States | Disallowed Jumps (Rejected) |
|---|---|---|
| `open` | `in-progress`, `blocked`, `done` | `verified` (cannot verify unworked task) |
| `in-progress` | `open`, `blocked`, `verified`, `done` | None |
| `blocked` | `open`, `in-progress`, `done` | `verified` |
| `verified` | `in-progress`, `blocked`, `done` | `open` |
| `done` | `open`, `in-progress`, `blocked`, `verified` | None (can reopen to any active state) |

### Transition Rules
1. **Direct Close Permitted**: A task may transition directly from `open` to `done` without passing through `in-progress` or `verified` (e.g. for administrative tasks or tasks resolved externally).
2. **Verification Gate is Advisory**: `SKILL.md` instructs agents to pass through `verified` and attach test evidence before closing features, but the underlying state machine allows direct close to `done`. This is why the `gaps` command exists: to audit the tree and flag features that were marked `done` without recorded verification links.
3. **Reopening**: Tasks can be reopened from `done` back to `open`, `in-progress`, `blocked`, or `verified` if regressions occur.
4. **Field Integrity**: `isDone` and `status` are synchronized automatically: only closed states (`done`) assert `isDone: true`, while active states (`open`, `in-progress`, `blocked`, `verified`) assert `isDone: false`.

---

## 3. Relationship Graph & Gap Analysis

Engineering tasks rarely exist in isolation. Lite ADLM links tasks across categories using formal relationship edges:

| Edge Type | Semantics | Typical Use |
|---|---|---|
| `derives-from` | Upstream lineage | A `func` feature derived from an `arch` architectural specification |
| `verifies` | Evidence link | A `test` or `exam` benchmark verifying a `func` implementation |
| `depends-on` | Execution dependency | Task A cannot start until Task B completes |
| `blocks` | Inverse blocker | Task A is actively blocking Task B |
| `relates-to` | Semantic association | Contextual cross-reference |

### Built-in Graph Queries & Gap Detection
The CLI and `/api/trace` / `/api/gaps` endpoints provide automated graph reasoning:
- **Cycle-Safe BFS Traversal**: Traverses dependency chains up to 5 hops, detecting circular dependencies.
- **Unverified Features**: Identifies `func` tasks marked `done` or `in-progress` that have no inbound `verifies` edge from a `test` or `exam` task.
- **Unclosed Dependencies**: Identifies active tasks that depend on incomplete upstream items.
- **Orphan Items**: Highlights tasks with no incoming or outgoing relationship edges.

---

## 4. Concurrency Control & Idempotent Writes

To support multiple AI agents and humans editing simultaneously without a database:

- **Optimistic Concurrency**: Writes supply `baseRev`. If another agent or human saved changes in the interim, the server rejects the write with `409 CONFLICT` and returns a visual diff, preventing silent overwrites.
- **Idempotent Retries**: When AI agents retry a failed network request or re-send a write payload, identical writes are detected and succeed safely without creating duplicate tasks.
- **Atomic File Swaps**: JSON files are written via temporary files and atomically renamed (`os.replace` / `fs.renameSync`), ensuring zero file corruption on system crashes.
