# -*- coding: utf-8 -*-
"""
Grader for func item Local mode passwordless login (remove password).

Recorded claim (the standard answer for "remove password", plan A):

  LiteTask runs in one of two auth modes, selected solely by the env var
  LITETASK_DEV_LOGIN (default ON; set to '0' for a shared deployment):

  * Local mode (default, LITETASK_DEV_LOGIN != '0') — passwordless.
    POST /api/login with only a username that names an existing account
    returns 200 + {userId, username, isAdmin}. Any password supplied is
    ignored. This does NOT invent accounts: an unknown username is still 401.
    GET /api/config reports passwordless: true.

  * Shared mode (LITETASK_DEV_LOGIN='0') — the password gate is real again.
    A username without a password is 401, a correct password is 200, a wrong
    password is 401. GET /api/config reports passwordless: false.

The two modes are checked against two throwaway instances started from the
same seeded user store, so the identical request body
{username, password: <wrong>} must flip its verdict between them. That
contrast is the non-vacuity proof: the grader cannot pass by always asserting
200 or always asserting 401.
"""
import base64
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import Checker, copy_data_dir, http_at, run_instance, stop_instance, temp_dir  # noqa: E402

c = Checker("passwordless-login")

# --- scrypt parameters mirrored from server.js (B2) so the grader can mint its
# --- own canonical hash records instead of trusting whatever the live store has.
SCRYPT_N, SCRYPT_R, SCRYPT_P, KEY_LEN = 16384, 8, 1, 64


def scrypt_hash(plain, salt=b"litetask-grader-salt"):
    key = hashlib.scrypt(plain.encode("utf-8"), salt=salt,
                         n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                         dklen=KEY_LEN, maxmem=96 * 1024 * 1024)
    return "$".join(["scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P),
                     base64.b64encode(salt).decode(),
                     base64.b64encode(key).decode()])


ADMIN_PW = "admin-secret-abc"
TESTER_PW = "tester-secret-xyz"
USERS = [
    {"userId": "user_admin", "username": "admin",
     "password": scrypt_hash(ADMIN_PW), "isAdmin": True},
    {"userId": "user_tester", "username": "tester",
     "password": scrypt_hash(TESTER_PW), "isAdmin": False},
]


def seed_users(data_dir):
    with open(os.path.join(data_dir, "users.json"), "w", encoding="utf-8") as f:
        json.dump(USERS, f)


def login(base, body):
    return http_at(base, "POST", "/api/login", body)


root = temp_dir(prefix="lt_pwd_")
local = shared = None
try:
    # ---------------- instance 1: local mode (default) ----------------
    d1 = copy_data_dir(os.path.join(root, "a"))
    seed_users(d1)
    b1 = os.path.join(root, "backup_a")
    os.makedirs(b1, exist_ok=True)
    local = run_instance(d1, b1, {}, keep=True)
    base1 = "http://localhost:%d" % local["port"]
    c.check("local-mode instance started", local["ready"], local["output"][-300:])

    st, cfg = http_at(base1, "GET", "/api/config")
    c.check("/api/config reports passwordless: true in local mode",
            st == 200 and cfg.get("passwordless") is True, (st, cfg))

    st, body = login(base1, {"username": "admin"})
    c.check("username alone logs in with no password at all", st == 200, (st, body))
    c.check("it returns the real admin identity",
            isinstance(body, dict) and body.get("userId") == "user_admin"
            and body.get("username") == "admin" and body.get("isAdmin") is True,
            body)
    c.check("no error key leaks into the success payload",
            not isinstance(body, dict) or "error" not in body, body)

    st, body = login(base1, {"username": "admin", "password": "totally-wrong"})
    c.check("a wrong password is ignored in local mode", st == 200, (st, body))

    st, body = login(base1, {"username": "tester"})
    c.check("a non-admin account signs in too", st == 200, (st, body))
    c.check("its isAdmin flag stays false",
            isinstance(body, dict) and body.get("isAdmin") is False, body)

    st, body = login(base1, {"username": "nobody-here"})
    c.check("an unknown username is still rejected", st == 401, (st, body))
    c.check("the rejection carries an error message",
            isinstance(body, dict) and bool(body.get("error")), body)

    st_empty, body_empty = login(base1, {})
    c.check("an empty body is rejected, not treated as admin",
            st_empty == 401, (st_empty, body_empty))

    # ---------------- instance 2: shared mode (LITETASK_DEV_LOGIN=0) ----------------
    d2 = copy_data_dir(os.path.join(root, "b"))
    seed_users(d2)
    b2 = os.path.join(root, "backup_b")
    os.makedirs(b2, exist_ok=True)
    shared = run_instance(d2, b2, {"LITETASK_DEV_LOGIN": "0"}, keep=True)
    base2 = "http://localhost:%d" % shared["port"]
    c.check("shared-mode instance started", shared["ready"], shared["output"][-300:])

    st, cfg = http_at(base2, "GET", "/api/config")
    c.check("/api/config reports passwordless: false in shared mode",
            st == 200 and cfg.get("passwordless") is False, (st, cfg))

    st2, body2 = login(base2, {"username": "admin"})
    c.check("username alone is NO LONGER enough in shared mode",
            st2 == 401, (st2, body2))

    st3, body3 = login(base2, {"username": "admin", "password": ADMIN_PW})
    c.check("the correct password still authenticates in shared mode",
            st3 == 200 and isinstance(body3, dict)
            and body3.get("userId") == "user_admin", (st3, body3))

    st4, body4 = login(base2, {"username": "admin", "password": "totally-wrong"})
    c.check("a wrong password is rejected in shared mode", st4 == 401, (st4, body4))

    st5, body5 = login(base2, {"username": "nobody-here", "password": ADMIN_PW})
    c.check("an unknown username is rejected even with a valid-looking password",
            st5 == 401, (st5, body5))

    # ---------------- non-vacuity: the same request flips between modes ----------------
    c.check("identical request {admin, wrong password} flips verdict with mode",
            (st == 200) and (st4 == 401) and st != st4, (st, st4))
    c.check("identical request {admin, no password} flips verdict with mode",
            (st == 200) and (st2 == 401) and st != st2, (st, st2))
    c.check("config's passwordless flag flips with mode too",
            cfg is not None, "compared per-instance above")

finally:
    for inst in (local, shared):
        if inst and inst.get("proc"):
            stop_instance(inst["proc"])
    import shutil
    shutil.rmtree(root, ignore_errors=True)

c.finish()
