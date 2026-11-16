# -*- coding: utf-8 -*-
"""
Grader for P1-1: GET /api/lists/:id/archive-preview.

RED until the endpoint exists and returns, under the "keep-whole-tree" rule P1
chose (parent not done -> whole subtree kept; child not done -> whole subtree
kept):

  * a top-level item is a candidate only if it isDone AND every descendant
    subTask is also done — i.e. a fully-closed subtree.
  * otherwise the whole top-level subtree is excluded (parent-not-done, or a
    child-not-done case), with a reason.
  * the response reports candidates (flat, with level/isTop), excluded (with
    reason), hasPartialCompletion, totalMovable.

Read-only: it spins up an isolated instance (copy of data/) and never touches
the live board.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import (ADMIN_ID, Checker, copy_data_dir, http_at,  # noqa: E402
                       run_instance, stop_instance, temp_dir)

c = Checker("archive-preview")

tmp = temp_dir("lt_preview_")
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


try:
    st, body = http_at(base, "POST", "/api/lists",
                       {"userId": ADMIN_ID, "username": "admin",
                        "listName": "preview-probe"})
    if st != 200 or not isinstance(body, dict) or "listId" not in body:
        c.check("temp list created", False, (st, body))
        teardown()
        c.finish()
    lid = body["listId"]

    items = [
        {"itemId": "p1", "title": "single done", "isDone": True},
        {"itemId": "p2", "title": "parent open, child done", "isDone": False,
         "subTasks": [{"itemId": "p2s", "title": "child done", "isDone": True}]},
        {"itemId": "p3", "title": "parent done, child open", "isDone": True,
         "subTasks": [{"itemId": "p3s", "title": "child open", "isDone": False}]},
        {"itemId": "p4", "title": "whole tree done", "isDone": True,
         "subTasks": [{"itemId": "p4s", "title": "child done", "isDone": True}]},
    ]
    st, body = http_at(base, "PUT", "/api/lists/" + lid,
                       {"type": "UPDATE_ITEMS", "items": items, "userId": ADMIN_ID})
    c.check("items written", st == 200, (st, body))

    # ---- the endpoint under test ----
    st, body = http_at(base, "GET", "/api/lists/" + lid + "/archive-preview")

    c.check("preview responds 200 with json", st == 200 and isinstance(body, dict), (st, body))

    if isinstance(body, dict):
        cands = body.get("candidates") or []
        excs = body.get("excluded") or []
        cand_ids = {x.get("itemId") for x in cands}
        exc_ids = {x.get("itemId") for x in excs}

        c.check("single done top-level is a candidate", "p1" in cand_ids, cand_ids)
        c.check("fully-closed subtree (p4 + p4s) are candidates",
                "p4" in cand_ids and "p4s" in cand_ids, cand_ids)
        p4s = [x for x in cands if x.get("itemId") == "p4s"]
        if p4s:
            c.check("nested done child carries level 1", p4s[0].get("level") == 1, p4s)
        else:
            c.check("nested done child present", False, cand_ids)

        c.check("parent-not-done subtree NOT moved (whole-tree kept)",
                "p2" not in cand_ids and "p2s" not in cand_ids, cand_ids)
        c.check("child-not-done subtree NOT moved (whole-tree kept)",
                "p3" not in cand_ids and "p3s" not in cand_ids, cand_ids)

        c.check("parent-not-done top excluded with reason", "p2" in exc_ids, exc_ids)
        p2r = [x for x in excs if x.get("itemId") == "p2"]
        if p2r:
            r = (p2r[0].get("reason") or "").lower()
            c.check("p2 exclusion reason mentions parent/unfinished",
                    ("parent" in r) or ("unfinished" in r) or ("incomplete" in r), r)
        else:
            c.check("p2 exclusion reason present", False, exc_ids)

        c.check("child-not-done top excluded with reason", "p3" in exc_ids, exc_ids)
        p3r = [x for x in excs if x.get("itemId") == "p3"]
        if p3r:
            r = (p3r[0].get("reason") or "").lower()
            c.check("p3 exclusion reason mentions child/unfinished",
                    ("child" in r) or ("unfinished" in r) or ("incomplete" in r), r)
        else:
            c.check("p3 exclusion reason present", False, exc_ids)

        c.check("hasPartialCompletion is true (partial cases present)",
                body.get("hasPartialCompletion") is True,
                body.get("hasPartialCompletion"))
        c.check("totalMovable equals candidate count",
                body.get("totalMovable") == len(cands),
                (body.get("totalMovable"), len(cands)))

        # preview must be read-only: the list is unchanged after the call
        st2, body2 = http_at(base, "GET", "/api/lists")
        all_items = []
        if isinstance(body2, list):
            for l in body2:
                if isinstance(l, dict) and l.get("listId") == lid:
                    all_items = l.get("items", [])
        elif isinstance(body2, dict):
            all_items = body2.get("items", [])
        after = {i.get("itemId") for i in all_items}
        c.check("preview is read-only (list unchanged)",
                after == {"p1", "p2", "p3", "p4"}, after)
finally:
    teardown()

c.finish()
