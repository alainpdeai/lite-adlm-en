# Lite ADLM Installation & First-Run Setup Guide

Lite ADLM is a lightweight Web Task Manager / Structured Memory system designed for Vibe Coding and AI Agent collaboration.
It merges a standalone runtime system with governance assets into a clean, deployable codebase free of proprietary project data, domain dictionaries, or credentials.

This guide walks you through the complete setup from obtaining the code to running a customized instance.
**No advanced programming skills are needed** — you only need to configure a single JSON file (or run an interactive CLI wizard).

---

## 0. Prerequisites

| Dependency | Requirement | Purpose |
|---|---|---|
| Node.js | ≥ 18 (Tested on v20 & v22) | Backend runtime |
| npm | Bundled with Node.js | Package manager and scripts |
| Browser | Any modern browser | Accessing the web board |
| Network | Internet access on first `npm install` | Installing `express`, `socket.io`, `chokidar`, `fs-extra` |
| Python | 3.8+ | CLI tools and test gates |

> All task data is stored locally in `data/` as JSON files. **No database or cloud account is required.**

---

## 1. Install Dependencies

```bash
cd lite-adlm
npm install
```

This installs necessary server dependencies into `node_modules/` (excluded from version control via `.gitignore`).

---

## 2. Configuration (`config/site.json`)

The project brand, subtitle, Goal, admin credentials, and port are driven by **`config/site.json`**.
**Setup = edit this file (or run the interactive wizard in Step 3).**

### 2.1 Default Configuration

```json
{
  "projectName": "Lite ADLM",
  "subtitle": "Shared Task Tree",
  "loginSubtitle": "Team Shared Workspace",
  "logPrefix": "ADLM",
  "goal": "An AI-assisted project management system: turning development progress and unexpected tasks into a structured memory during development, displayed intuitively on a live web board while preserving traceable history.",
  "admin": {
    "userId": "user_admin",
    "username": "admin",
    "password": "admin"
  },
  "port": 3000
}
```

### 2.2 Field Descriptions

| Field | Default | Description |
|---|---|---|
| `projectName` | `Lite ADLM` | **Project Name**. Injected into page title, sidebar, login modal, and headers. Change this to your project's name. |
| `subtitle` | `Shared Task Tree` | Subtitle displayed beneath the main board title. |
| `loginSubtitle` | `Team Shared Workspace` | Subtitle on the login modal. |
| `logPrefix` | `ADLM` | Server console log prefix `[ADLM]`. |
| `goal` | One-sentence goal | High-level North Star goal, exposed via `/api/config`. |
| `admin.userId` | `user_admin` | Internal user ID for the primary administrator. |
| `admin.username` | `admin` | Administrator username. |
| `admin.password` | `admin` | ⚠️ **Default password. Change before deploying outside local machine.** Only effective on first initialization. |
| `port` | `3000` | Port for the HTTP server (override via `PORT` environment variable). |

> **Security Mode is an Environment Variable, not a JSON field**:
> The authentication mode is strictly controlled by `LITETASK_DEV_LOGIN`.
> - Unset (default): `passwordless-local` (instant login with username, loopback binding).
> - Set to `0`: `shared-authenticated` (enforces scrypt password check and HTTP-only session cookies).

---

## 3. (Optional) Interactive Wizard

To configure interactively via the command line:

```bash
npm run init
```

The wizard prompts for:
1. **Brand & Runtime**: Project name, subtitle, goal, admin credentials, port.
2. **Project Context**: Project domain, repository root, truth policy.
3. **Project Knowledge**: Custom L2 subdomains and key file anchors.

Press **Enter** to accept existing defaults. Rerunning `npm run init` is idempotent.

Non-interactive CI mode:

```bash
node scripts/init.js --defaults
```

### 3.1 Taxonomy Validation

```bash
npm run validate                  # Validates taxonomy, file anchors, and task note specs
npm run validate -- --strict       # Strict mode: treats warnings as errors
```

---

## 4. Categories & Rules (`data/categories.json`)

`data/categories.json` is the **single source of truth** defining:
- The 5 standard task categories (`arch`, `func`, `test`, `exam`, `bug`), their colors, and descriptions.
- Relationship types (`related`, `derives-from`, `verifies`, `depends-on`, `blocks`).
- Workflow status transitions (`open`, `in-progress`, `blocked`, `verified`, `done`).
- Traceability gap rules (`func-not-verified`, `arch-not-derived`, `orphan`).
- Auto-archive policies (`minClosed: 25`, `protected` categories).

Modify `data/categories.json` to customize categories or archiving thresholds. Changes take effect upon restarting the server.

---

## 5. Starting the Service

```bash
npm start
```

- Listens on `http://localhost:3000` (or configured `port`).
- Bootstraps `data/` directories, initializes default categories, and seeds the admin user on first launch.

### Multi-user & Network Deployment

- By default, the server binds strictly to `127.0.0.1` (loopback).
- For team collaboration in a trusted LAN:
  ```bash
  LITETASK_DEV_LOGIN=0 LITETASK_BIND_HOST=0.0.0.0 npm start
  ```
- **Do not expose directly to the public internet** without a TLS reverse proxy (e.g. Caddy, Nginx).

---

## 6. Verifying Installation

Verify endpoints via `curl` or browser:

```bash
# Health check
curl http://localhost:3000/api/health

# Public configuration
curl http://localhost:3000/api/config
```

Open `http://localhost:3000` in your browser:
- Page title reflects your configured `projectName`.
- All board columns and task categories are visible and ready.

---

## 7. Creating History Snapshots

Lite ADLM preserves traceable development milestones:

```bash
npm run snapshot
```

Captures point-in-time snapshots of all task lists with file SHA-256 hashes into `docs/records/<timestamp>/`. This directory is tracked by git, ensuring milestone history is preserved across repositories.

---

## 8. Zero-Dependency Skill Packaging

To build the self-contained AI Agent Skill package:

```bash
python scripts/build_skill_package.py --verify
```

Creates a standalone package in `dist/skill/LiteADLM/` containing the bundled server, CLI tools, frontend, and SKILL.md.
