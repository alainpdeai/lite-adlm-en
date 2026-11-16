# -*- coding: utf-8 -*-
"""
Grader: Incremental sync P3-A — conditional reads (ETag / 304) and change events that
carry the actor.

Before this change every read returned the whole payload and every change event
was an empty ping: four open tabs each re-downloaded and re-rendered all four
lists on any write anywhere. That re-render is not free — measured at ~5 s of
blocked main thread for 1k rows (tests/browser_render_baseline_check.js).

What is asserted here:

  1. GET /api/lists tags the answer; the same request with If-None-Match
     answers 304 with an empty body (no payload, no parse, no render).
  2. A stale tag answers 200 again — the 304 is not a blanket "never send".
  3. The tag follows the CONTENT: writing one item changes it; writing the
     identical content back does not (the idempotent-write rule).
  4. Adding and removing a list changes the tag too (the tag covers the set of
     lists, not just one of them).
  5. GET /api/lists/:id exists and is tagged with that list's own rev.
  6. The change event names the list, the new revision and the actor — a client
     holding that revision can skip the refetch, which is the point of the
     exercise. The actor is compared against /api/users, not hardcoded.
  7. The frontend actually does both halves: it sends the tag back and it
     listens for `items-changed`. An event nobody handles is not a feature.

Runs against a throwaway instance on a copy of data/.
"""
import json
import os
import shutil
import socket
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (ROOT, Checker, copy_data_dir,  # noqa: E402
                       run_instance, stop_instance, temp_dir, temp_item)

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

TIMEOUT = "timeout"
ERROR = "error"

c = Checker("incremental-sync")


def http(method, base, path, body=None, headers=None, timeout=15):
    """(status, body, headers) — HTTP errors returned, not raised."""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    hdrs = dict(headers or {})
    if data:
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, method=method, headers=hdrs)
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw) if raw else None, dict(r.headers)
            except ValueError:
                return r.status, raw, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw) if raw else None, dict(e.headers)
        except ValueError:
            return e.code, raw, dict(e.headers)
    except Exception as e:                                          # noqa: BLE001
        return 0, "transport error: %s" % e, {}


# ----------------------------------------------------------- engine.io client
def raw(base, sid=None, body=None, timeout=6.0):
    if sid:
        path = "/socket.io/?EIO=4&transport=polling&sid=" + sid
    else:
        path = "/socket.io/?EIO=4&transport=polling"
    data = body.encode("utf-8") if body is not None else None
    req = urllib.request.Request(base + path, data=data, method="POST" if data else "GET")
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return "data", r.read().decode("utf-8", "replace")
    except (socket.timeout, TimeoutError):
        return TIMEOUT, None
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            return TIMEOUT, None
        return ERROR, str(e)
    except Exception as e:                                          # noqa: BLE001
        return ERROR, str(e)


def join(base):
    kind, body = raw(base)
    if kind != "data" or not (body or "").startswith("0"):
        return None
    try:
        sid = json.loads(body[1:])["sid"]
    except (ValueError, KeyError):
        return None
    raw(base, sid, body="40")
    return sid


def packets(body):
    """[(eventName, payload)] inside an engine.io payload."""
    out = []
    for part in (body or "").split("\x1e"):
        if part.startswith("42"):
            try:
                arr = json.loads(part[2:])
                out.append((arr[0], arr[1] if len(arr) > 1 else None))
            except (ValueError, IndexError, TypeError):
                pass
    return out


root = temp_dir(prefix="lt_grade_sync_")
inst = None
try:
    data_dir = copy_data_dir(root)
    backup_dir = os.path.join(root, "backup")
    inst = run_instance(data_dir, backup_dir, {"LITETASK_AUTO_ARCHIVE": "0"},
                        wait_after_ready=2.0, keep=True)
    base = "http://127.0.0.1:%d" % inst["port"]
    c.check("throwaway instance came up", inst["ready"], inst["output"][-300:])

    # ---------- 1. conditional read on the collection route ----------------
    st, lists, hdrs = http("GET", base, "/api/lists")
    etag = hdrs.get("ETag") or hdrs.get("etag")
    c.check("GET /api/lists answers 200 with a list payload",
            st == 200 and isinstance(lists, list), st)
    c.check("the answer carries an ETag", bool(etag), sorted(hdrs.keys()))
    c.check("the answer is marked no-cache (always revalidated, never stale)",
            (hdrs.get("Cache-Control") or "").lower().find("no-cache") >= 0,
            hdrs.get("Cache-Control"))

    st2, body2, hdrs2 = http("GET", base, "/api/lists", headers={"If-None-Match": etag})
    raw_len = len(json.dumps(body2, ensure_ascii=False)) if body2 else 0
    c.check("the same request with If-None-Match answers 304", st2 == 304, (st2, body2))
    c.check("the 304 carries no payload at all (no parse, no re-render)",
            raw_len <= 2, (raw_len, str(body2)[:60]))

    st3, _, _ = http("GET", base, "/api/lists", headers={"If-None-Match": '"stale-tag"'})
    c.check("a stale tag answers 200 again (304 is not a blanket refusal)",
            st3 == 200, st3)

    # ---------- 2. the tag follows the content -----------------------------
    st, created, _ = http("POST", base, "/api/lists",
                          {"userId": "user_admin", "username": "admin",
                           "listName": "SYNC-PROBE"})
    c.check("a throwaway list was created", st == 200 and isinstance(created, dict),
            (st, created))
    lid = (created or {}).get("listId")

    st, _, hdrs4 = http("GET", base, "/api/lists")
    etag_after_add = hdrs4.get("ETag")
    c.check("adding a list changes the tag (it covers the set of lists)",
            etag_after_add != etag, (etag, etag_after_add))

    item = temp_item("sync-1", title="sync probe")
    st, wrote, _ = http("POST", base, "/api/lists/%s/items" % lid,
                        {"userId": "user_admin", "item": item})
    c.check("one item was written through the item endpoint",
            st == 200 and (wrote or {}).get("ok"), (st, wrote))
    st, _, hdrs5 = http("GET", base, "/api/lists")
    etag_after_item = hdrs5.get("ETag")
    c.check("writing one item changes the tag", etag_after_item != etag_after_add,
            (etag_after_add, etag_after_item))

    # byte-identical rewrite: same item, nothing changed. (Adding a comment here
    # would make it a real change and the assertion below would be a lie.)
    st, again, _ = http("PUT", base, "/api/lists/%s/items/sync-1" % lid,
                        {"userId": "user_admin", "item": item})
    c.check("writing identical content back is a no-op (idempotent write)",
            st == 200 and (again or {}).get("rev") == (wrote or {}).get("rev"),
            (st, (again or {}).get("rev"), (wrote or {}).get("rev")))
    st, _, hdrs6 = http("GET", base, "/api/lists")
    c.check("that no-op did NOT change the tag (nothing was written to disk)",
            (hdrs6.get("ETag")) == etag_after_item, (etag_after_item, hdrs6.get("ETag")))

    # ---------- 3. single-list route ---------------------------------------
    st, one, hdrs7 = http("GET", base, "/api/lists/%s" % lid)
    c.check("GET /api/lists/:id answers 200 with that one list",
            st == 200 and isinstance(one, dict) and one.get("listId") == lid, (st, one))
    c.check("its ETag is the list's own revision",
            (hdrs7.get("ETag") or "").strip('"') == (one or {}).get("rev"),
            (hdrs7.get("ETag"), (one or {}).get("rev")))
    st8, _, _ = http("GET", base, "/api/lists/%s" % lid,
                     headers={"If-None-Match": hdrs7.get("ETag")})
    c.check("the single-list route answers 304 for an unchanged list",
            st8 == 304, st8)
    st404, _, _ = http("GET", base, "/api/lists/does-not-exist")
    c.check("an unknown list is still 404, not 200 or 500", st404 == 404, st404)

    # ---------- 4. the change event carries the actor ----------------------
    _, users, _ = http("GET", base, "/api/users")
    admin_name = None
    for u in users or []:
        if u.get("userId") == "user_admin":
            admin_name = u.get("username")
    c.check("the admin user resolves to a username (compared, not hardcoded)",
            bool(admin_name), admin_name)

    sid = join(base)
    c.check("a socket client can join", bool(sid), sid)
    if sid:
        st, wrote2, _ = http("POST", base, "/api/lists/%s/items" % lid,
                             {"userId": "user_admin",
                              "item": temp_item("sync-2", title="sync probe 2")})
        c.check("a second item was written to provoke the event",
                st == 200 and (wrote2 or {}).get("ok"), (st, wrote2))
        time.sleep(0.8)
        kind, body = raw(base, sid, timeout=8.0)
        got = packets(body)
        names = [n for n, _p in got]
        c.check("the write broadcasts an items-changed event",
                kind == "data" and "items-changed" in names, (kind, names or body))

        payload = None
        for n, p in got:
            if n == "items-changed":
                payload = p
        c.check("the event carries a payload (it used to be an empty ping)",
                isinstance(payload, dict), payload)
        if isinstance(payload, dict):
            c.check("the payload names the list that changed",
                    payload.get("listId") == lid, payload.get("listId"))
            c.check("the payload carries the NEW revision — the number a client "
                    "compares against what it already holds",
                    payload.get("rev") == (wrote2 or {}).get("rev"),
                    (payload.get("rev"), (wrote2 or {}).get("rev")))
            actor = payload.get("actor") or {}
            c.check("the payload names the actor who did it",
                    actor.get("userId") == "user_admin" and actor.get("username") == admin_name,
                    (actor, admin_name))
            c.check("the payload says what happened (a human-readable summary)",
                    isinstance(payload.get("summary"), str) and payload["summary"],
                    payload.get("summary"))

    # ---------- 5. removing the list changes the tag again -----------------
    st, _, _ = http("DELETE", base, "/api/lists/%s?userId=user_admin&confirm=true" % lid)
    c.check("the throwaway list was removed", st == 200, st)
    st, _, hdrs9 = http("GET", base, "/api/lists")
    c.check("removing a list changes the tag too", hdrs9.get("ETag") != etag_after_item,
            (etag_after_item, hdrs9.get("ETag")))

    # ---------- 6. the frontend does its half ------------------------------
    html = open(os.path.join(ROOT, "public", "index.html"), encoding="utf-8").read()
    c.check("the frontend sends the tag back as If-None-Match",
            "If-None-Match" in html, None)
    c.check("the frontend stores the ETag it was given",
            "listsETag" in html and "res.headers.get('ETag')" in html.replace('"', "'"),
            None)
    c.check("a 304 short-circuits the refetch instead of re-rendering",
            "res.status === 304" in html, None)
    c.check("the frontend listens for items-changed",
            "socket.on('items-changed'" in html, None)
    c.check("and skips the refetch when it already holds that revision "
            "(otherwise the event saves nothing)",
            "alreadyHave" in html and "payload.rev === currentList.value.rev" in html,
            None)
finally:
    if inst and inst.get("proc"):
        stop_instance(inst["proc"])
    shutil.rmtree(root, ignore_errors=True)

c.finish()
