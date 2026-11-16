# -*- coding: utf-8 -*-
"""P2-7 grader: user enumeration is minimised in shared mode."""
import base64
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (  # noqa: E402
    Checker, copy_data_dir, http_at, http_at_headers, run_instance,
    stop_instance, temp_dir,
)

NAME = "p2-users-visibility"
c = Checker(NAME)
json_out = None
if "--json" in sys.argv:
    i = sys.argv.index("--json")
    if i + 1 < len(sys.argv):
        json_out = sys.argv[i + 1]


def seed(data):
    users = [
        {"userId": "user_admin", "username": "admin",
         "password": base64.b64encode(b"admin").decode(), "isAdmin": True},
        {"userId": "user_a", "username": "alice",
         "password": base64.b64encode(b"alice-pass").decode(), "isAdmin": False},
        {"userId": "user_b", "username": "bob",
         "password": base64.b64encode(b"bob-pass").decode(), "isAdmin": False},
        {"userId": "user_c", "username": "carol",
         "password": base64.b64encode(b"carol-pass").decode(), "isAdmin": False},
    ]
    with open(os.path.join(data, "users.json"), "w", encoding="utf-8") as f:
        json.dump(users, f)
    shared = os.path.join(data, "shared_lists")
    os.makedirs(shared, exist_ok=True)
    def item(iid, creator, assignee):
        return {"itemId": iid, "title": iid, "isDone": False, "status": "open",
                "statusHistory": [], "blockedReason": "", "dueDate": "",
                "priority": "Medium", "assignedTo": assignee, "createdBy": creator,
                "createdByAgent": "AI Agent", "createdById": "user_" + creator,
                "createdAt": "2026-11-01 00:00", "closedBy": None,
                "closedById": None, "closedAt": None, "localDirectory": "",
                "localDirectories": [], "comment": "", "subTasks": []}
    docs = {
        "a_only": [item("a1", "alice", "alice")],
        "b_only": [item("b1", "bob", "bob")],
        "shared_ab": [item("s1", "alice", "bob")],
    }
    for lid, items in docs.items():
        with open(os.path.join(shared, lid + ".json"), "w", encoding="utf-8") as f:
            json.dump({"listId": lid, "listName": lid, "category": "test", "items": items}, f)


def start(tag, env_extra):
    tmp = temp_dir(prefix="lt_p2_users_%s_" % tag)
    data = copy_data_dir(os.path.join(tmp, "inst"))
    seed(data)
    logs = os.path.join(tmp, "logs")
    env = {"LITETASK_AUTO_ARCHIVE": "0", "LITETASK_BACKUP_MIRROR": "0",
           "LITETASK_LOG_DIR": logs,
           "LITETASK_AUDIT_FILE": os.path.join(logs, "audit.log")}
    env.update(env_extra or {})
    inst = run_instance(data, os.path.join(tmp, "backup"), env,
                        wait_after_ready=2.0, timeout=60, keep=True)
    return {"inst": inst, "tmp": tmp, "base": "http://127.0.0.1:%d" % inst["port"]}


def login(base, user, password):
    st, _, hdrs = http_at_headers(base, "POST", "/api/login",
                                  {"username": user, "password": password})
    setc = (hdrs.get("Set-Cookie") or hdrs.get("set-cookie") or "")
    return st, (setc.split(";", 1)[0] if "=" in setc else "")


local = shared = None
try:
    local = start("local", {})
    st, users = http_at(local["base"], "GET", "/api/users")
    c.check("local mode still lists everyone without a session",
            st == 200 and len(users) == 4, (st, len(users or [])))

    shared = start("shared", {"LITETASK_DEV_LOGIN": "0"})
    b = shared["base"]
    st, _ = http_at(b, "GET", "/api/users")
    c.check("shared mode refuses /api/users without a session", st == 401, st)

    st, cookie = login(b, "alice", "alice-pass")
    c.check("shared login issues a cookie", st == 200 and bool(cookie), (st, cookie))
    st, a_users = http_at(b, "GET", "/api/users", cookie=cookie)
    names = [u.get("username") for u in (a_users or [])]
    c.check("alice sees herself and her collaborators", st == 200
            and "alice" in names and "bob" in names, names)
    c.check("alice does not see unrelated carol", "carol" not in names, names)
    c.check("user objects expose only userId/username",
            all(set(u.keys()) == {"userId", "username"} for u in (a_users or [])), a_users)

    st, _ = http_at(b, "GET", "/api/users?userId=user_b", cookie=cookie)
    st, widened = http_at(b, "GET", "/api/users?userId=user_b", cookie=cookie)
    c.check("a request userId cannot widen the result",
            "carol" not in [u.get("username") for u in (widened or [])], widened)

    st, admin_cookie = login(b, "admin", "admin")
    st, all_users = http_at(b, "GET", "/api/users", cookie=admin_cookie)
    c.check("admin sees the full user store", st == 200 and len(all_users) == 4,
            (st, len(all_users or [])))
    raw = json.dumps(all_users, ensure_ascii=False)
    c.check("no credential material leaks", "scrypt$" not in raw
            and "password" not in raw and "isAdmin" not in raw, raw[:120])
finally:
    for ctx in (local, shared):
        if ctx and ctx["inst"].get("proc"):
            stop_instance(ctx["inst"]["proc"])
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump({"grader": NAME, "result": "FAIL" if c.failed else "PASS",
                       "checks": c.passed + len(c.failed), "failures": c.failed},
                      f, ensure_ascii=False, indent=2)
    import shutil
    for ctx in (local, shared):
        if ctx:
            shutil.rmtree(ctx["tmp"], ignore_errors=True)
c.finish()