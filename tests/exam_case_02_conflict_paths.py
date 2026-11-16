# -*- coding: utf-8 -*-
"""
Exam case 02 — the four ways out of a save conflict (B3).

Probe, not grader: it prints what the server actually does, and never fails.
`exam_case_02_grade.py` is the file that can fail.

The question this case answers: when two clients edit the same list and the
loser gets 409 REV_CONFLICT, the UI offers four ways out — take mine, take the
server's, merge, cancel. They feel like four different operations. On the wire
they are not: two of them issue no write at all, and the revision token is a
digest of the content rather than a version counter, so two of them leave the
file byte-identical and the rev untouched.

It runs on a THROWAWAY temp list (created and deleted via the API), *not* the
real `exam` list. This is a deliberate test-hygiene choice: the old version
appended scenario items to the real exam list and restored them with force-writes
that bumped exam.json's `updatedAt`/`updatedBy`, dirtying the git tree after every
commit. The scenario items are prefixed `EXAM02-`, added to the temp list, and the
whole temp list is deleted at the end (never by emptying a shared list). The
recorded answer is identical — the assertions never depend on the list's name, only
on the scenario items' content/rev relationships.

Setup:

    base + two shared items          -> rev R1 (what both clients loaded)
    client B saves first             -> rev R2  (changed shared item, added one)
    client A saves its own edit      -> 409 REV_CONFLICT

Then each of the four resolutions is replayed from that identical 409 state, and
the resulting rev and on-disk content are recorded.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import (ADMIN_ID, create_temp_list, delete_temp_list,  # noqa: E402
                      get_list, put_items, snapshot, restore)

# Historical: this case used to run inside the real `exam` list. It now uses a
# throwaway temp list (see run_paths) so data/shared_lists/exam.json stays untouched.
LIST = "exam"
PREFIX = "EXAM02-"


def item(title, **kw):
    it = {
        "itemId": PREFIX + title, "title": "EXAM02 " + title,
        "isDone": False, "status": "open", "priority": kw.pop("priority", "Medium"),
        "statusHistory": [], "blockedReason": "", "dueDate": "2026-10-28",
        "assignedTo": "admin", "createdBy": "admin", "createdByAgent": "AI Agent",
        "createdById": ADMIN_ID, "createdAt": "2026-10-28 00:00",
        "closedBy": None, "closedById": None, "closedAt": None,
        "localDirectory": "", "localDirectories": [], "comment": kw.pop("comment", ""),
        "relatesTo": [], "subTasks": [],
    }
    it.update(kw)
    return it


def clone(items):
    return json.loads(json.dumps(items))


def local_rev(items):
    """Python mirror of contentRev(): sha256(JSON.stringify(items)).slice(0,16)."""
    s = json.dumps(items, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def mine(items):
    """Only this scenario's items — the filed exam cases are not part of it."""
    return [i for i in items if str(i.get("itemId", "")).startswith(PREFIX)]


def fingerprint(items):
    """What this scenario left on disk, independent of the filed cases."""
    return sorted((i.get("itemId"), i.get("priority"), i.get("comment"))
                  for i in mine(items))


def _replay_take_mine(lid, a_items, r1, r2):
    st, _ = put_items(lid, a_items, rev=r1, force=True)
    after = get_list(lid)
    return {"write": "PUT baseRev=R1 + force", "http": st,
            "rev_before": r2, "rev_after": after["rev"],
            "content": fingerprint(after["items"]),
            "rev_is_digest": local_rev(after["items"]) == after["rev"]}


def _replay_take_server(lid, b_items, a_items, r1, prev_rev):
    put_items(lid, b_items, rev=prev_rev, force=True)      # back to B's content
    r2b = get_list(lid)["rev"]
    put_items(lid, a_items, rev=r1)                        # the 409 happens again
    after = get_list(lid)                                  # and the client gives up
    return {"write": "none (client reloads)", "http": None,
            "rev_before": r2b, "rev_after": after["rev"],
            "content": fingerprint(after["items"]),
            "rev_is_digest": local_rev(after["items"]) == after["rev"]}


def _replay_merge(lid, b_items, a_items, prev_rev):
    merged = clone(b_items)                                # start from what the server has
    by_id = {i["itemId"]: i for i in merged}
    for a_it in a_items:
        if a_it["itemId"] in by_id:
            by_id[a_it["itemId"]]["comment"] = a_it["comment"]   # A's edit wins
        else:
            merged.append(a_it)                                  # A's new item joins
    st, _ = put_items(lid, merged, rev=prev_rev)
    after = get_list(lid)
    return {"write": "PUT baseRev=R2 (fresh)", "http": st,
            "rev_before": prev_rev, "rev_after": after["rev"],
            "content": fingerprint(after["items"]),
            "rev_is_digest": local_rev(after["items"]) == after["rev"]}


def _replay_cancel(lid, b_items, a_items, r1, prev_rev):
    put_items(lid, b_items, rev=prev_rev, force=True)      # back to B's content
    r2c = get_list(lid)["rev"]
    put_items(lid, a_items, rev=r1)                        # 409 again
    after = get_list(lid)                                  # client cancels
    return {"write": "none (client abandons)", "http": None,
            "rev_before": r2c, "rev_after": after["rev"],
            "content": fingerprint(after["items"]),
            "rev_is_digest": local_rev(after["items"]) == after["rev"]}


def _replay_digest_property(lid):
    """Observation 5: rev is a digest, not a counter — re-writing identical
    content leaves it unchanged."""
    rev_before = get_list(lid)["rev"]
    st, _ = put_items(lid, get_list(lid)["items"], rev="stale-on-purpose", force=True)
    rev_after = get_list(lid)["rev"]
    return {"http": st, "rev_before": rev_before, "rev_after": rev_after,
            "unchanged": rev_before == rev_after}


def _setup_conflict(lid, base):
    """Build the shared ancestor, then replay client B's save and client A's
    stale-rev save to reach the identical 409 state. Returns the revs and the two
    clients' item sets so the four resolutions can be replayed from there."""
    put_items(lid, base + [item("Common Task"), item("Other Task")], force=True)
    loaded = get_list(lid)["items"]
    r1 = get_list(lid)["rev"]

    def find(items, title):
        return [i for i in items if i["itemId"] == PREFIX + title][0]

    # ---------- client B saves first ----------
    b_items = clone(loaded)
    find(b_items, "Common Task")["priority"] = "High"
    find(b_items, "Common Task")["comment"] = "Comment written by B"
    b_items.append(item("B Added Task"))
    put_items(lid, b_items, rev=r1)
    r2 = get_list(lid)["rev"]

    # ---------- client A saves on the stale rev ----------
    a_items = clone(loaded)
    find(a_items, "Common Task")["comment"] = "Comment written by A"
    a_items.append(item("A Added Task"))
    st409, body409 = put_items(lid, a_items, rev=r1)
    return r1, r2, b_items, a_items, st409, body409


def run_paths(cleanup=True):
    """Replay all four resolutions; return (result, meta). Used by the grader.

    Runs against a THROWAWAY temp list (created/deleted via the API), never the
    real `exam` list — so the live board and data/shared_lists/exam.json are left
    byte-identical. The old version appended scenario items to the real exam list
    and restored them with force-writes that bumped exam.json's updatedAt/updatedBy,
    dirtying the git tree after every commit. See FROZEN.md §2.5 (test-hygiene
    maintenance approved under the freeze).
    """
    lid = create_temp_list("EXAM02-PROBE")
    base = snapshot(lid)
    result = {"list": lid, "paths": {}}
    meta = {}
    try:
        r1, r2, b_items, a_items, st409, body409 = _setup_conflict(lid, base)
        meta = {"r1": r1, "r2": r2, "http409": st409, "body409": body409,
                "base_ids": [i["itemId"] for i in base], "list_id": lid}

        # ---------- the four resolutions, replayed from the identical 409 ----------
        p1 = _replay_take_mine(lid, a_items, r1, r2)
        result["paths"]["take_mine"] = p1
        p2 = _replay_take_server(lid, b_items, a_items, r1, p1["rev_after"])
        result["paths"]["take_server"] = p2
        p3 = _replay_merge(lid, b_items, a_items, p2["rev_after"])
        result["paths"]["merge"] = p3
        p4 = _replay_cancel(lid, b_items, a_items, r1, p3["rev_after"])
        result["paths"]["cancel"] = p4

        # ---------- observation 5: rev is a digest, not a counter ----------
        result["rev_is_a_digest"] = _replay_digest_property(lid)
    finally:
        # Restore the temp list to its pre-scenario snapshot (base is the empty
        # list, taken right after create_temp_list), then delete the whole temp
        # list so the live board stays byte-clean. Restoring to `base` rather than
        # "keep non-scenario items" matters here: every item on a throwaway list is
        # a scenario item, so the keep-filter would be a no-op and leave them behind.
        try:
            put_items(lid, base, force=True)
        except Exception:
            pass
        if cleanup:
            delete_temp_list(lid)
    return result, meta


def _print_conflict_report(result, meta):
    r1, r2 = meta["r1"], meta["r2"]
    st409, body409 = meta["http409"], meta["body409"]

    print("Exam case 02 — four ways out of a save conflict")
    print("list: %s (throwaway temp list; scenario items prefixed %s)"
          % (meta["list_id"], PREFIX))
    print("R1=%s  R2=%s" % (r1, r2))
    print()
    print("the 409 both clients start from: HTTP %s  code=%s"
          % (st409, (body409 or {}).get("code")))
    print("  409 body keys: %s" % sorted((body409 or {}).keys()))
    diff = (body409 or {}).get("diff") or {}
    print("  diff keys:     %s" % sorted(diff.keys()))
    print("  diff counts:   %s" % (diff.get("counts") or {}))
    print("  serverRev:     %s (== R2: %s)"
          % ((body409 or {}).get("serverRev"), (body409 or {}).get("serverRev") == r2))
    print()

    print("%-30s %-6s %-24s %s" % ("resolution", "HTTP", "rev", "scenario items on disk"))
    print("-" * 104)
    for key, label in [("take_mine", "1. Adopt Mine (force)"),
                       ("take_server", "2. Keep Server (no write)"),
                       ("merge", "3. Merge (fresh baseRev)"),
                       ("cancel", "4. Cancel (no write)")]:
        p = result["paths"][key]
        moved = "%s -> %s" % (p["rev_before"][:8], p["rev_after"][:8])
        if p["rev_before"] == p["rev_after"]:
            moved += " (unchanged)"
        print("%-30s %-6s %-24s %s" % (
            label, p["http"] if p["http"] is not None else "-", moved,
            "; ".join("%s/%s" % (c[0][len(PREFIX):], c[1][0]) for c in p["content"])))
    print()
    for key in ("take_mine", "take_server", "merge", "cancel"):
        p = result["paths"][key]
        print("  %-12s rev=%s   local sha256(items) == rev: %s"
              % (key, p["rev_after"], p["rev_is_digest"]))
    print()
    print("  take_server and cancel leave the same rev: %s"
          % (result["paths"]["take_server"]["rev_after"]
             == result["paths"]["cancel"]["rev_after"]))
    print("  rev is a digest, not a version counter: force-writing identical content "
          "left it unchanged (%s)" % result["rev_is_a_digest"]["unchanged"])
    print()
    final_ids = [i["itemId"] for i in get_list(meta["list_id"])["items"]]
    print("temp list restored: %s" % (final_ids == meta["base_ids"]))
    print()
    print("ANSWER_JSON " + json.dumps(result, ensure_ascii=False))


def main():
    result, meta = run_paths(cleanup=False)
    _print_conflict_report(result, meta)
    delete_temp_list(meta["list_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
