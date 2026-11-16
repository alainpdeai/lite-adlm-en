# -*- coding: utf-8 -*-
"""
Grade: item schema validation (Contract and schema P1).

Server must validate item field names + types before writing and REJECT malformed
items with a readable 400 INVALID_ITEM_SCHEMA, while still accepting every valid
item (including the dual-write legacy fields isDone/status and unknown legacy
fields).

RED before implementation: server.js has no such check, so malformed items return
200 and these checks fail. After validateItems is wired into the UPDATE_ITEMS path,
bad items return 400 and valid items 200.

Reverse control (guard against tautology): valid items — a hand-built full-shape item, a real
item copied from current data, and an item carrying an unknown legacy field — must
all be accepted. Bad items — missing required, wrong type, enum out-of-range — must
all be rejected.

Hermetic: runs against a throwaway instance (LITETASK_DATA_DIR copy) so it never
touches production data.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from grade_lib import (Checker, run_instance, stop_instance, copy_data_dir,
                       temp_dir, http_at, create_temp_list, delete_temp_list,
                       ADMIN_ID)



def _put(base, lid, items, force=False):
    payload = {"type": "UPDATE_ITEMS", "items": items, "userId": ADMIN_ID}
    if force:
        payload["force"] = True
    return http_at(base, "PUT", "/api/lists/" + lid, payload)


def _ids_now(base, lid):
    _, lists = http_at(base, "GET", "/api/lists")
    for L in (lists or []):
        if L.get("listId") == lid:
            return [i.get("itemId") for i in L.get("items", [])]
    return None


def _check_reverse_control_1(c, put):
    # ---- reverse control 1: fully-specified valid item (all known fields) ----
    valid = {
        "itemId": "schema_valid_01", "title": "valid item",
        "isDone": False, "status": "open", "statusHistory": [],
        "blockedReason": "", "dueDate": "2026-10-30",
        "priority": "High", "assignedTo": "admin", "createdBy": "admin",
        "createdByAgent": "AI Agent", "createdById": ADMIN_ID,
        "createdAt": "2026-10-28 00:00", "closedBy": None, "closedById": None,
        "closedAt": None, "localDirectory": "<PROJECT_DIR>",
        "localDirectories": ["<PROJECT_DIR>"], "comment": "<p>hi</p>",
        "subTasks": [], "relatesTo": [{"listId": "arch", "itemId": "x",
                                       "relation": "related"}],
    }
    st, b = put([valid])
    c.check("valid item (all 21 fields, correct types) accepted -> 200", st == 200, (st, b))
    last_ids = ["schema_valid_01"]
    return valid, ["schema_valid_01"]


def _check_reverse_control_2(base, c, put, last_ids):
    # ---- reverse control 2: a real existing item copied from current data ----
    _, lists = http_at(base, "GET", "/api/lists")
    real_item = None
    for L in (lists or []):
        if L.get("items"):
            real_item = L["items"][0]
            break
    if real_item is not None:
        st, b = put([real_item])
        c.check("a real existing item re-written is accepted -> 200",
                st == 200, (st, b))
        last_ids = [real_item.get("itemId")]
    else:
        c.check("a real existing item re-written is accepted -> 200", False,
                "no list with items found")
    return last_ids


def _check_reverse_control_3(c, put, valid, last_ids):
    # ---- reverse control 3: unknown extra field tolerated (forward-compat) ----
    tolerated = dict(valid)
    tolerated["itemId"] = "schema_unknown_01"
    tolerated["someLegacyField"] = "keep me"
    st, b = put([tolerated])
    c.check("item with unknown extra field still accepted -> 200", st == 200, (st, b))
    last_ids = ["schema_unknown_01"]
    return ["schema_unknown_01"]


def _check_rejections(c, put, ids_now, last_ids):
    # ---- bad items: each must be rejected 400 + readable INVALID_ITEM_SCHEMA ----
    def expect_reject(name, bad_item, field_in_msg):
        st, b = put([bad_item])
        code = b.get("code") if isinstance(b, dict) else None
        err = b.get("error", "") if isinstance(b, dict) else str(b)
        ok = (st == 400) and (code == "INVALID_ITEM_SCHEMA")
        c.check("%s rejected -> 400 INVALID_ITEM_SCHEMA" % name, ok, (st, code, err))
        c.check("%s error names the offending field" % name,
                isinstance(b, dict) and field_in_msg in err, err)
        # isolation: a rejected write must not change the stored list
        c.check("%s did not persist (list unchanged)" % name,
                ids_now() == last_ids, (ids_now(), last_ids))

    expect_reject("missing itemId",
                  {"title": "no id", "isDone": False, "status": "open"},
                  "itemId")
    expect_reject("missing title",
                  {"itemId": "x1", "isDone": False, "status": "open"},
                  "title")
    expect_reject("itemId wrong type (number)",
                  {"itemId": 123, "title": "t", "isDone": False, "status": "open"},
                  "itemId")
    expect_reject("isDone wrong type (string)",
                  {"itemId": "x2", "title": "t", "isDone": "yes", "status": "open"},
                  "isDone")
    expect_reject("status enum out of range",
                  {"itemId": "x3", "title": "t", "isDone": False,
                   "status": "frobnicate"},
                  "status")
    expect_reject("priority enum out of range",
                  {"itemId": "x4", "title": "t", "isDone": False, "status": "open",
                   "priority": "Urgent"},
                  "priority")
    expect_reject("subTasks wrong type (string)",
                  {"itemId": "x5", "title": "t", "isDone": False, "status": "open",
                   "subTasks": "nope"},
                  "subTasks")
    expect_reject("closedBy wrong type (number, not null/string)",
                  {"itemId": "x6", "title": "t", "isDone": False, "status": "open",
                   "closedBy": 42},
                  "closedBy")


def _check_valid_survived(c, ids_now):
    # ---- after every rejection, the valid item is still present ----
    c.check("valid item survived all rejections",
            "schema_unknown_01" in (ids_now() or []), ids_now())


def main():
    data = temp_dir("lt_schema_")
    backup = temp_dir("lt_schema_bak_")
    copy_data_dir(data)
    inst = run_instance(data, backup, {}, keep=True)
    base = "http://127.0.0.1:%d" % inst["port"]
    c = Checker("item-schema")

    st, body = http_at(base, "POST", "/api/lists",
                       {"userId": ADMIN_ID, "username": "admin",
                        "listName": "SCHEMA-GRADE"})
    c.check("temp list created", st == 200 and isinstance(body, dict), (st, body))
    lid = body["listId"]

    def put(items, force=False):
        return _put(base, lid, items, force)

    def ids_now():
        return _ids_now(base, lid)

    # clean start
    st, _ = put([], force=True)
    c.check("empty list write ok", st == 200, st)
    last_ids = []

    valid, last_ids = _check_reverse_control_1(c, put)
    last_ids = _check_reverse_control_2(base, c, put, last_ids)
    last_ids = _check_reverse_control_3(c, put, valid, last_ids)
    _check_rejections(c, put, ids_now, last_ids)
    _check_valid_survived(c, ids_now)

    delete_temp_list(lid)
    stop_instance(inst["proc"])
    c.finish()

if __name__ == "__main__":
    main()
