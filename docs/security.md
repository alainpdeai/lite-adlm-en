# Security and Trust Boundaries

This document details the concrete security mechanisms, assumptions, and deployment recommendations for Lite ADLM.

---

## 1. Network Surface

- **Loopback Binding**: By default, the board server binds strictly to `127.0.0.1` (loopback only). Attempting to bind to external or non-loopback addresses emits a startup security warning.
- **TLS Termination**: The server does not terminate TLS natively. When sharing across an intranet or remote host, place Lite ADLM behind a reverse proxy (e.g. Nginx, Caddy, Cloudflare Tunnel) with TLS encryption and upstream IP whitelisting.

---

## 2. Authentication Models

Lite ADLM supports two authentication modes configured via environment variables:

| Mode | Trigger | Behavior | Ideal Environment |
|---|---|---|---|
| **`local-passwordless`** | Default (`LITETASK_DEV_LOGIN=1`) | Bypasses password checks on localhost; auto-logs in as `admin`. | Local single-developer & agent workstations. |
| **`shared-authenticated`** | `LITETASK_DEV_LOGIN=0` | Enforces `scrypt` password verification; issues HTTP-only `lt_session` cookies. | Shared local network or team environments. |

---

## 3. Data API Trust Model

Data manipulation endpoints (`/api/lists/*`, `/api/items/*`) operate on a **local trust model**: requests pass caller `userId` without cryptographic session-token validation. 

> **Important**: Never expose Data APIs directly to untrusted public networks without an authenticating reverse proxy or API gateway.

---

## 4. Filesystem & Process Boundaries

- **Directory Whitelisting**: `POST /api/open-folder` only allows opening directories explicitly included in configured project root whitelists. Traversal attempts (e.g. `../../etc`) are rejected with `403 PATH_OUTSIDE_ALLOWED_ROOT` and logged to the audit system with rate limiting.
- **Subprocess Safety**: All child processes use explicit parameter arrays (`spawn(['git', 'status'])`) without shell string interpolation or `eval`, eliminating shell injection risks.
- **Content Security Policy (CSP)**: Strict CSP headers prevent inline script injection.
- **Same-Origin Vendoring**: All frontend dependencies (`Vue 3`, `Tailwind`, `Quill`, `DOMPurify`, `FontAwesome`) are vendored locally under `public/vendor/` with verified SHA-256 hashes in `VENDOR.json` — zero third-party CDN runtime dependencies.
