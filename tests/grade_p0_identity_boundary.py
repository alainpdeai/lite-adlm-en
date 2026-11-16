# -*- coding: utf-8 -*-
"""
P0-2 grader: the identity boundary is server-side, not client-declared.

Two throwaway instances (local + shared) are started from the same seeded user
store. The recorded claim:

  * local mode: reads/writes work without a session; a *declared* identity must
    exist (unknown -> 403 UNKNOWN_ACTOR), and an undeclared write is anonymous
    in the audit (actor === null); admin rights come from users.json only.
  * shared mode: every data/admin endpoint requires the HTTP-only session
    cookie; a self-reported ?userId=user_admin is ignored; tampered, expired and
    missing sessions are 401; non-admin sessions cannot perform admin actions.
  * credentials never appear in access/audit logs or in /api/config|/api/health.

Run pre-fix and the shared-mode groups fail (the data surface is open) — that is
the non-vacuity proof. Destructive probes only ever target a throwaway list.
"""
import base64
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (  # noqa: E402
    Checker, copy_data_dir, http_at, http_at_headers, run_instance,
    stop_instance, temp_dir, temp_item,
)

NAME = "p0-identity-boundary"
c = Checker(NAME)

json_out = None
if "--json" in sys.argv:
    i = sys.argv.index("--json")
    if i + 1 < len(sys.argv):
        json_out = sys.argv[i + 1]


def seed_users(data_dir):
    users = [
        {"userId": "user_admin", "username": "admin",
         "password": base64.b64encode(b"admin").decode(), "isAdmin": True},
        {"userId": "user_tester", "username": "tester",
         "password": base64.b64encode(b"tester-pass").decode(), "isAdmin": False},
    ]
    with open(os.path.join(data_dir, "users.json"), "w", encoding="utf-8") as f:
        json.dump(users, f)


def start(tag, env_extra):
    tmp = temp_dir(prefix="lt_p0_id_%s_" % tag)
    data = copy_data_dir(os.path.join(tmp, "inst"))
    seed_users(data)
    logs = os.path.join(tmp, "logs")
    env = dict(env_extra or {})
    env.update({
        "LITETASK_LOG_DIR": logs,
        "LITETASK_AUDIT_FILE": os.path.join(logs, "audit.log"),
        "LITETASK_BACKUP_MIRROR": "0",
    })
    inst = run_instance(data, os.path.join(tmp, "backup"), env,
                        wait_after_ready=2.0, timeout=60, keep=True)
    return {"inst": inst, "tmp": tmp, "data": data, "logs": logs,
            "base": "http://127.0.0.1:%d" % inst["port"]}


def hardened(base):
    st, cfg = http_at(base, "GET", "/api/config")
    return bool(st == 200 and isinstance(cfg, dict)
                and "passwordless" in cfg and isinstance(cfg.get("securityModel"), dict))


def cookie_of(headers):
    raw = headers.get("Set-Cookie") or headers.get("set-cookie") or ""
    first = raw.split(",", 1)[0]
    return first.split(";", 1)[0].strip() if "=" in first else ""


local = shared = expired = noadmin = None
try:
    # ============================ local mode ============================
    local = start("local", {})
    b = local["base"]
    c.check("local instance started", local["inst"]["ready"], local["inst"]["output"][-300:])
    hard_local = hardened(b)

    st, cfg = http_at(b, "GET", "/api/config")
    c.check("local /api/config reports passwordless: true",
            st == 200 and cfg.get("passwordless") is True, (st, cfg))
    c.check("local security model is local-passwordless",
            (cfg.get("securityModel") or {}).get("mode") == "local-passwordless", cfg)
    c.check("local /api/config exposes the openFolder capability state",
            isinstance(cfg.get("openFolder"), dict), cfg)

    st, body = http_at(b, "GET", "/api/lists")
    c.check("local reads work with no session", st == 200, st)
    st, users = http_at(b, "GET", "/api/users")
    c.check("local /api/users works with no session", st == 200, st)

    anon_item = temp_item("p0-anon-write")
    st, body = http_at(b, "POST", "/api/lists/arch/items", {"item": anon_item})
    c.check("undeclared local write succeeds (anonymous compatibility)",
            st == 200, (st, body))

    st, audit = http_at(b, "GET", "/api/audit?userId=user_admin&limit=50")
    last = (audit or {}).get("entries", [])[-1] if st == 200 else {}
    c.check("the anonymous write is audited with actor === null",
            isinstance(last, dict) and last.get("actor") is None, last)

    st, body = http_at(b, "POST", "/api/lists/arch/items",
                       {"item": temp_item("p0-ghost-write"), "userId": "user_ghost"})
    c.check("a declared-but-unknown identity is 403 UNKNOWN_ACTOR",
            st == 403 and isinstance(body, dict) and body.get("code") == "UNKNOWN_ACTOR",
            (st, body))
    st, body = http_at(b, "GET", "/api/lists?userId=user_ghost")
    c.check("the same rule applies to reads", st == 403, (st, body))

    st, body = http_at(b, "POST", "/api/lists/arch/items",
                       {"item": temp_item("p0-declared-write"), "userId": "user_admin"})
    c.check("a declared, existing identity still works in local mode", st == 200, (st, body))

    # admin rights must come from users.json, not from the literal user_admin
    noadmin = start("noadmin", {})
    with open(os.path.join(noadmin["data"], "users.json"), encoding="utf-8") as f:
        users_doc = json.load(f)
    users_doc = [u for u in users_doc if u.get("userId") != "user_admin"]
    with open(os.path.join(noadmin["data"], "users.json"), "w", encoding="utf-8") as f:
        json.dump(users_doc, f)
    nb = noadmin["base"]
    # the running instance created users.json before we edited it; restart it.
    stop_instance(noadmin["inst"]["proc"])
    noadmin["inst"] = run_instance(noadmin["data"], os.path.join(noadmin["tmp"], "backup2"), {
        "LITETASK_LOG_DIR": noadmin["logs"],
        "LITETASK_AUDIT_FILE": os.path.join(noadmin["logs"], "audit.log"),
        "LITETASK_BACKUP_MIRROR": "0",
    }, wait_after_ready=2.0, timeout=60, keep=True)
    nb = "http://localhost:%d" % noadmin["inst"]["port"]
    st, created = http_at(nb, "POST", "/api/lists", {"listName": "P0-ADMIN-PROBE"})
    probe_lid = created.get("listId") if isinstance(created, dict) else None
    st, body = http_at(nb, "DELETE",
                       "/api/lists/%s?userId=user_admin&confirm=true" % probe_lid)
    c.check("after removing the admin record, user_admin loses admin rights (403)",
            st == 403, (st, body))

    # ============================ shared mode ============================
    shared = start("shared", {"LITETASK_DEV_LOGIN": "0"})
    sb = shared["base"]
    c.check("shared instance started", shared["inst"]["ready"], shared["inst"]["output"][-300:])
    hard_shared = hardened(sb)

    st, cfg = http_at(sb, "GET", "/api/config")
    c.check("shared /api/config reports passwordless: false",
            st == 200 and cfg.get("passwordless") is False, (st, cfg))
    c.check("shared security model is shared-authenticated",
            (cfg.get("securityModel") or {}).get("mode") == "shared-authenticated", cfg)

    for path in ("/api/lists", "/api/users", "/api/audit",
                 "/api/admin/users", "/api/integrity", "/api/categories"):
        st, body = http_at(sb, "GET", path)
        c.check("shared mode: GET %s without a session is 401" % path, st == 401, (st, body))

    st, body = http_at(sb, "GET", "/api/lists?userId=user_admin")
    c.check("shared mode ignores a self-reported userId (still 401)", st == 401, (st, body))

    write_probes = [
        ("POST", "/api/lists", {"listName": "nope"}),
        ("POST", "/api/lists/arch/items", {"item": temp_item("p0-shared-write")}),
        ("POST", "/api/lists/arch/archive", {"confirm": True}),
        ("POST", "/api/admin/users", {"username": "x", "password": "yyy"}),
        ("POST", "/api/admin/reset-password", {"targetUserId": "user_tester",
                                               "newPassword": "zzz"}),
    ]
    write_ok = True
    for method, path, body in write_probes:
        st, bd = http_at(sb, method, path, body)
        if st != 401:
            write_ok = False
    c.check("shared mode: every write/admin probe without a session is 401", write_ok)

    st, body = http_at(sb, "POST", "/api/login",
                       {"username": "admin", "password": "wrong"})
    c.check("wrong password is 401 in shared mode", st == 401, (st, body))

    st, body, hdrs = http_at_headers(sb, "POST", "/api/login",
                                     {"username": "admin", "password": "admin"})
    setc = (hdrs.get("Set-Cookie") or hdrs.get("set-cookie") or "")
    cookie = cookie_of(hdrs)
    c.check("correct password issues a session cookie", st == 200 and bool(cookie), (st, setc))
    c.check("the cookie is HttpOnly, SameSite and Path=/",
            ("HttpOnly" in setc and "SameSite" in setc and "Path=/" in setc), setc)
    c.check("the login body stays {userId, username, isAdmin}",
            isinstance(body, dict) and set(body.keys()) == {"userId", "username", "isAdmin"},
            body)

    if cookie:
        st, body = http_at(sb, "GET", "/api/lists", cookie=cookie)
        c.check("a valid session reads the board", st == 200, (st, body))
        tampered = cookie[:-1] + ("A" if cookie[-1] != "A" else "B")
        st, body = http_at(sb, "GET", "/api/lists", cookie=tampered)
        c.check("a tampered signature is 401", st == 401, (st, body))
        st, body = http_at(sb, "GET", "/api/lists?token=%s" % cookie.split("=", 1)[-1])
        c.check("a token in the query string is not accepted", st == 401, (st, body))
    else:
        for label in ("a valid session reads the board",
                      "a tampered signature is 401",
                      "a token in the query string is not accepted"):
            c.check(label, False, "no session cookie was issued (legacy implementation)")

    st, body, hdrs = http_at_headers(sb, "POST", "/api/login",
                                     {"username": "tester", "password": "tester-pass"})
    tester_cookie = cookie_of(hdrs)
    if tester_cookie:
        st, body = http_at(sb, "DELETE",
                           "/api/lists/arch?confirm=true&userId=user_admin",
                           cookie=tester_cookie)
        c.check("a non-admin session cannot delete a list, even while claiming "
                "user_admin (403)", st == 403, (st, body))
    else:
        c.check("a non-admin session cannot delete a list, even while claiming "
                "user_admin (403)", False, "no tester cookie")

    # expired sessions do not degrade to "userId is enough"
    expired = start("expired", {"LITETASK_DEV_LOGIN": "0",
                                "LITETASK_SESSION_TTL_MS": "80"})
    eb = expired["base"]
    st, body, hdrs = http_at_headers(eb, "POST", "/api/login",
                                     {"username": "admin", "password": "admin"})
    ecookie = cookie_of(hdrs)
    if ecookie:
        time.sleep(0.4)
        st, body = http_at(eb, "GET", "/api/lists", cookie=ecookie)
        c.check("an expired session is 401 and never falls back to self-report",
                st == 401, (st, body))
    else:
        c.check("an expired session is 401 and never falls back to self-report",
                False, "no cookie issued")

    # credentials must not reach the logs or the public endpoints
    leak = ""
    for name in ("access.log", "audit.log"):
        p = os.path.join(shared["logs"], name)
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                leak += f.read()
    st, cfg_txt, _ = http_at_headers(sb, "GET", "/api/config")
    st2, health_txt, _ = http_at_headers(sb, "GET", "/api/health")
    public = json.dumps([cfg_txt, health_txt], ensure_ascii=False, default=str)
    c.check("the session cookie value never appears in access/audit logs",
            (not cookie) or (cookie.split("=", 1)[-1] not in leak), "cookie leaked")
    c.check("no credential material appears in /api/config or /api/health",
            "scrypt$" not in public and "lt_session" not in public, "credential leaked")

finally:
    for ctx in (local, shared, expired, noadmin):
        if ctx and ctx.get("inst") and ctx["inst"].get("proc"):
            stop_instance(ctx["inst"]["proc"])
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump({"name": NAME, "passed": c.passed, "failed": c.failed},
                      f, ensure_ascii=False, indent=2)
    import shutil
    for ctx in (local, shared, expired, noadmin):
        if ctx:
            shutil.rmtree(ctx["tmp"], ignore_errors=True)

c.finish()