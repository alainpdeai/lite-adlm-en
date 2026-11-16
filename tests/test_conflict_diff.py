"""B3 follow-up verification: save-conflict diff + --force overwrite.

Creates a throwaway list, plays two clients that both loaded the same rev,
and checks:
  1. the loser gets 409 REV_CONFLICT
  2. the payload carries a usable field-level diff (incl. nested subtasks)
  3. a retry with force=true goes through and lands exactly "my" content
  4. a normal (non-forced) save still conflicts afterwards (guard not disabled)

Run:  python tests/test_conflict_diff.py        (server must be on :3000)
"""
import json
import os
import sys
import urllib.request

BASE = os.environ.get("LITETASK_BASE_URL", "http://localhost:3000") + "/api"
ADMIN = "user_admin"


def req(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body or "null")
        except ValueError:
            return e.code, {"raw": body}


def get_list(lid):
    st, lists = req("GET", "/lists")
    assert st == 200, st
    for l in lists:
        if l.get("listId") == lid:
            return l
    raise SystemExit("list %s not found" % lid)


def put_items(lid, items, base_rev, force=False):
    body = {"type": "UPDATE_ITEMS", "items": items, "userId": ADMIN}
    if base_rev:
        body["baseRev"] = base_rev
    if force:
        body["force"] = True
        body["confirm"] = True
    return req("PUT", "/lists/" + lid, body)


def item(title, iid=None, subs=None):
    return {
        "itemId": iid or ("task_" + title),
        "title": title,
        "isDone": False, "status": "open", "priority": "Medium",
        "dueDate": "2026-10-28", "comment": "", "blockedReason": "",
        "localDirectory": "", "localDirectories": [], "relatesTo": [],
        "subTasks": subs or [],
    }


FAILURES = []


def check(label, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (("  -> " + str(detail)) if detail else ""))
    if not cond:
        FAILURES.append(label)


def _seed_and_client_b(lid, rev0):
    """Seed both clients from the same rev, then let client B save first."""
    # ---- both clients load the same content -------------------------
    seed = [item("Task A"), item("Task B", subs=[item("Subtask B1")])]
    st, after = put_items(lid, seed, rev0)
    check("seed write ok", st == 200, st)
    rev1 = after["rev"]
    loaded = after["items"]            # what "client A" and "client B" both hold

    # ---- client B saves first (bumps the rev) -----------------------
    b_items = json.loads(json.dumps(loaded))
    b_items[0]["priority"] = "High"
    b_items[0]["comment"] = "Comment modified by B"
    b_items.append(item("Task C added by B"))
    st, after_b = put_items(lid, b_items, rev1)
    check("client B save ok", st == 200, st)
    rev2 = after_b["rev"]
    return rev1, loaded, rev2


def _client_a_conflict(lid, rev1, loaded, rev2):
    """Client A edits the stale rev: the save must 409 with a usable diff."""
    # ---- client A saves its own edit on the stale rev ---------------
    a_items = json.loads(json.dumps(loaded))          # A never saw B's write
    a_items[0]["title"] = "Title modified by A"
    a_items[0]["priority"] = "Low"                    # conflicts with B's High
    a_items[0]["comment"] = "Comment modified by A"                # conflicts with B's comment
    a_items[1]["subTasks"][0]["title"] = "Subtask B1 modified by A"
    a_items.append(item("Task D added by A"))

    st, info = put_items(lid, a_items, rev1)          # stale rev -> must refuse
    check("stale save rejected with 409", st == 409, st)
    check("code is REV_CONFLICT", info.get("code") == "REV_CONFLICT", info.get("code"))
    check("serverRev returned", info.get("serverRev") == rev2, info.get("serverRev"))

    d = info.get("diff") or {}
    c = d.get("counts") or {}
    print("  diff counts:", c)
    check("diff: 1 item only in mine", c.get("added") == 1, c)
    check("diff: 1 item only on server", c.get("removed") == 1, c)
    check("diff: 2 changed items", c.get("changed") == 2, c)
    check("diff: 4 changed fields", c.get("fields") == 4, c)

    titles = {x["itemId"]: x["title"] for x in d.get("added", [])}
    check("added reports my new item", "task_Task D added by A" in titles, titles)
    rem = {x["itemId"] for x in d.get("removed", [])}
    check("removed reports server new item", "task_Task C added by B" in rem, rem)

    ch = {x["itemId"]: x for x in d.get("changed", [])}
    top = ch.get("task_Task A") or {}
    fmap = {f["field"]: f for f in top.get("fields", [])}
    check("field diff: title", fmap.get("title", {}).get("mine") == "Title modified by A", fmap.get("title"))
    check("field diff: priority mine=Low", fmap.get("priority", {}).get("mine") == "Low", fmap.get("priority"))
    check("field diff: priority server=High", fmap.get("priority", {}).get("server") == "High", fmap.get("priority"))
    check("field diff: comment both sides",
          fmap.get("comment", {}).get("mine") == "Comment modified by A"
          and fmap.get("comment", {}).get("server") == "Comment modified by B", fmap.get("comment"))
    sub = ch.get("task_Subtask B1") or {}
    subf = {f["field"]: f for f in sub.get("fields", [])}
    check("nested subtask diff present", subf.get("title", {}).get("mine") == "Subtask B1 modified by A", sub)
    check("diff exposes server items", isinstance(info.get("items"), list) and len(info["items"]) == 3,
          len(info.get("items") or []))
    return a_items


def _guard_and_force(lid, a_items, rev1, rev2):
    """Without force it still 409s; with force it lands exactly my version."""
    # ---- the guard must still work without force --------------------
    st2, info2 = put_items(lid, a_items, rev1)
    check("still 409 without force", st2 == 409, st2)

    # ---- one-click "keep my version" --------------------------------
    st3, res3 = put_items(lid, a_items, rev1, force=True)
    check("force save accepted", st3 == 200, (st3, res3))
    # The server augments every item with workflow bookkeeping
    # (statusHistory / closedBy / closedAt …), so compare the payload fields.
    def sketch(items):
        return [(i["itemId"], i["title"], i.get("priority"), i.get("comment"),
                 [(s["itemId"], s["title"]) for s in (i.get("subTasks") or [])])
                for i in items]

    server_now = get_list(lid)
    check("server now equals my version", sketch(server_now["items"]) == sketch(a_items),
          sketch(server_now["items"]))
    check("rev advanced after force", server_now["rev"] != rev2, server_now["rev"])
    return server_now


def _clean_force(lid, a_items, server_now):
    """Force on a clean rev is harmless."""
    # ---- force without any conflict is harmless ---------------------
    st4, _ = put_items(lid, a_items, server_now["rev"], force=True)
    check("force on a clean rev still ok", st4 == 200, st4)


def main():
    st, created = req("POST", "/lists", {"listName": "ZZ-B3-tmp", "userId": ADMIN, "username": "admin"})
    check("create throwaway list", st == 200, st)
    lid = created["listId"]
    print("temp list:", lid)
    try:
        base = get_list(lid)
        rev0 = base["rev"]

        rev1, loaded, rev2 = _seed_and_client_b(lid, rev0)
        a_items = _client_a_conflict(lid, rev1, loaded, rev2)
        server_now = _guard_and_force(lid, a_items, rev1, rev2)
        _clean_force(lid, a_items, server_now)

        print("\nRESULT: %d failure(s)" % len(FAILURES))
        for f in FAILURES:
            print("  - " + f)
    finally:
        st, _ = req("DELETE", "/lists/%s?adminUserId=%s&confirm=true" % (lid, ADMIN))
        print("cleanup delete:", st)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
