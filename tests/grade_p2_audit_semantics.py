# -*- coding: utf-8 -*-
"""P2-1/P2-2 grader: audit confirmation mark and real unarchive counts."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (  # noqa: E402
    Checker, copy_data_dir, http_at, run_instance, stop_instance, temp_dir,
)

NAME = "p2-audit-semantics"
c = Checker(NAME)
json_out = None
if "--json" in sys.argv:
    i = sys.argv.index("--json")
    if i + 1 < len(sys.argv):
        json_out = sys.argv[i + 1]

ADMIN = "user_admin"
LID = "probe_audit"


def item(iid, done):
    return {"itemId": iid, "title": iid, "isDone": done,
            "status": "done" if done else "open", "statusHistory": [],
            "blockedReason": "", "dueDate": "", "priority": "Medium",
            "assignedTo": "admin", "createdBy": "admin", "createdByAgent": "AI Agent",
            "createdById": ADMIN, "createdAt": "2026-11-01 00:00",
            "closedBy": "admin" if done else None, "closedById": ADMIN if done else None,
            "closedAt": "2026-11-01 00:00" if done else None,
            "localDirectory": "", "localDirectories": [], "comment": "", "subTasks": []}


def start(tag):
    tmp = temp_dir(prefix="lt_p2_audit_%s_" % tag)
    data = copy_data_dir(os.path.join(tmp, "inst"))
    os.makedirs(os.path.join(data, "shared_lists"), exist_ok=True)
    with open(os.path.join(data, "shared_lists", LID + ".json"), "w", encoding="utf-8") as f:
        json.dump({"listId": LID, "listName": "P2 AUDIT", "category": "test",
                   "items": [item("a%d" % i, i < 3) for i in range(5)]}, f)
    logs = os.path.join(tmp, "logs")
    env = {"LITETASK_AUTO_ARCHIVE": "0", "LITETASK_BACKUP_MIRROR": "0",
           "LITETASK_LOG_DIR": logs,
           "LITETASK_AUDIT_FILE": os.path.join(logs, "audit.log")}
    inst = run_instance(data, os.path.join(tmp, "backup"), env,
                        wait_after_ready=2.0, timeout=60, keep=True)
    return {"inst": inst, "tmp": tmp, "base": "http://127.0.0.1:%d" % inst["port"],
            "data": data, "audit": os.path.join(logs, "audit.log")}


def entries(path):
    out = []
    if os.path.exists(path):
        for line in open(path, encoding="utf-8", errors="replace"):
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


ctx = None
try:
    ctx = start("main")
    b = ctx["base"]
    c.check("instance started", ctx["inst"]["ready"], ctx["inst"]["output"][-200:])

    # unconfirmed delete: 400 and no success audit
    st, _ = http_at(b, "DELETE", "/api/lists/%s?userId=%s" % (LID, ADMIN))
    c.check("unconfirmed delete is refused", st == 400, st)
    ok_delete = [e for e in entries(ctx["audit"])
                 if e.get("action") == "delete-list" and e.get("outcome") == "ok"]
    c.check("refused delete writes no success audit", not ok_delete, ok_delete[-1:])

    # confirmed delete must record explicit confirmation
    st, _ = http_at(b, "DELETE",
                    "/api/lists/%s?userId=%s&confirm=true" % (LID, ADMIN))
    c.check("confirmed delete succeeds", st == 200, st)
    del_entries = [e for e in entries(ctx["audit"])
                   if e.get("action") == "delete-list" and e.get("outcome") == "ok"]
    c.check("delete-list audit marks confirmed=explicit",
            bool(del_entries) and del_entries[-1].get("confirmed") == "explicit",
            del_entries[-1:] if del_entries else [])

    # ordinary write is not marked explicit
    ctx2 = start("ordinary")
    b2 = ctx2["base"]
    st, doc = http_at(b2, "GET", "/api/lists/" + LID)
    st, _ = http_at(b2, "PUT", "/api/lists/" + LID,
                    {"type": "UPDATE_ITEMS", "userId": ADMIN,
                     "items": doc.get("items"), "force": False})
    c.check("ordinary whole-list write still succeeds", st == 200, st)
    upd = [e for e in entries(ctx2["audit"])
           if e.get("action") == "update-items" and e.get("outcome") == "ok"]
    c.check("ordinary write stays confirmed=null",
            bool(upd) and upd[-1].get("confirmed") is None, upd[-1:] if upd else [])
    stop_instance(ctx2["inst"]["proc"])

    # unarchive note carries the real moved count, never '?'
    ctx3 = start("unarchive")
    b3 = ctx3["base"]
    st, r = http_at(b3, "POST", "/api/lists/%s/archive" % LID,
                    {"userId": ADMIN, "confirm": True})
    c.check("archive succeeds for fixture", st == 200 and r.get("moved") == 3, (st, r))
    st, r = http_at(b3, "POST", "/api/lists/%s/unarchive" % LID,
                    {"userId": ADMIN})
    c.check("unarchive succeeds", st == 200, (st, r))
    c.check("unarchive response has no legacy 'restored' key",
            isinstance(r, dict) and "restored" not in r, list((r or {}).keys()))
    c.check("unarchive response exposes moved/reattached/orphaned/archiveCount",
            isinstance(r, dict) and all(k in r for k in
                                        ("moved", "reattached", "orphaned", "archiveCount")), r)
    un = [e for e in entries(ctx3["audit"])
          if e.get("action") == "unarchive" and e.get("outcome") == "ok"]
    note = (un[-1].get("note") or "") if un else ""
    c.check("unarchive audit note contains the real moved count",
            bool(un) and "?" not in note and "restored" not in note
            and str(r.get("moved")) in note, note)

    st, r = http_at(b3, "POST", "/api/lists/%s/unarchive" % LID,
                    {"userId": ADMIN})
    un = [e for e in entries(ctx3["audit"])
          if e.get("action") == "unarchive" and e.get("outcome") == "ok"]
    note = (un[-1].get("note") or "") if un else ""
    c.check("a zero-move unarchive audit says 0, not '?'",
            st == 200 and r.get("moved") == 0 and "0 item" in note, (st, r, note))

    # refill the archive so the unknown-id path is reachable
    st, _ = http_at(b3, "POST", "/api/lists/%s/archive" % LID,
                    {"userId": ADMIN, "confirm": True})
    st, r = http_at(b3, "POST", "/api/lists/%s/unarchive" % LID,
                    {"userId": ADMIN, "itemIds": ["nope"]})
    c.check("unknown archived id is 400 UNKNOWN_ARCHIVED_ITEM",
            st == 400 and r.get("code") == "UNKNOWN_ARCHIVED_ITEM", (st, r))
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