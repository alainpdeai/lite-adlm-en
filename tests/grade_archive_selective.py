# -*- coding: utf-8 -*-
"""Grader for P1-3 backend: archive honours a caller-supplied itemIds whitelist.

The frontend selection dialog sends only the checked candidates; the endpoint must
archive exactly those fully-closed top-level subtrees and leave everything else
(including other fully-closed subtrees the user unchecked) in the active list.
Isolated instance, never touches the live board.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import (ADMIN_ID, Checker, copy_data_dir, http_at,  # noqa: E402
                       run_instance, stop_instance, temp_dir)

c = Checker("archive-selective")

tmp = temp_dir("lt_sel_")
data_dir = copy_data_dir(tmp)
backup_dir = os.path.join(tmp, "backup")
os.makedirs(backup_dir, exist_ok=True)
inst = run_instance(data_dir, backup_dir, {}, keep=True, timeout=60)
base = "http://127.0.0.1:%d" % inst["port"]


def teardown():
    try:
        stop_instance(inst["proc"])
    except Exception:
        pass


def collect_ids(items, acc):
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        acc.add(it.get("itemId"))
        collect_ids(it.get("subTasks"), acc)


try:
    st, body = http_at(base, "POST", "/api/lists",
                       {"userId": ADMIN_ID, "username": "admin",
                        "listName": "sel-probe"})
    lid = body["listId"]
    items = [
        {"itemId": "p1", "title": "done A", "isDone": True},
        {"itemId": "p4", "title": "done tree", "isDone": True,
         "subTasks": [{"itemId": "p4s", "title": "child done", "isDone": True}]},
        {"itemId": "p2", "title": "open parent", "isDone": False,
         "subTasks": [{"itemId": "p2s", "title": "child done", "isDone": True}]},
    ]
    st, body = http_at(base, "PUT", "/api/lists/" + lid,
                       {"type": "UPDATE_ITEMS", "items": items, "userId": ADMIN_ID})
    c.check("items written", st == 200, (st, body))

    # archive ONLY p1 (the user unchecked p4)
    st, body = http_at(base, "POST", "/api/lists/" + lid + "/archive",
                       {"userId": ADMIN_ID, "itemIds": ["p1"], "confirm": True})
    c.check("selective archive success",
            st == 200 and isinstance(body, dict) and body.get("success"), (st, body))

    _, lists = http_at(base, "GET", "/api/lists")
    active = next((l for l in (lists or [])
                   if isinstance(l, dict) and l.get("listId") == lid), None)
    active_ids = {i.get("itemId") for i in (active or {}).get("items", [])}
    c.check("p4 (unchecked) stays active", "p4" in active_ids, active_ids)
    c.check("p2 stays active (partial)", "p2" in active_ids, active_ids)
    c.check("p1 moved out of active", "p1" not in active_ids, active_ids)

    st, arch = http_at(base, "GET", "/api/archive/" + lid)
    arch_ids = set()
    collect_ids((arch or {}).get("items", []), arch_ids)
    c.check("archive holds only the selected p1", arch_ids == {"p1"}, arch_ids)
finally:
    teardown()

c.finish()
