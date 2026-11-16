# -*- coding: utf-8 -*-
"""P2-3 grader: an idempotent write answers with an authoritative rev."""
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (  # noqa: E402
    Checker, copy_data_dir, http_at, run_instance, stop_instance, temp_dir,
)

NAME = "p2-rev-authority"
c = Checker(NAME)
json_out = None
if "--json" in sys.argv:
    i = sys.argv.index("--json")
    if i + 1 < len(sys.argv):
        json_out = sys.argv[i + 1]

ADMIN = "user_admin"
LID = "probe_rev"


def item(iid):
    return {"itemId": iid, "title": iid, "isDone": False, "status": "open",
            "statusHistory": [], "blockedReason": "", "dueDate": "",
            "priority": "Medium", "assignedTo": "admin", "createdBy": "admin",
            "createdByAgent": "AI Agent", "createdById": ADMIN,
            "createdAt": "2026-11-01 00:00", "closedBy": None, "closedById": None,
            "closedAt": None, "localDirectory": "", "localDirectories": [],
            "comment": "", "subTasks": []}


def start(tag):
    tmp = temp_dir(prefix="lt_p2_rev_%s_" % tag)
    data = copy_data_dir(os.path.join(tmp, "inst"))
    shared = os.path.join(data, "shared_lists")
    os.makedirs(shared, exist_ok=True)
    # Deliberately stale rev: content hash will differ from the stored value.
    doc = {"listId": LID, "listName": "P2 REV", "category": "test",
           "rev": "stale-rev", "items": [item("r1"), item("r2")]}
    with open(os.path.join(shared, LID + ".json"), "w", encoding="utf-8") as f:
        json.dump(doc, f)
    logs = os.path.join(tmp, "logs")
    env = {"LITETASK_AUTO_ARCHIVE": "0", "LITETASK_BACKUP_MIRROR": "0",
           "LITETASK_LOG_DIR": logs,
           "LITETASK_AUDIT_FILE": os.path.join(logs, "audit.log")}
    inst = run_instance(data, os.path.join(tmp, "backup"), env,
                        wait_after_ready=2.0, timeout=60, keep=True)
    return {"inst": inst, "tmp": tmp, "data": data,
            "base": "http://127.0.0.1:%d" % inst["port"],
            "file": os.path.join(shared, LID + ".json")}


def stat(path):
    st = os.stat(path)
    b = open(path, "rb").read()
    return hashlib.sha256(b).hexdigest(), st.st_mtime_ns


ctx = None
try:
    ctx = start("main")
    b = ctx["base"]
    c.check("instance started", ctx["inst"]["ready"], ctx["inst"]["output"][-200:])
    st, doc = http_at(b, "GET", "/api/lists/" + LID)
    c.check("GET exposes a computed rev", st == 200 and bool(doc.get("rev")), (st, doc.get("rev")))

    # First write normalises sanitizeRelatesTo/localDirectories (an existing
    # contract), so make the fixture canonical before exercising idempotency.
    st, _ = http_at(b, "PUT", "/api/lists/" + LID,
                    {"type": "UPDATE_ITEMS", "userId": ADMIN,
                     "items": doc.get("items"), "force": False})
    st, doc = http_at(b, "GET", "/api/lists/" + LID)
    authoritative = doc.get("rev")
    c.check("normalised list has an authoritative rev", st == 200 and bool(authoritative),
            (st, authoritative))
    # Re-introduce a deliberately stale on-disk rev without touching items.
    raw = json.load(open(ctx["file"], encoding="utf-8"))
    raw["rev"] = "stale-rev"
    with open(ctx["file"], "w", encoding="utf-8") as f:
        json.dump(raw, f)
    before = stat(ctx["file"])

    # whole-list idempotent write
    st, r = http_at(b, "PUT", "/api/lists/" + LID,
                    {"type": "UPDATE_ITEMS", "userId": ADMIN,
                     "items": doc.get("items"), "baseRev": authoritative, "force": False})
    c.check("idempotent whole-list write returns 200", st == 200, (st, r))
    c.check("whole-list response rev is the authoritative rev",
            isinstance(r, dict) and r.get("rev") == authoritative, (r.get("rev"), authoritative))
    st2, doc2 = http_at(b, "GET", "/api/lists/" + LID)
    c.check("write response rev equals the subsequent GET rev",
            r.get("rev") == doc2.get("rev"), (r.get("rev"), doc2.get("rev")))
    raw = json.load(open(ctx["file"], encoding="utf-8"))
    c.check("the stale on-disk rev is left untouched", raw.get("rev") == "stale-rev", raw.get("rev"))
    c.check("idempotent write touches no bytes or mtime", stat(ctx["file"]) == before,
            (stat(ctx["file"])[0][:8], before[0][:8]))

    # stale baseRev still conflicts
    st, r = http_at(b, "PUT", "/api/lists/" + LID,
                    {"type": "UPDATE_ITEMS", "userId": ADMIN,
                     "items": doc.get("items"), "baseRev": "definitely-stale", "force": False})
    c.check("a stale baseRev is still 409 REV_CONFLICT",
            st == 409 and r.get("code") == "REV_CONFLICT", (st, r))

    # item-level idempotent write (items are canonical after the first write)
    st, one = http_at(b, "GET", "/api/lists/" + LID)
    target = (one.get("items") or [])[0]
    st, r = http_at(b, "PUT", "/api/lists/%s/items/%s" % (LID, target["itemId"]),
                    {"userId": ADMIN, "baseRev": one.get("rev"), "item": target})
    c.check("idempotent item write returns 200", st == 200, (st, r))
    c.check("item response rev is the authoritative rev",
            isinstance(r, dict) and r.get("rev") == one.get("rev"), (r.get("rev"), one.get("rev")))
    c.check("idempotent item write leaves the file untouched", stat(ctx["file"]) == before,
            "file changed")

    # repeated identical writes keep the same rev
    st, r2 = http_at(b, "PUT", "/api/lists/" + LID,
                     {"type": "UPDATE_ITEMS", "userId": ADMIN,
                      "items": doc.get("items"), "baseRev": authoritative, "force": False})
    c.check("two identical writes answer the same rev", r.get("rev") and r2.get("rev") == r.get("rev"),
            (r.get("rev"), r2.get("rev")))
finally:
    if ctx and ctx["inst"].get("proc"):
        stop_instance(ctx["inst"]["proc"])
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump({"grader": NAME, "result": "FAIL" if c.failed else "PASS",
                       "checks": c.passed + len(c.failed), "failures": c.failed},
                      f, ensure_ascii=False, indent=2)
    import shutil
    if ctx:
        shutil.rmtree(ctx["tmp"], ignore_errors=True)
c.finish()