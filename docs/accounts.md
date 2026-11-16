# Teams & Accounts: Collaboration, Not Permission Silos

Lite ADLM manages user credentials in `data/users.json`. 

---

## 1. Design Intent: Attribution, Not Restriction

Accounts in Lite ADLM solve **attribution and ownership** ("who created this task, who is currently assigned, and who verified/closed it"). 

All human team members and AI agents share and collaborate on the same task tree. Fine-grained permission silos (e.g., "User A cannot read List B") are intentionally out of scope: in fast-paced Vibe Coding and engineering projects, transparency and rapid handoffs are paramount.

---

## 2. AI Agent Attribution

- **CLI Operations**: The CLI (`scripts/litetask_cli.py`) operates by default under the administrative role `user_admin` (`userId: user_admin`), ensuring agent operations are never blocked by permission barriers.
- **Agent Identity**: Tasks created or modified by AI tools record the specific agent name in the `createdByAgent` / `updatedByAgent` fields (e.g. `createdByAgent: "Claude Code"` or `"Cursor Agent"`).
- **Human Collaboration**: When a human adds a task on the web board, it records the human's account name. Both human and agent tasks sit side-by-side in the same tree.

---

## 3. User Account Security

- **Password Storage**: Passwords are hashed using Node.js native `crypto.scrypt` with individual random 16-byte salts. Plaintext passwords are never persisted.
- **Session Management**: Authenticated mode issues secure HTTP-only `lt_session` cookies with `SameSite=Lax`.
- **Default Credentials**: The initial installation seeds default administrator credentials (`admin/admin` in `config/site.json`). This placeholder is strictly for immediate local setup and **must be changed** via the User Management modal or `POST /api/admin/reset-password` before team sharing.
