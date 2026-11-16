# -*- coding: utf-8 -*-
"""P2-6 grader: derived reads stay fresh without a cache."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (  # noqa: E402
    Checker, copy_data_dir, http_at, http_at_headers, run_instance,
    stop_instance, temp_dir,
)

NAME = "p2-derived-read"
c = Checker(NAME)
json_out = None
if "--json" in sys.argv:
    i = sys.argv.index("--json")
    if i + 1 < len(sys.argv):
        json_out = sys.argv[i + 1]

ADMIN = "user_admin"
LID = "probe_read"


def item(iid, title):
    return {"itemId": iid, "title": title, "isDone": False, "status": "open",
            "statusHistory": [], "blockedReason": "", "dueDate": "",
            "priority": "Medium", "assignedTo": "admin", "createdBy": "admin",
            "createdByAgent": "AI Agent", "createdById": ADMIN,
            "createdAt": "2026-11-01 00:00", "closedBy": None,
            "closedById": None, "closedAt": None, "localDirectory": "",
            "localDirectories": [], "comment": "", "subTasks": []}


ctx = None
try:
    tmp = temp_dir(prefix="lt_p2_read_")
    data = copy_data_dir(os.path.join(tmp, "inst"))
    os.makedirs(os.path.join(data, "shared_lists"), exist_ok=True)
    with open(os.path.join(data, "shared_lists", LID + ".json"), "w", encoding="utf-8") as f:
        json.dump({"listId": LID, "listName": "P2 READ", "category": "test",
                   "items": [item("r1", "one")]}, f)
    inst = run_instance(data, os.path.join(tmp, "backup"), {
        "LITETASK_AUTO_ARCHIVE": "0", "LITETASK_BACKUP_MIRROR": "0",
    }, wait_after_ready=2.0, timeout=60, keep=True)
    ctx = {"inst": inst, "tmp": tmp, "data": data}
    b = "http://127.0.0.1:%d" % inst["port"]

    st, links = http_at(b, "GET", "/api/links")
    c.check("links answers", st == 200, st)
    st, integrity = http_at(b, "GET", "/api/integrity")
    c.check("integrity answers", st == 200, st)
    st, health = http_at(b, "GET", "/api/health")
    c.check("health answers", st == 200, st)
    typed = True

    # write through the API, then read the derived endpoints immediately
    st, _ = http_at(b, "PUT", "/api/lists/" + LID,
                    {"type": "UPDATE_ITEMS", "userId": ADMIN,
                     "items": [item("r1", "one"), item("r2", "two")]})
    st, all_lists = http_at(b, "GET", "/api/lists")
    counts = {l.get("listId"): len(l.get("items") or []) for l in (all_lists or [])}
    st, health_now = http_at(b, "GET", "/api/health")
    c.check("health lists counts agree with /api/lists",
            all(h.get("items") == counts.get(h.get("listId")) for h in health_now.get("lists", [])),
            health_now.get("lists"))
    c.check("write is visible on the next read", st == 200
            and counts.get(LID) == 2, counts)

    # external edit must be visible without restart
    p = os.path.join(data, "shared_lists", LID + ".json")
    raw = json.load(open(p, encoding="utf-8"))
    raw["items"].append(item("external", "external"))
    with open(p, "w", encoding="utf-8") as f:
        json.dump(raw, f)
    st, lists2 = http_at(b, "GET", "/api/lists")
    c.check("external file edit is visible on the next read", st == 200
            and any(len(l.get("items") or []) == 3 for l in lists2 if l["listId"] == LID), lists2)

    st, _, h = http_at_headers(b, "GET", "/api/lists")
    etag = {k.lower(): v for k, v in h.items()}.get("etag")
    if etag:
        st304, _ = http_at(b, "GET", "/api/lists", headers={"If-None-Match": etag})
        c.check("unchanged read still answers 304", st304 == 304, st304)
        raw["items"].append(item("etag", "etag change"))
        with open(p, "w", encoding="utf-8") as f:
            json.dump(raw, f)
        st200, _ = http_at(b, "GET", "/api/lists", headers={"If-None-Match": etag})
        c.check("a changed file invalidates the ETag", st200 == 200, st200)
    c.check("no cache layer is present (explicit no-cache decision)",
            "mtimeCache" not in open(os.path.join(HERE, "..", "lib", "links.js"),
                                     encoding="utf-8").read(), "cache code found")
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