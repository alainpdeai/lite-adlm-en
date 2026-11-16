# -*- coding: utf-8 -*-
"""
Grader for P1-2: archive execution honours the keep-whole-tree rule.

The live POST /api/lists/:id/archive must move ONLY fully-closed top-level
subtrees; partially-closed subtrees (parent-not-done, or any child-not-done)
stay whole in the active list — including their completed children, which must
NOT be split off. Runs against an isolated instance so the live board is never
touched.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import (ADMIN_ID, Checker, copy_data_dir, http_at,  # noqa: E402
                       run_instance, stop_instance, temp_dir)

c = Checker("archive-splitclosed")

tmp = temp_dir("lt_split_")
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


def find(items, iid):
    for it in (items or []):
        if it.get("itemId") == iid:
            return it
    return None


try:
    st, body = http_at(base, "POST", "/api/lists",
                       {"userId": ADMIN_ID, "username": "admin",
                        "listName": "split-probe"})
    lid = body["listId"]

    items = [
        {"itemId": "p1", "title": "single done", "isDone": True},
        {"itemId": "p2", "title": "parent open child done", "isDone": False,
         "subTasks": [{"itemId": "p2s", "title": "child done", "isDone": True}]},
        {"itemId": "p3", "title": "parent done child open", "isDone": True,
         "subTasks": [{"itemId": "p3s", "title": "child open", "isDone": False}]},
        {"itemId": "p4", "title": "whole tree done", "isDone": True,
         "subTasks": [{"itemId": "p4s", "title": "child done", "isDone": True}]},
    ]
    st, body = http_at(base, "PUT", "/api/lists/" + lid,
                       {"type": "UPDATE_ITEMS", "items": items, "userId": ADMIN_ID})
    c.check("items written", st == 200, (st, body))

    st, body = http_at(base, "POST", "/api/lists/" + lid + "/archive",
                       {"userId": ADMIN_ID, "confirm": True})
    c.check("archive returns success",
            st == 200 and isinstance(body, dict) and body.get("success"), (st, body))

    # active list after archive
    _, lists = http_at(base, "GET", "/api/lists")
    active = None
    for l in (lists or []):
        if isinstance(l, dict) and l.get("listId") == lid:
            active = l
    active_ids = {i.get("itemId") for i in (active or {}).get("items", [])}
    c.check("only p2 and p3 remain active (whole-tree kept)",
            active_ids == {"p2", "p3"}, active_ids)

    p2 = find(active.get("items", []), "p2") if active else None
    if p2:
        p2_subs = {s.get("itemId") for s in (p2.get("subTasks") or [])}
        c.check("p2 keeps its completed child p2s (not split off)",
                "p2s" in p2_subs, p2_subs)
    else:
        c.check("p2 present in active", False, active_ids)

    p3 = find(active.get("items", []), "p3") if active else None
    if p3:
        p3_subs = {s.get("itemId") for s in (p3.get("subTasks") or [])}
        c.check("p3 keeps its open child p3s", "p3s" in p3_subs, p3_subs)
    else:
        c.check("p3 present in active", False, active_ids)

    # archive store (recurse into subTasks: moved subtrees are nested)
    def collect_ids(items, acc):
        for it in (items or []):
            if not isinstance(it, dict):
                continue
            acc.add(it.get("itemId"))
            collect_ids(it.get("subTasks"), acc)

    st, arch = http_at(base, "GET", "/api/archive/" + lid)
    arch_ids = set()
    collect_ids((arch or {}).get("items", []), arch_ids)
    c.check("archive holds fully-closed subtrees p1 and p4(+p4s)",
            {"p1", "p4", "p4s"}.issubset(arch_ids), arch_ids)
    c.check("archive does NOT hold partially-closed subtrees",
            not ({"p2", "p2s", "p3", "p3s"} & arch_ids), arch_ids)
finally:
    teardown()

c.finish()
