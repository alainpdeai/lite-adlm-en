# -*- coding: utf-8 -*-
"""
Grader: Item-level write endpoint P3-B — change one item without shipping the whole list.

`PUT /api/lists/:id` takes the entire array, and until now that was the only
write there was: ticking one checkbox meant downloading every list, touching one
field and uploading everything back. That is why the body limit had to be raised
to 16 MB, why a stale copy could silently drop unrelated items (the 2026-10-29
`arch` loss had exactly this shape) and why every write raced every other write
on the same list.

The endpoints under test:

    POST   /api/lists/:id/items            create
    PUT    /api/lists/:id/items/:itemId    replace
    DELETE /api/lists/:id/items/:itemId    remove

The property being graded is not "they exist" — it is that **nothing was
relaxed** to make the small write easy. Every guard the whole-list path applies,
the item path applies too:

  * schema validation (a malformed item is refused before it reaches disk)
  * the F1 status machine — including the subtle one: the previous status must
    be read from the list AS IT IS ON DISK, before the replacement is spliced
    in. Read it afterwards and every transition looks like a no-op.
  * baseRev concurrency (a stale token gets 409, not a silent clobber)
  * the non-admin delete rule
  * the destructive-operation confirmation gate (hard: omitting `confirm` is a
    refusal, not consent)
  * the idempotent-write shortcut (an identical rewrite touches nothing)

Runs against a throwaway instance on a copy of data/, on its own list.
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (ROOT, Checker, copy_data_dir,  # noqa: E402
                       run_instance, stop_instance, temp_dir, temp_item)

c = Checker("item-endpoints")

root = temp_dir(prefix="lt_grade_item_")
inst = None
try:
    data_dir = copy_data_dir(root)
    backup_dir = os.path.join(root, "backup")
    inst = run_instance(data_dir, backup_dir, {"LITETASK_AUTO_ARCHIVE": "0"},
                        wait_after_ready=2.0, keep=True)
    base = "http://127.0.0.1:%d" % inst["port"]
    c.check("throwaway instance came up", inst["ready"], inst["output"][-300:])

    def http(method, path, body=None, timeout=15):
        import urllib.request
        import urllib.error
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        hdrs = {"Content-Type": "application/json"} if data else {}
        req = urllib.request.Request(base + path, data=data, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8", "replace")
                return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(raw) if raw else None
            except ValueError:
                return e.code, raw
        except Exception as e:                                      # noqa: BLE001
            return 0, "transport error: %s" % e

    st, created = http("POST", "/api/lists",
                       {"userId": "user_admin", "username": "admin",
                        "listName": "ITEM-API-PROBE"})
    c.check("a throwaway list was created", st == 200 and isinstance(created, dict),
            (st, created))
    lid = (created or {}).get("listId")
    ITEMS = "/api/lists/%s/items" % lid

    def ids():
        st, doc = http("GET", "/api/lists/%s" % lid)
        return (doc or {}).get("items") or [], (doc or {}).get("rev")

    def item(iid, status="open", **kw):
        return temp_item(iid, title="item api " + iid, status=status, **kw)

    # ---------------- create ------------------------------------------------
    st, body = http("POST", ITEMS, {"userId": "user_admin", "item": item("ia-1")})
    rev1 = (body or {}).get("rev")
    c.check("POST /items creates an item", st == 200 and (body or {}).get("ok"),
            (st, body))
    c.check("it answers with the new revision", bool(rev1), body)
    live, rev_now = ids()
    c.check("the item is on the list", [i["itemId"] for i in live] == ["ia-1"], live)
    c.check("the revision it answered with is the revision on disk",
            rev1 == rev_now, (rev1, rev_now))

    st, body = http("POST", ITEMS, {"userId": "user_admin", "item": item("ia-1")})
    c.check("creating an item that already exists is 409 ITEM_EXISTS "
            "(not a silent duplicate)",
            st == 409 and (body or {}).get("code") == "ITEM_EXISTS", (st, body))

    st, body = http("POST", ITEMS, {"userId": "user_admin", "item": {"itemId": "ia-2"}})
    c.check("a malformed item is refused with 400 INVALID_ITEM_SCHEMA "
            "(schema is not relaxed for the small write)",
            st == 400 and (body or {}).get("code") == "INVALID_ITEM_SCHEMA", (st, body))
    c.check("the refused item never reached the list",
            [i["itemId"] for i in ids()[0]] == ["ia-1"], ids()[0])

    # ---------------- update, and the F1 machine -----------------------------
    st, body = http("PUT", ITEMS + "/ia-1",
                    {"userId": "user_admin", "item": item("ia-1", status="verified")})
    c.check("open -> verified is refused with INVALID_TRANSITION "
            "(the status machine still runs on a single-item write)",
            st == 400 and (body or {}).get("code") == "INVALID_TRANSITION", (st, body))
    c.check("the refusal names the allowed set, as the whole-list path does",
            "Allowed" in ((body or {}).get("error") or ""), (body or {}).get("error"))

    st, body = http("PUT", ITEMS + "/ia-1",
                    {"userId": "user_admin", "item": item("ia-1", status="in-progress")})
    rev2 = (body or {}).get("rev")
    c.check("a legal transition is accepted", st == 200 and bool(rev2), (st, body))
    live, _ = ids()
    moved = next((i for i in live if i["itemId"] == "ia-1"), {})
    c.check("the new status is stored", moved.get("status") == "in-progress", moved)
    c.check("the transition is recorded in statusHistory",
            (moved.get("statusHistory") or [{}])[-1].get("to") == "in-progress",
            moved.get("statusHistory"))

    # Send back exactly what is stored — status, history and all. Hand-building
    # an "identical" item would miss the statusHistory entry the write above
    # appended, and the assertion would then be testing a real change.
    live, _ = ids()
    stored = next(i for i in live if i["itemId"] == "ia-1")
    st, body = http("PUT", ITEMS + "/ia-1", {"userId": "user_admin", "item": stored})
    c.check("rewriting identical content is a no-op (idempotent write: the rev "
            "does not move and nothing is written)",
            st == 200 and (body or {}).get("rev") == rev2, (st, (body or {}).get("rev"), rev2))

    st, body = http("PUT", ITEMS + "/nope", {"userId": "user_admin", "item": item("nope")})
    c.check("updating an item that does not exist is 404 ITEM_NOT_FOUND",
            st == 404 and (body or {}).get("code") == "ITEM_NOT_FOUND", (st, body))

    st, body = http("PUT", ITEMS + "/ia-1", {"userId": "user_admin", "item": item("ia-9")})
    c.check("an itemId that disagrees with the path is refused "
            "(the path is not decoration)",
            st == 400 and (body or {}).get("code") == "ITEM_ID_MISMATCH", (st, body))

    st, body = http("PUT", ITEMS + "/ia-1",
                    {"userId": "user_admin", "baseRev": "stale-token",
                     "item": item("ia-1", status="blocked")})
    c.check("a stale baseRev is 409 REV_CONFLICT (concurrency is not relaxed)",
            st == 409 and (body or {}).get("code") == "REV_CONFLICT", (st, body))
    c.check("the conflict answer carries the server revision",
            (body or {}).get("serverRev") == rev2, ((body or {}).get("serverRev"), rev2))
    live, _ = ids()
    c.check("the refused write did not change the list",
            next(i for i in live if i["itemId"] == "ia-1").get("status") == "in-progress",
            live)

    # ---------------- nested items are reachable -----------------------------
    parent = item("ia-parent")
    parent["subTasks"] = [item("ia-sub", status="open")]
    st, _ = http("POST", ITEMS, {"userId": "user_admin", "item": parent})
    c.check("an item with a subtask was created", st == 200, st)
    st, body = http("PUT", ITEMS + "/ia-sub",
                    {"userId": "user_admin", "item": item("ia-sub", status="in-progress")})
    c.check("a nested subtask can be updated by its own itemId "
            "(the endpoint is not top-level-only)",
            st == 200, (st, body))
    live, _ = ids()
    subs = next(i for i in live if i["itemId"] == "ia-parent").get("subTasks") or []
    c.check("the subtask really changed",
            (subs or [{}])[0].get("status") == "in-progress", subs)

    # ---------------- delete, and the hard confirmation gate -----------------
    st, body = http("DELETE", ITEMS + "/ia-sub", {"userId": "user_admin"})
    c.check("deleting without confirm is refused (hard gate: an omitted field "
            "is not consent)",
            st == 400 and (body or {}).get("code") == "CONFIRMATION_REQUIRED", (st, body))
    st, body = http("DELETE", ITEMS + "/ia-sub", {"userId": "user_admin", "confirm": False})
    c.check("deleting with confirm:false is refused too", st == 400, (st, body))

    st, body = http("DELETE", ITEMS + "/ia-sub",
                    {"userId": "user_nobody", "confirm": True})
    c.check("a non-admin delete is 403 (the delete rule still applies)",
            st == 403, (st, body))

    before_delete, _ = ids()
    st, body = http("DELETE", ITEMS + "/ia-sub", {"userId": "user_admin", "confirm": True})
    c.check("deleting with confirm:true is performed", st == 200 and (body or {}).get("ok"),
            (st, body))
    live, _ = ids()
    subs_after = next(i for i in live if i["itemId"] == "ia-parent").get("subTasks") or []
    c.check("the subtask is gone and its parent survived",
            len(live) == len(before_delete) and not subs_after, (len(live), subs_after))

    st, body = http("DELETE", ITEMS + "/ghost", {"userId": "user_admin", "confirm": True})
    c.check("deleting something that is not there is 404 ITEM_NOT_FOUND",
            st == 404 and (body or {}).get("code") == "ITEM_NOT_FOUND", (st, body))

    # ---------------- an unknown list is still 404 ---------------------------
    st, _ = http("POST", "/api/lists/no-such-list/items",
                 {"userId": "user_admin", "item": item("x")})
    c.check("writing to an unknown list is 404, not a created file", st == 404, st)
finally:
    if inst and inst.get("proc"):
        stop_instance(inst["proc"])
    shutil.rmtree(root, ignore_errors=True)

c.finish()
