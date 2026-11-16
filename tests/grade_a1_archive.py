# -*- coding: utf-8 -*-
"""
Grader for test item Verify F5 Hide Closed and A1 Archive (task_17931422186693352f1).

The "hide completed" half is graded in the browser (`browser_ui_check.js`).
This file grades the archive half, which is server-side and had no grader at all:

* archiving moves closed items out of the active file and into data/archive/
* open items stay put — archiving is not "empty the list"
* the moved item is stamped with where and when it came from
* archiving twice moves nothing the second time (idempotent), and an empty
  archive read is not an error

Everything happens on a throwaway list; the archive file it produces is removed
again afterwards.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import (ADMIN_ID, api, Checker, create_temp_list, delete_temp_list,  # noqa: E402
                       get_list, put_items, temp_item)

c = Checker("A1")

LID = create_temp_list("GRADE-TEMP a1")


def archive():
    return api("POST", "/api/lists/%s/archive" % LID,
               {"userId": ADMIN_ID, "confirm": True})


def ids():
    return [i["itemId"] for i in get_list(LID)["items"]]


try:
    print("== setup: one closed item, one open item ==")
    put_items(LID, [temp_item("a1-done", title="closed", status="done", isDone=True),
                    temp_item("a1-open", title="open", status="open")])
    c.check("both items are in the list", ids() == ["a1-done", "a1-open"], ids())
    rev_before = get_list(LID)["rev"]

    print()
    print("== archiving moves only the closed one ==")
    st, body = archive()
    c.check("POST archive answers 200", st == 200, (st, body))
    c.check("reports moved=1", isinstance(body, dict) and body.get("moved") == 1, body)
    c.check("reports remaining=1", isinstance(body, dict) and body.get("remaining") == 1, body)
    c.check("open item stayed in the list", ids() == ["a1-open"], ids())
    c.check("rev advanced", get_list(LID)["rev"] != rev_before, None)

    print()
    print("== the archived item is still readable ==")
    st, doc = api("GET", "/api/archive/" + LID)
    c.check("GET /api/archive answers", st == 200, (st, doc))
    moved = [i for i in (doc or {}).get("items", []) if i.get("itemId") == "a1-done"]
    c.check("the closed item is in the archive", len(moved) == 1,
            [i.get("itemId") for i in (doc or {}).get("items", [])])
    c.check("it is stamped with archivedFrom", moved and moved[0].get("archivedFrom") == LID,
            moved[:1])
    c.check("it is stamped with archivedAt", moved and bool(moved[0].get("archivedAt")),
            moved[:1])
    c.check("the archive keeps the list name", bool((doc or {}).get("listName")),
            (doc or {}).get("listName"))

    print()
    print("== archived content is not silently dropped on a second sweep ==")
    st, body2 = archive()
    c.check("second archive reports moved=0", isinstance(body2, dict) and body2.get("moved") == 0,
            body2)
    c.check("remaining is still 1", isinstance(body2, dict) and body2.get("remaining") == 1, body2)
    c.check("archive still holds the one item",
            isinstance(body2, dict) and body2.get("archiveCount") == 1, body2)
    c.check("the open item is still in the list", ids() == ["a1-open"], ids())

    print()
    print("== a list with nothing closed is left alone ==")
    put_items(LID, [temp_item("a1-open", title="open", status="open")])
    st, body3 = archive()
    c.check("nothing closed -> moved=0", isinstance(body3, dict) and body3.get("moved") == 0,
            body3)
    c.check("the item is untouched", ids() == ["a1-open"], ids())
finally:
    delete_temp_list(LID)

c.check("temp list removed again", get_list(LID) is None, LID)
c.check("its archive file was cleaned up too",
        not os.path.exists("%s/data/archive/%s.json" % (
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), LID)), LID)
c.finish()
