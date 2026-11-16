# -*- coding: utf-8 -*-
"""
Grader: Integrity report P3-D + P3-E — dangling relatesTo edges and itemIds that are
not unique.

`relatesTo` is typed by hand and by Agents, and nothing ever checked that the
thing on the other end exists. An edge to an item that was deleted, moved to the
archive, or never created is invisible: the graph silently loses a link and the
gap report quietly stops counting it as coverage. Likewise an itemId is unique
only by convention — copy/paste one across two lists and every per-item
operation (relations, the new item endpoints, traces) addresses the wrong one.

The cheap version is graded here: a READ-ONLY report. It refuses nothing on
write, because rejecting existing data would lock the board until somebody
cleaned it by hand; the honest first step is to see how much there is.

The properties asserted (on a planted copy of the data, never on the live board):

  * an edge to an item that does not exist is reported, and says why
    (target-item-missing);
  * an edge to a LIST that does not exist is reported too (target-list-missing);
  * an edge to a healthy target is NOT reported — otherwise the report is just
    noise and people stop reading it;
  * an edge to an item that lives in the ARCHIVE is NOT reported: F3 treats
    archived referrers as coverage evidence on purpose, and calling those
    dangling would be a false finding dressed up as a real one;
  * a duplicate itemId is reported, and marked as cross-list or same-list;
  * `ok` is false whenever either kind of problem exists.

The live board is queried at the end and printed — not asserted. How much real
drift exists today is a finding, not a constant; asserting "zero" would be
re-asserting yesterday's data (grade_lib rule 3).
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (ROOT, Checker, copy_data_dir,  # noqa: E402
                       run_instance, stop_instance, temp_dir, temp_item)

c = Checker("integrity-report")

CLI = os.path.join(ROOT, "scripts", "litetask_cli.py")


def write_list(data_dir, list_id, items, list_name=None):
    p = os.path.join(data_dir, "shared_lists", "%s.json" % list_id)
    doc = {
        "listId": list_id,
        "listName": list_name or list_id,
        "category": "probe",
        "owner": "admin",
        "createdAt": "2026-10-31 00:00",
        "items": items,
        "rev": None,
    }
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


def write_archive(data_dir, list_id, items):
    d = os.path.join(data_dir, "archive")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "%s.json" % list_id), "w", encoding="utf-8") as f:
        json.dump({"listId": list_id, "listName": list_id, "items": items},
                  f, ensure_ascii=False, indent=2)


def edge(list_id, item_id, relation="verifies"):
    return {"listId": list_id, "itemId": item_id, "relation": relation}


root = temp_dir(prefix="lt_grade_integrity_")
inst = None
try:
    data_dir = copy_data_dir(root)
    backup_dir = os.path.join(root, "backup")

    # --- the planted scene ------------------------------------------------
    # owner: one item that everything else points at, plus one that only the
    # archive holds (the F3 "archived evidence counts" case).
    write_list(data_dir, "owner", [
        temp_item("ow-live", title="live owner"),
    ])
    write_archive(data_dir, "owner", [temp_item("ow-archived", title="archived owner")])

    write_list(data_dir, "probe", [
        # healthy: must NOT be reported
        temp_item("pr-ok", title="healthy edge", relatesTo=[edge("owner", "ow-live")]),
        # dangling: target item is gone
        temp_item("pr-gone", title="target missing",
                  relatesTo=[edge("owner", "ow-deleted")]),
        # dangling: the whole target list is gone
        temp_item("pr-nolist", title="target list missing",
                  relatesTo=[edge("no-such-list", "whatever")]),
        # archived target: must NOT be reported (F3 counts archived evidence)
        temp_item("pr-arch", title="archived target",
                  relatesTo=[edge("owner", "ow-archived")]),
        # duplicate id #1 (same list)
        temp_item("dup-same", title="duplicate, first"),
        temp_item("dup-same", title="duplicate, second"),
    ])
    # duplicate id #2 (across lists)
    write_list(data_dir, "probe2", [
        temp_item("pr-ok", title="same id in another list"),
    ])

    inst = run_instance(data_dir, backup_dir, {"LITETASK_AUTO_ARCHIVE": "0"},
                        wait_after_ready=1.5, keep=True)
    base = "http://127.0.0.1:%d" % inst["port"]
    c.check("throwaway instance came up", inst["ready"], inst["output"][-300:])

    st, rep = None, None
    import urllib.request
    with urllib.request.urlopen(base + "/api/integrity", timeout=20) as r:
        rep = json.loads(r.read().decode("utf-8"))
        st = r.status
    c.check("GET /api/integrity answers 200", st == 200, st)
    c.check("it reports a checkedAt timestamp and the scale it looked at",
            bool(rep.get("checkedAt")) and isinstance(rep.get("items"), int),
            (rep.get("checkedAt"), rep.get("items")))

    dangling = rep.get("danglingEdges") or []
    dups = rep.get("duplicateItemIds") or []

    def dangling_for(item_id):
        return [d for d in dangling if d.get("itemId") == item_id]

    c.check("an edge to a missing ITEM is reported", bool(dangling_for("pr-gone")),
            dangling)
    c.check("and it says the target item is the thing that is missing",
            (dangling_for("pr-gone") or [{}])[0].get("reason") == "target-item-missing",
            dangling_for("pr-gone"))
    c.check("an edge to a missing LIST is reported", bool(dangling_for("pr-nolist")),
            dangling)
    c.check("and it says the target list is the thing that is missing",
            (dangling_for("pr-nolist") or [{}])[0].get("reason") == "target-list-missing",
            dangling_for("pr-nolist"))
    c.check("a healthy edge is NOT reported (otherwise the report is noise)",
            not dangling_for("pr-ok"), dangling)
    c.check("an edge to an ARCHIVED item is NOT reported — F3 counts archived "
            "referrers as evidence, so calling it dangling would be a false "
            "finding", not dangling_for("pr-arch"), dangling)
    c.check("every reported edge names both ends, so a human can fix it",
            all(d.get("listId") and (d.get("target") or {}).get("itemId")
                and d.get("relation") is not None for d in dangling),
            dangling[:1])

    dup_ids = sorted(d.get("itemId") for d in dups)
    c.check("a duplicate itemId inside one list is reported",
            "dup-same" in dup_ids, dup_ids)
    c.check("a duplicate itemId ACROSS two lists is reported",
            "pr-ok" in dup_ids, dup_ids)
    by_id = {d.get("itemId"): d for d in dups}
    c.check("the cross-list duplicate is marked as cross-list",
            by_id.get("pr-ok", {}).get("crossList") is True, by_id.get("pr-ok"))
    c.check("the same-list duplicate is NOT marked as cross-list",
            by_id.get("dup-same", {}).get("crossList") is False, by_id.get("dup-same"))
    c.check("each duplicate lists where it occurs",
            len((by_id.get("pr-ok") or {}).get("occurrences") or []) >= 2,
            by_id.get("pr-ok"))
    c.check("counts agree with the arrays (a reader should not have to count)",
            (rep.get("counts") or {}).get("dangling") == len(dangling)
            and (rep.get("counts") or {}).get("duplicates") == len(dups),
            (rep.get("counts"), len(dangling), len(dups)))
    c.check("ok is false when the board has drift", rep.get("ok") is False, rep.get("ok"))
    c.check("the report states that it is read-only (nobody should expect a "
            "write to have been refused)",
            "read-only" in ((rep.get("note") or "").lower()), rep.get("note"))

    # ---------- the CLI half ------------------------------------------------
    cli = open(CLI, encoding="utf-8").read()
    c.check("the CLI has a lint subcommand that reads this endpoint",
            "/api/integrity" in cli and 'sub.add_parser("lint"' in cli, None)
    c.check("lint exits non-zero under --strict when something is reported",
            "args.strict" in cli and "return 1 if" in cli, None)

    # ---------- the live board: printed, not asserted ------------------------
    try:
        with urllib.request.urlopen("http://localhost:3000/api/integrity",
                                    timeout=20) as r:
            live = json.loads(r.read().decode("utf-8"))
        print("  live board: %d dangling / %d duplicate(s) across %d items"
              % ((live.get("counts") or {}).get("dangling", 0),
                 (live.get("counts") or {}).get("duplicates", 0),
                 live.get("items", 0)))
        for d in (live.get("danglingEdges") or [])[:5]:
            print("      - %s/%s -%s-> %s/%s [%s]"
                  % (d.get("listId"), d.get("itemId"), d.get("relation"),
                     (d.get("target") or {}).get("listId"),
                     (d.get("target") or {}).get("itemId"), d.get("reason")))
    except Exception as e:                                          # noqa: BLE001
        print("  live board not reachable for the informational read: %s" % e)
finally:
    if inst and inst.get("proc"):
        stop_instance(inst["proc"])
    shutil.rmtree(root, ignore_errors=True)

c.finish()
