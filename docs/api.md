# REST API Reference

All Lite ADLM API endpoints are routed under `/api`:

---

## 1. Health & Configuration

| Endpoint | Method | Description | Response Status |
|---|---|---|---|
| `/api/health` | `GET` | Service health status, uptime, and active list counts | `200 OK` |
| `/api/config` | `GET` | Project metadata (`projectName`, `brand`, `securityMode`) | `200 OK` |

---

## 2. Authentication & Session

| Endpoint | Method | Description | Response Status |
|---|---|---|---|
| `/api/login` | `POST` | Authenticate user credentials and issue `lt_session` cookie | `200 OK` / `401 UNAUTHORIZED` |
| `/api/logout` | `POST` | Invalidate current session cookie | `200 OK` |

---

## 3. List & Item Operations

| Endpoint | Method | Description | Response Status |
|---|---|---|---|
| `/api/lists` | `GET` | Retrieve summary of all 5 lists with revision hashes | `200 OK` |
| `/api/lists/:id` | `GET` | Fetch full list items and metadata | `200 OK` / `404 NOT_FOUND` |
| `/api/lists/:id` | `PUT` | Atomic full-list write; validates `baseRev` unless `force: true` | `200 OK` / `409 CONFLICT` |
| `/api/lists/:id/items` | `POST` | Append new item to list (idempotent write support) | `200 OK` / `400 INVALID_SCHEMA` |
| `/api/lists/:id/items/:itemId` | `PUT` | Update specific item attributes, state, or relations | `200 OK` / `400 INVALID_STATUS` |
| `/api/lists/:id/items/:itemId` | `DELETE` | Remove task item from list | `200 OK` / `404 NOT_FOUND` |

---

## 4. Relations, Trace & Integrity

| Endpoint | Method | Description | Response Status |
|---|---|---|---|
| `/api/links` | `GET` | Relationship graph containing all inter-task edges | `200 OK` |
| `/api/trace` | `GET` | Cycle-safe multi-hop BFS dependency traversal | `200 OK` |
| `/api/gaps` | `GET` | Gap analysis report (unverified features, unclosed blockers) | `200 OK` |
| `/api/integrity` | `GET` | Schema and bidirectional relation consistency report | `200 OK` |

---

## 5. Archiving & Snapshots

| Endpoint | Method | Description | Response Status |
|---|---|---|---|
| `/api/archive-status` | `GET` | Overview of archived items count per category | `200 OK` |
| `/api/lists/:id/archive-preview` | `GET` | Dry-run preview of candidate completed items | `200 OK` |
| `/api/lists/:id/archive` | `POST` | Commit completed items to archive (`confirm: true` required) | `200 OK` / `400 BAD_REQUEST` |
| `/api/lists/:id/archive-restore` | `POST` | Rollback last archive operation from snapshot | `200 OK` / `400 NO_SNAPSHOT` |

---

## 6. Administration & Audit

| Endpoint | Method | Description | Response Status |
|---|---|---|---|
| `/api/users` | `GET` | List active users for assignment dropdowns | `200 OK` |
| `/api/admin/users` | `POST` | Create new human user account | `200 OK` / `400 EXISTS` |
| `/api/admin/reset-password` | `POST` | Change user password | `200 OK` |
| `/api/admin/users/:userId` | `DELETE` | Delete human user account | `200 OK` |
| `/api/audit` | `GET` | Paginated security and change audit log | `200 OK` |
| `/api/open-folder` | `POST` | Open whitelisted directory in OS file explorer | `200 OK` / `403 FORBIDDEN` |
