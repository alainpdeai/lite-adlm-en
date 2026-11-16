# -*- coding: utf-8 -*-
"""
P0-1 grader: list identifiers can never address a file outside the data dirs.

The recorded claim is structural, not incidental:

  * every /api/lists/:id and /api/archive/:id route refuses a malformed
    identifier with 400 INVALID_LIST_ID *before* touching the filesystem;
  * a traversal-shaped identifier cannot read data/users.json and a delete
    attempt cannot remove it;
  * a legal but absent identifier is 404 LIST_NOT_FOUND (not 400, not 200);
  * listings only expose well-formed list documents;
  * a bad snapshot stamp is 400 INVALID_STAMP before the archive lock.

Run against the pre-fix implementation this file fails hard (that is its
non-vacuity proof). It never performs the destructive delete on a legacy
instance: reading is safe, deleting users.json is not.
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (  # noqa: E402
    Checker, copy_data_dir, http_at, run_instance, stop_instance,
    temp_dir, temp_item,
)

NAME = "p0-path-isolation"
c = Checker(NAME)

json_out = None
if "--json" in sys.argv:
    i = sys.argv.index("--json")
    if i + 1 < len(sys.argv):
        json_out = sys.argv[i + 1]

INST = {"keep": True}
root = temp_dir(prefix="lt_p0_path_")
data_dir = os.path.join(root, "inst", "data")
os.makedirs(os.path.dirname(data_dir), exist_ok=True)
copy_data_dir(os.path.dirname(data_dir))
inst = None


def hardened(base):
    st, cfg = http_at(base, "GET", "/api/config")
    return bool(st == 200 and isinstance(cfg, dict)
                and "passwordless" in cfg
                and isinstance(cfg.get("securityModel"), dict)
                and isinstance(cfg.get("openFolder"), dict))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


try:
    inst = run_instance(data_dir, os.path.join(root, "backup"), {}, keep=True)
    base = "http://127.0.0.1:%d" % inst["port"]
    c.check("P0 test instance started", inst["ready"], inst["output"][-300:])
    hard = hardened(base) if inst["ready"] else False
    print("     implementation: %s" % ("hardened" if hard else "LEGACY (pre-fix)"))

    users_file = os.path.join(data_dir, "users.json")
    users_hash = sha256_file(users_file) if os.path.exists(users_file) else None

    # ---- 1. malformed identifiers: every route refuses with the same code ----
    bad_ids = [
        "..", "..%2Fusers", "..%5Cusers", "%2e%2e%2fusers", "a%00b",
        "%E4%B8%AD%E6%96%87", "x" * 33, ".hidden", "a%20b",
    ]
    captures = []
    for raw in bad_ids:
        probes = [
            ("GET", "/api/lists/%s" % raw, None),
            ("PUT", "/api/lists/%s" % raw,
             {"type": "UPDATE_ITEMS", "items": [], "userId": "user_admin"}),
            ("POST", "/api/lists/%s/items" % raw,
             {"item": temp_item("p0-invalid-%s" % abs(hash(raw))), "userId": "user_admin"}),
            ("GET", "/api/lists/%s/archive-preview" % raw, None),
            ("GET", "/api/archive/%s" % raw, None),
        ]
        ok = True
        for method, path, body in probes:
            st, bd = http_at(base, method, path, body)
            captures.append(bd)
            if not (st == 400 and isinstance(bd, dict) and bd.get("code") == "INVALID_LIST_ID"):
                ok = False
        c.check("malformed id %r is rejected on all five routes (400 INVALID_LIST_ID)"
                % raw, ok, "" if ok else "at least one route answered something else")

    # ---- 2. traversal delete: refuse, and prove users.json is untouched ----
    if hard:
        st, _ = http_at(base, "DELETE",
                        "/api/lists/..%2Fusers?userId=user_admin&confirm=true")
    else:
        st = 0          # never execute this on an unguarded instance
    c.check("traversal delete is refused with 400 INVALID_LIST_ID", st == 400, (st,))
    now_hash = sha256_file(users_file) if os.path.exists(users_file) else None
    c.check("data/users.json still exists and is byte-identical",
            hard and now_hash is not None and now_hash == users_hash,
            ("legacy: probe skipped" if not hard else (now_hash == users_hash)))

    # ---- 3. rejection bodies carry no file content, path, or credential ----
    def dirty(v):
        s = json.dumps(v, ensure_ascii=False, default=str) if not isinstance(v, str) else v
        return ("scrypt$" in s or re.search(r"[A-Za-z]:\\\\", s) is not None
                or "node:internal" in s)
    c.check("no rejection body leaks a password hash, drive path or stack trace",
            not any(dirty(x) for x in captures),
            "a response carried sensitive material")

    # ---- 4. legal-but-absent identifier is 404 LIST_NOT_FOUND ----
    for lid in ("99", "does-not-exist"):
        st, bd = http_at(base, "GET", "/api/lists/%s" % lid)
        c.check("legal-but-absent id %r answers 404 LIST_NOT_FOUND" % lid,
                st == 404 and isinstance(bd, dict) and bd.get("code") == "LIST_NOT_FOUND",
                (st, bd))

    # ---- 5. existing identifiers keep working ----
    st, _ = http_at(base, "GET", "/api/lists/arch")
    c.check("GET /api/lists/arch still answers 200", st == 200, st)
    item_id = "p0-path-probe-item"
    st, bd = http_at(base, "POST", "/api/lists/arch/items",
                     {"item": temp_item(item_id), "userId": "user_admin"})
    c.check("a normal item write to arch still answers 200", st == 200, (st, bd))

    # ---- 6. listing isolation ----
    shared = os.path.join(data_dir, "shared_lists")
    with open(os.path.join(shared, "bad.name.json"), "w", encoding="utf-8") as f:
        json.dump({"listId": "bad.name", "listName": "evil", "items": []}, f)
    with open(os.path.join(shared, "evil.json.bak"), "w", encoding="utf-8") as f:
        f.write("{}")
    st, lists = http_at(base, "GET", "/api/lists")
    ids = [x.get("listId") for x in (lists or []) if isinstance(x, dict)]
    c.check("every listed id matches the whitelist",
            st == 200 and all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}", str(i)) for i in ids),
            ids)
    c.check("users / categories are never listed as task lists",
            ("users" not in ids) and ("categories" not in ids), ids)
    c.check("a file whose name is not a legal list id is not listed",
            "bad.name" not in ids, ids)

    # ---- 7. snapshot stamp is a first-class identifier too ----
    for stamp in ("../users", "2026-01-01T00:00:00.000Z/../x"):
        st, bd = http_at(base, "POST", "/api/lists/arch/archive-restore",
                         {"stamp": stamp, "userId": "user_admin", "confirm": True})
        c.check("bad snapshot stamp %r is 400 INVALID_STAMP" % stamp,
                st == 400 and isinstance(bd, dict) and bd.get("code") == "INVALID_STAMP",
                (st, bd))

    # ---- 8. a rejected request leaves no lock or state behind ----
    st, bd = http_at(base, "POST", "/api/lists/arch/items",
                     {"item": temp_item("p0-after-reject"), "userId": "user_admin"})
    c.check("a legal write immediately after rejections still answers 200", st == 200,
            (st, bd))

finally:
    if inst and inst.get("proc"):
        stop_instance(inst["proc"])
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump({"name": NAME, "passed": c.passed, "failed": c.failed},
                      f, ensure_ascii=False, indent=2)
    import shutil
    shutil.rmtree(root, ignore_errors=True)

c.finish()