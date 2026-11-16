# -*- coding: utf-8 -*-
"""
Grader for test item Verify F1 five-state status flow, invalid transitions and filters
(task_1793144570836a5fe92).

`exam_case_01_grade.py` grades *which* transitions the server accepts. This one
grades what a transition does to the record — the side effects that make the
state machine trustworthy:

  * a legal move appends exactly one statusHistory entry, attributed to the writer
  * an illegal move is refused and changes nothing at all — not the status, not
    the history (a 400 that still mutated the item would be the worst of both)
  * closing fills isDone / closedBy / closedAt
  * a self-transition is a genuine no-op: no history entry

Runs on a throwaway list so nothing real is touched.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import (Checker, create_temp_list, delete_temp_list,  # noqa: E402
                       get_list, put_items, temp_item)

c = Checker("F1")

LID = create_temp_list("GRADE-TEMP f1")
try:
    def item():
        return [i for i in get_list(LID)["items"] if i["itemId"] == "f1a"][0]

    print("== an item can be filed at any starting state ==")
    put_items(LID, [temp_item("f1a", status="blocked")])
    c.check("filed as blocked", item().get("status") == "blocked", item().get("status"))
    c.check("starts with no history", item().get("statusHistory") == [],
            item().get("statusHistory"))

    print()
    print("== a legal transition records one step ==")
    before_rev = get_list(LID)["rev"]
    st, body = put_items(LID, [temp_item("f1a", status="in-progress")])
    c.check("blocked -> in-progress accepted", st == 200, (st, body))
    it = item()
    c.check("status changed", it.get("status") == "in-progress", it.get("status"))
    hist = it.get("statusHistory") or []
    c.check("exactly one history entry appended", len(hist) == 1, hist)
    c.check("entry records from and to",
            hist and (hist[0].get("from"), hist[0].get("to")) == ("blocked", "in-progress"),
            hist[:1])
    c.check("entry attributes the writer", hist and hist[0].get("by"), hist[:1])
    c.check("rev advanced", get_list(LID)["rev"] != before_rev, None)

    print()
    print("== an illegal transition changes nothing ==")
    # A fresh itemId, so the starting state is created rather than reached:
    # walking an existing item back to `open` is itself subject to the flow table
    # (verified -> open is illegal), which would leave the probe in a state it
    # did not intend to test from.
    put_items(LID, [temp_item("f1a", status="in-progress"), temp_item("f1b", status="open")])
    hist_before = len([i for i in get_list(LID)["items"]
                       if i["itemId"] == "f1b"][0].get("statusHistory") or [])
    st, body = put_items(LID, [temp_item("f1a", status="in-progress"),
                               temp_item("f1b", status="verified")])
    it = [i for i in get_list(LID)["items"] if i["itemId"] == "f1b"][0]
    c.check("open -> verified refused with 400", st == 400, (st, body))
    c.check("error code is INVALID_TRANSITION",
            isinstance(body, dict) and body.get("code") == "INVALID_TRANSITION", body)
    c.check("violation names from, to and the allowed set",
            isinstance(body, dict)
            and set(["from", "to", "allowed"]).issubset((body.get("violation") or {}).keys()),
            (body or {}).get("violation"))
    c.check("status is untouched by the refusal", it.get("status") == "open", it.get("status"))
    c.check("no history entry was written",
            len(it.get("statusHistory") or []) == hist_before, it.get("statusHistory"))

    print()
    print("== self-transition is a no-op ==")
    st, _ = put_items(LID, [temp_item("f1a", status="in-progress"),
                            temp_item("f1b", status="open")])
    it = [i for i in get_list(LID)["items"] if i["itemId"] == "f1b"][0]
    c.check("open -> open accepted", st == 200, st)
    c.check("no history entry for a self-transition",
            len(it.get("statusHistory") or []) == hist_before, it.get("statusHistory"))

    print()
    print("== closing fills the closure fields ==")
    st, body = put_items(LID, [temp_item("f1a", status="in-progress"),
                               temp_item("f1b", status="done", isDone=True)])
    it = [i for i in get_list(LID)["items"] if i["itemId"] == "f1b"][0]
    c.check("open -> done accepted", st == 200, (st, body))
    c.check("isDone is set", it.get("isDone") is True, it.get("isDone"))
    c.check("closedBy recorded", bool(it.get("closedBy")), it.get("closedBy"))
    c.check("closedById recorded", bool(it.get("closedById")), it.get("closedById"))
    c.check("closedAt recorded", bool(it.get("closedAt")), it.get("closedAt"))
    c.check("history shows the closing step",
            (it.get("statusHistory") or [{}])[-1].get("to") == "done",
            (it.get("statusHistory") or [])[-1:])
finally:
    delete_temp_list(LID)

c.check("temp list removed again", get_list(LID) is None, LID)
c.finish()
