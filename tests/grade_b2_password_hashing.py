# -*- coding: utf-8 -*-
"""
Grader for test item Verify B2 password hashing and security hardening (task_1793140426939ae2e9c).

Recorded claim: passwords are stored as scrypt hashes — never plaintext, never a
reversible encoding — the public user endpoint does not hand them out, and the
login path compares through the hash rather than the raw string.

This grader deliberately does not create, reset, or delete any user. Verifying a
password store by mutating it would be a grader that can lock someone out.

Mode note (2026-10-29): local mode is now passwordless — /api/login accepts a
username alone and ignores the password, so "a wrong password is refused" is no
longer a property of the default instance. That property still holds, and is
still graded, but only where the password gate is actually on: the checks below
run against a shared-mode instance (LITETASK_DEV_LOGIN=0) started from a copy of
data/ with a grader-minted account, so they assert the real hash comparison
without depending on anyone's real password. See grade_passwordless_login.py for
the local/shared contrast itself.
"""
import base64
import hashlib
import json
import os
import re
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import api, Checker, ROOT, copy_data_dir, http_at, run_instance, stop_instance, temp_dir  # noqa: E402

c = Checker("B2")

STORED = re.compile(r"^scrypt\$(\d+)\$(\d+)\$(\d+)\$[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+$")


def scrypt_hash(plain, salt=b"litetask-grader-salt"):
    """Mint a canonical B2 record so the login checks need no real password."""
    key = hashlib.scrypt(plain.encode("utf-8"), salt=salt,
                         n=16384, r=8, p=1, dklen=64, maxmem=96 * 1024 * 1024)
    return "$".join(["scrypt", "16384", "8", "1",
                     base64.b64encode(salt).decode(),
                     base64.b64encode(key).decode()])

with open(os.path.join(ROOT, "data", "users.json"), encoding="utf-8") as f:
    raw = json.load(f)
users = raw.get("users", raw) if isinstance(raw, dict) else raw

print("== stored form ==")
c.check("users.json parses and has users", isinstance(users, list) and len(users) >= 1,
        type(users).__name__)
for u in users:
    pw = u.get("password")
    m = STORED.match(pw) if isinstance(pw, str) else None
    c.check("%s stores a scrypt hash" % u.get("username"), bool(m),
            (pw[:24] + "...") if isinstance(pw, str) else pw)

params = set()
for u in users:
    m = STORED.match(u.get("password") or "")
    if m:
        params.add((int(m.group(1)), int(m.group(2)), int(m.group(3))))
c.check("every record uses the same scrypt parameters", len(params) == 1, params)
c.check("parameters are N=16384 r=8 p=1", params == {(16384, 8, 1)}, params)

plain_hits = [u.get("username") for u in users
              if isinstance(u.get("password"), str) and u["password"] in ("admin", "demo", "")]
c.check("no record stores the obvious plaintext", not plain_hits, plain_hits)

print()
print("== the hash is not handed out ==")
st, body = api("GET", "/api/users")
c.check("GET /api/users is readable", st == 200, st)
leaked = [u for u in (body or []) if isinstance(u, dict) and "password" in u]
c.check("no password field in the public user list", not leaked, leaked)
c.check("the list still identifies users",
        bool(body) and all("username" in u for u in body), body)

print()
print("== login goes through the hash (shared mode: the gate is actually on) ==")
# The grader mints its own account inside a throwaway copy of data/, so these
# checks never touch the real user store and never assume a real password.
PROBE_USER, PROBE_PW = "grade_probe", "probe-secret-42"

root = temp_dir(prefix="lt_b2_")
inst = None
try:
    d = copy_data_dir(os.path.join(root, "data_copy"))
    with open(os.path.join(d, "users.json"), encoding="utf-8") as f:
        probe_users = json.load(f)
    with open(os.path.join(d, "users.json"), "w", encoding="utf-8") as f:
        json.dump(probe_users + [
            {"userId": "user_grade_probe", "username": PROBE_USER,
             "password": scrypt_hash(PROBE_PW), "isAdmin": False}], f)
    bdir = os.path.join(root, "backup")
    os.makedirs(bdir, exist_ok=True)
    inst = run_instance(d, bdir, {"LITETASK_DEV_LOGIN": "0"}, keep=True)
    base = "http://localhost:%d" % inst["port"]
    c.check("shared-mode instance started", inst["ready"], inst["output"][-300:])

    st, body = http_at(base, "POST", "/api/login",
                       {"username": PROBE_USER, "password": PROBE_PW})
    c.check("correct password accepted", st == 200, (st, body))
    st, _ = http_at(base, "POST", "/api/login",
                    {"username": PROBE_USER, "password": PROBE_PW + " "})
    c.check("whitespace-padded password rejected", st == 401, st)
    st, _ = http_at(base, "POST", "/api/login",
                    {"username": PROBE_USER, "password": ""})
    c.check("empty password rejected", st == 401, st)
    st, _ = http_at(base, "POST", "/api/login", {"username": PROBE_USER})
    c.check("no password at all rejected", st == 401, st)
    st, _ = http_at(base, "POST", "/api/login",
                    {"username": "nobody", "password": PROBE_PW})
    c.check("unknown user rejected", st == 401, st)
finally:
    if inst and inst.get("proc"):
        stop_instance(inst["proc"])
    import shutil
    shutil.rmtree(root, ignore_errors=True)

print()
print("== the write path hashes too (source-level) ==")
# B2's password crypto now lives in lib/config.js (modular foundation, route ①):
# scan server.js AND lib/*.js so the static assertions follow the relocated code.
_src_parts = [open(os.path.join(ROOT, "server.js"), encoding="utf-8").read()]
for _f in sorted(glob.glob(os.path.join(ROOT, "lib", "*.js"))):
    _src_parts.append(open(_f, encoding="utf-8").read())
src = "\n".join(_src_parts)
c.check("hashing uses crypto.scryptSync", "crypto.scryptSync" in src, None)
c.check("login compares via verifyPassword", "verifyPassword(password" in src, None)
c.check("no plaintext equality check on the stored password",
        not re.search(r"\.password\s*===\s*(plain|password|cleanPassword)\b", src), None)
c.check("reset-password writes through hashPassword",
        "users[targetIndex].password = hashPassword(" in src, None)
c.check("legacy plaintext records are migrated at startup",
        "One-time startup migration" in src, None)

c.finish()
