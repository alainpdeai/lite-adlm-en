# -*- coding: utf-8 -*-
"""
Grader for test item Verify B1 port graceful exit and F4 passwordless login
(task_1793139243975ea9524).

Two claims are recorded on that item and re-derived here:

F4 (no-login entry): the board is usable without signing in, but that
convenience must not quietly extend to the admin surface. `/api/config` exposes
`devAutoLogin`, unauthenticated reads of the shared lists succeed, and the admin
endpoints still answer 403 without a session.

B1 (port conflict handled gracefully): a second instance must fail loudly and
exit 1 with an actionable message — not hang, not half-start, not corrupt the
instance that already owns the port.

The second instance is started on its own port too, which proves the suggestion
printed in the error message (`PORT=<n+1> node server.js`) actually works.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import api, Checker, ROOT, free_port, http_at   # noqa: E402

c = Checker("B1/F4")

print("== F4: no-login entry, admin surface still guarded ==")
st, cfg = api("GET", "/api/config")
c.check("GET /api/config is readable", st == 200, (st, cfg))
c.check("devAutoLogin is on", isinstance(cfg, dict) and cfg.get("devAutoLogin") is True, cfg)

st, _ = api("GET", "/api/lists")
c.check("shared lists readable without a session", st == 200, st)
st, _ = api("GET", "/api/categories")
c.check("categories readable without a session", st == 200, st)

st, body = api("GET", "/api/admin/users")
c.check("admin user list still 403 without a session", st == 403, (st, body))
c.check("403 body names the reason",
        isinstance(body, dict) and "Forbidden" in str(body.get("error", "")), body)

# (The password gate itself is graded against a shared-mode instance at the end
#  of this file, once spawn() exists.)

print()
print("== B1: second instance on a busy port ==")


def spawn(port, wait=6.0, env_extra=None):
    env = dict(os.environ, PORT=str(port))
    if env_extra:
        env.update(env_extra)
    p = subprocess.Popen(
        ["node", "server.js"], cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    time.sleep(wait)
    return p


p = spawn(3000)
try:
    p.terminate()
    out, err = p.communicate(timeout=20)
except subprocess.TimeoutExpired:
    p.kill()
    out, err = p.communicate(timeout=20)

blob = (out or "") + (err or "")
c.check("second instance exits non-zero", p.returncode != 0, p.returncode)
c.check("it names EADDRINUSE / already in use",
        "already in use" in blob or "EADDRINUSE" in blob, blob.strip()[:200])
c.check("it suggests another port (PORT=3001)",
        "PORT=3001" in blob, blob.strip()[:200])
c.check("it does not print a raw stack trace",
        "at Server." not in blob and "node:internal" not in blob,
        blob.strip()[:200])

st, _ = api("GET", "/api/lists")
c.check("the instance that owns the port is unaffected", st == 200, st)

print()
print("== B1: the suggested workaround actually works ==")
p2 = spawn(3999, wait=6.0)
try:
    p2.terminate()
    out2, err2 = p2.communicate(timeout=20)
except subprocess.TimeoutExpired:
    p2.kill()
    out2, err2 = p2.communicate(timeout=20)
blob2 = (out2 or "") + (err2 or "")
c.check("an instance on PORT=3999 starts", "Server running on http://localhost:3999" in blob2,
        blob2.strip()[:160])
c.check("startup backup runs on that instance too", "Startup backup" in blob2,
        blob2.strip()[:160])

print()
print("== F4: the password gate still bites when it is switched on ==")
# Local mode is passwordless since 2026-10-29 (see grade_passwordless_login.py),
# so "wrong credentials are refused" is graded here, against a shared-mode
# instance where the gate is on: the convenience must not have quietly removed
# the check for deployments that need it.
pw_port = free_port()
p_pw = spawn(pw_port, env_extra={"LITETASK_DEV_LOGIN": "0"})
try:
    pbase = "http://localhost:%d" % pw_port
    st, body = http_at(pbase, "POST", "/api/login",
                       {"username": "admin", "password": "admin"})
    c.check("correct credentials still accepted", st == 200, (st, body))
    st, body = http_at(pbase, "POST", "/api/login",
                       {"username": "admin", "password": "definitely-wrong"})
    c.check("wrong credentials rejected with 401", st == 401, (st, body))
    st, body = http_at(pbase, "POST", "/api/login", {"username": "admin"})
    c.check("a bare username is refused while the gate is on", st == 401, (st, body))
finally:
    try:
        p_pw.terminate()
        p_pw.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        p_pw.kill()
        p_pw.communicate(timeout=20)

c.finish()
