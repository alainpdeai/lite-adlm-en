# -*- coding: utf-8 -*-
"""
Grader for P1-4: archive pre-action snapshot (auditable + reversible).

Why this file exists: before P1-4 an archive removed items from the active list
and appended them to data/archive/<list>.json with NO copy of the pre-state —
the 2026-10-29 loss of 17 `arch` items (hand-recovered from git, commit
b780480) is the canonical scar. This grader proves the fix:

* archiveList writes a snapshot of BOTH files (active list + archive) to
  data/archive-snapshots/<listId>-<stamp>.snapshot.json before it mutates
  anything. The snapshot holds the exact pre-move state.
* GET  /api/lists/:id/archive-snapshots  lists the audit trail (admin only).
* POST /api/lists/:id/archive-restore     reverses ONE archive action by writing
  the captured pre-state back to both files (admin only).
* Snapshots are pruned to MAX_ARCHIVE_SNAPSHOTS (20) per list.

Everything runs against a throwaway `node server.js` on a private copy of data/
(grade_lib rule 2) with auto-archive OFF, so the working board is untouched;
the last section proves that by hashing the real data files before and after.
"""
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import (ADMIN_ID, ROOT, Checker, copy_data_dir,  # noqa: E402
                       http_at, read_items_file, run_instance,
                       stop_instance, temp_dir, temp_item)

c = Checker("archive-snapshot")

LID = "probe_snap"
SNAP_DIRNAME = "archive-snapshots"
MAX_SNAP = 20


def snap_dir(data_dir):
    return os.path.join(data_dir, SNAP_DIRNAME)


def list_snap_files(data_dir, lid):
    d = snap_dir(data_dir)
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d)
                  if f.startswith("%s-" % lid) and f.endswith(".snapshot.json"))


def read_snap(data_dir, fn):
    with open(os.path.join(snap_dir(data_dir), fn), encoding="utf-8") as f:
        return json.load(f)


def ids_of(items):
    return sorted(i["itemId"] for i in items)


def write_list(data_dir, list_id, items, list_name="GRADE probe snapshot"):
    doc = {"listId": list_id, "listName": list_name, "category": "test",
           "items": items, "rev": "", "updatedAt": "2026-10-28T00:00:00.000Z"}
    with open(os.path.join(data_dir, "shared_lists", "%s.json" % list_id),
              "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


def probe_items():
    sub_done = temp_item("ps-sub-done", title="probe subtask done",
                         status="done", isDone=True)
    return [
        temp_item("ps-p1", title="probe closed 1", status="done", isDone=True),
        temp_item("ps-p2", title="probe open", status="open"),
        temp_item("ps-p3", title="probe closed subtree", status="done",
                  isDone=True, subTasks=[sub_done]),
    ]


def data_hashes():
    out = {}
    d = os.path.join(ROOT, "data")
    for rel in ("shared_lists/arch.json", "shared_lists/func.json",
                "shared_lists/test.json", "shared_lists/exam.json"):
        p = os.path.join(d, rel)
        if os.path.exists(p):
            with open(p, "rb") as f:
                out[rel] = hashlib.sha256(f.read()).hexdigest()
    ad = os.path.join(d, "archive")
    out["archive"] = sorted(os.listdir(ad)) if os.path.isdir(ad) else []
    sd = os.path.join(d, SNAP_DIRNAME)
    out[SNAP_DIRNAME] = sorted(os.listdir(sd)) if os.path.isdir(sd) else []
    return out


HASHES_BEFORE = data_hashes()

tmp_root = temp_dir(prefix="lt_grade_snap_")
run = None
try:
    data_dir = copy_data_dir(tmp_root)
    backup_dir = os.path.join(tmp_root, "backup")
    original = probe_items()
    write_list(data_dir, LID, original)
    lists_file = os.path.join(data_dir, "shared_lists", "%s.json" % LID)

    run = run_instance(data_dir, backup_dir, {"LITETASK_AUTO_ARCHIVE": "0"},
                       wait_after_ready=1.5, keep=True)
    base = "http://localhost:%d" % run["port"]
    c.check("the throwaway instance came up", run["ready"], run["output"][-300:])

    print()
    print("== the snapshot endpoint exists and is admin-guarded ==")
    st, body = http_at(base, "GET", "/api/lists/%s/archive-snapshots?userId=%s"
                       % (LID, ADMIN_ID))
    c.check("GET /api/lists/:id/archive-snapshots answers 200", st == 200, (st, body))
    c.check("it reports 0 snapshots before any archive",
            isinstance(body, dict) and body.get("count") == 0
            and body.get("snapshots") == [], body)
    st403, b403 = http_at(base, "GET", "/api/lists/%s/archive-snapshots?userId=nope"
                          % LID)
    c.check("a non-admin is refused with 403 on list", st403 == 403, (st403, b403))

    print()
    print("== archiving ONE item writes a pre-state snapshot ==")
    st, ar = http_at(base, "POST", "/api/lists/%s/archive" % LID,
                     {"userId": ADMIN_ID, "itemIds": ["ps-p1"], "confirm": True})
    c.check("the manual archive moved exactly 1 entry",
            st == 200 and isinstance(ar, dict) and ar.get("moved") == 1, (st, ar))
    st, doc = http_at(base, "GET", "/api/archive/%s" % LID)
    c.check("the archive now holds ps-p1",
            (doc or {}).get("items") and ids_of(doc["items"]) == ["ps-p1"], doc)
    live = read_items_file(lists_file)
    c.check("the active list dropped ps-p1, kept ps-p2 and ps-p3",
            ids_of(live) == ["ps-p2", "ps-p3"], ids_of(live))

    print()
    print("== the snapshot captured the PRE-mutation state of both files ==")
    snaps = list_snap_files(data_dir, LID)
    c.check("exactly one snapshot file exists on disk", len(snaps) == 1, snaps)
    st, doc = http_at(base, "GET", "/api/lists/%s/archive-snapshots?userId=%s"
                      % (LID, ADMIN_ID))
    c.check("the endpoint lists the 1 snapshot", doc.get("count") == 1, doc)
    snap = read_snap(data_dir, snaps[0])
    c.check("snapshot carries the active list pre-state (all 3 items present)",
            ids_of(snap.get("activeBefore", {}).get("items", []))
            == ["ps-p1", "ps-p2", "ps-p3"],
            ids_of(snap.get("activeBefore", {}).get("items", [])))
    c.check("snapshot also carries the archive pre-state",
            "archiveBefore" in snap, list(snap.keys()))
    c.check("snapshot stamps a timestamp", bool(snap.get("stamp")), snap.get("stamp"))
    stamp = snap["stamp"]

    print()
    print("== restore reverses the single archive action ==")
    st, rs = http_at(base, "POST", "/api/lists/%s/archive-restore" % LID,
                     {"userId": ADMIN_ID, "stamp": stamp, "confirm": True})
    c.check("POST /api/lists/:id/archive-restore answers 200",
            st == 200 and isinstance(rs, dict), (st, rs))
    c.check("it restored 3 active items", rs.get("restoredActive") == 3, rs)
    c.check("it emptied the archive again", rs.get("restoredArchive") == 0, rs)
    back = read_items_file(lists_file)
    c.check("the active list is whole again (ps-p1 returned)",
            ids_of(back) == ["ps-p1", "ps-p2", "ps-p3"], ids_of(back))
    st, doc = http_at(base, "GET", "/api/archive/%s" % LID)
    c.check("the archive is empty after restore",
            not (doc or {}).get("items"), doc)
    subtree = next(i for i in back if i["itemId"] == "ps-p3")
    c.check("the restored closed subtree kept its child intact",
            ids_of(subtree.get("subTasks", [])) == ["ps-sub-done"],
            ids_of(subtree.get("subTasks", [])))

    print()
    print("== restore is admin-guarded and replay-safe ==")
    st403r, b403r = http_at(base, "POST", "/api/lists/%s/archive-restore" % LID,
                            {"userId": "not_admin", "stamp": stamp})
    c.check("a non-admin restore is refused with 403", st403r == 403, (st403r, b403r))
    st, rs2 = http_at(base, "POST", "/api/lists/%s/archive-restore" % LID,
                      {"userId": ADMIN_ID, "stamp": stamp, "confirm": True})
    c.check("restoring the same snapshot again is a no-op (pre-state already there)",
            st == 200 and rs2.get("restoredActive") == 3, (st, rs2))

    print()
    print("== pruning caps snapshots at MAX_ARCHIVE_SNAPSHOTS per list ==")
    # Rebuild a fresh list with 22 closed items, archive each one separately.
    many = [temp_item("ps-m%d" % i, title="probe many %d" % i,
                      status="done", isDone=True) for i in range(22)]
    write_list(data_dir, LID, many)
    for i in range(22):
        st, r = http_at(base, "POST", "/api/lists/%s/archive" % LID,
                        {"userId": ADMIN_ID, "itemIds": ["ps-m%d" % i], "confirm": True})
        if st != 200 or (isinstance(r, dict) and r.get("moved") != 1):
            c.check("archived probe item ps-m%d (loop)" % i, False, (st, r))
            break
    snaps_now = list_snap_files(data_dir, LID)
    c.check("snapshots are capped at %d (not 23)" % MAX_SNAP,
            len(snaps_now) == MAX_SNAP, len(snaps_now))
finally:
    if run and run.get("proc"):
        stop_instance(run["proc"])
    shutil.rmtree(tmp_root, ignore_errors=True)

print()
print("== the working board was not touched ==")
c.check("the real data files are byte-identical to before this grader ran",
        data_hashes() == HASHES_BEFORE, (HASHES_BEFORE, data_hashes()))

c.finish()
