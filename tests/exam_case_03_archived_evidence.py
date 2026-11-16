# -*- coding: utf-8 -*-
"""
Exam case 03 — archiving moves storage, it does not withdraw evidence.

Probe, not grader: it prints what the server actually does, and never fails.
`exam_case_03_grade.py` is the file that can fail.

The question this case answers: a task is archived once it is closed. What
happens to the evidence it carries? A test item that is the *only* verifier of a
function item still proves that function is covered — archiving it moves it to
another file, it does not retract the proof. Before the fix recorded here,
`buildLinkGraph()` read `data/shared_lists` only, so archiving a list silently
deleted every relation that list carried from the graph, and the coverage rules
started reporting gaps that were never real (measured at the time:
`func-not-verified` went 0 -> 18 when the `test` list was archived).

Setup — the three scenario items are prefixed `EXAM03-`, filed on a THROWAWAY
temp list (created/deleted via the API), never the real `exam` list. This is a
deliberate test-hygiene choice: the old version appended them to the real exam
list and restored them with force-writes that bumped exam.json's updatedAt/updatedBy,
dirtying the git tree after every commit. The assertions never depend on the list's
name, only on the scenario items' content/relations:

    EXAM03-Verified-Feature   open, not closed      -> the owner; never archived
    EXAM03-Sole-Verifier   done, verifies former  -> the only verifier; gets archived
    EXAM03-Orphan-Done     done, no relations    -> archived too; a natural orphan

Archiving is destructive, so it is performed on a throwaway `node server.js`
started against a private copy of data/ (LITETASK_DATA_DIR), not on the working
data. The copy is made *after* the scenario items are filed, so it contains them.

The last step is the reason this case is worth having: on that same copy, the
archive file is deleted, which reproduces the pre-fix view exactly (the graph
cannot see archived work any more). If the assertions that follow were vacuous,
this step would show it — the owner must turn into a gap.
"""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import (ADMIN_ID, copy_data_dir, create_temp_list,  # noqa: E402
                      delete_temp_list, get_items, http_at,
                      put_items, read_items_file, run_instance, server_data_dir,
                      snapshot, stop_instance, temp_dir)

import shutil  # noqa: E402

# Historical: this case used to file the scenario inside the real `exam` list. It
# now uses a throwaway temp list (see run_scenario) so data/shared_lists/exam.json
# is left byte-identical.
LIST = "exam"
PREFIX = "EXAM03-"
OWNER = PREFIX + "Verified-Feature"
VERIFIER = PREFIX + "Sole-Verifier"
LONE = PREFIX + "Orphan-Done"


def item(item_id, title, **kw):
    it = {
        "itemId": item_id, "title": title,
        "isDone": kw.pop("isDone", False), "status": kw.pop("status", "open"),
        "priority": kw.pop("priority", "Medium"), "statusHistory": [],
        "blockedReason": "", "dueDate": "2026-10-28",
        "assignedTo": "admin", "createdBy": "admin", "createdByAgent": "AI Agent",
        "createdById": ADMIN_ID, "createdAt": "2026-10-28 00:00",
        "closedBy": None, "closedById": None, "closedAt": None,
        "localDirectory": "", "localDirectories": [], "comment": kw.pop("comment", ""),
        "relatesTo": kw.pop("relatesTo", []), "subTasks": [],
    }
    it.update(kw)
    return it


def rule_of(doc, value):
    for r in (doc or {}).get("rules", []):
        if r.get("value") == value:
            return r
    return None


def ids_of(rule):
    return [i.get("itemId") for i in (rule or {}).get("items", [])]


def node_of(doc, item_id):
    for n in (doc or {}).get("nodes", []):
        if n.get("itemId") == item_id:
            return n
    return None


def as_dict(x):
    """http_at returns a raw string when the body is not JSON (transport error)."""
    return x if isinstance(x, dict) else {}


def edges_from(doc, item_id):
    return [e for e in (doc or {}).get("edges", [])
            if e["from"]["itemId"] == item_id]


def scenario(items):
    """Only this scenario's items — the filed exam cases are not part of it."""
    return [i for i in items if str(i.get("itemId", "")).startswith(PREFIX)]


def scen_ids(ids):
    """Scenario-scoped view of a gap/orphan id list.

    The raw counts include whatever else is filed in the exam list, so they
    change as the list grows. The scenario-scoped counts do not: they are a
    property of the three items this case files, and they are what the recorded
    answer quotes.
    """
    return sorted(i for i in (ids or []) if str(i).startswith(PREFIX))


def _board_ids(url, lid):
    _, doc = http_at(url, "GET", "/api/lists")
    row = [l for l in (doc or []) if l.get("listId") == lid]
    return [i["itemId"] for i in (row[0]["items"] if row else [])]


def _snapshot(url, lid):
    """Capture every fact the grader later compares — board, gaps, orphans, graph
    nodes/edges, trace, and the archive read-back — from the running copy."""
    _, g = http_at(url, "GET", "/api/gaps?owner=%s&referrer=%s&relation=verifies" % (lid, lid))
    _, o = http_at(url, "GET", "/api/gaps?rule=orphan")
    _, lk = http_at(url, "GET", "/api/links")
    _, tr = http_at(url, "GET",
                    "/api/trace?listId=%s&itemId=%s&direction=back&depth=3"
                    % (lid, urllib.parse.quote(OWNER)))
    st, arc = http_at(url, "GET", "/api/archive/" + lid)
    g, o, lk, tr, arc = (as_dict(g), as_dict(o), as_dict(lk), as_dict(tr), as_dict(arc))
    return {
        "board_ids": _board_ids(url, lid),
        "gap_count": (rule_of(g, "adhoc") or {}).get("count"),
        "gap_ids": ids_of(rule_of(g, "adhoc")),
        "gap_count_scen": len(scen_ids(ids_of(rule_of(g, "adhoc")))),
        "gap_ids_scen": scen_ids(ids_of(rule_of(g, "adhoc"))),
        "orphan_count": (rule_of(o, "orphan") or {}).get("count"),
        "orphan_ids": ids_of(rule_of(o, "orphan")),
        "orphan_count_scen": len(scen_ids(ids_of(rule_of(o, "orphan")))),
        "orphan_ids_scen": scen_ids(ids_of(rule_of(o, "orphan"))),
        "owner_node": node_of(lk, OWNER),
        "verifier_node": node_of(lk, VERIFIER),
        "verifier_edges": [e.get("relation") for e in edges_from(lk, VERIFIER)],
        "trace_ids": [i.get("itemId") for i in tr.get("items", [])],
        "archive_api_status": st,
        "archive_api_ids": [i.get("itemId") for i in arc.get("items", [])],
    }


def _file_scenario(lid):
    """File the three scenario items on the throwaway temp list."""
    put_items(lid, [
        item(OWNER, "EXAM03 Verified Feature (Open, not archived)", status="open"),
        item(VERIFIER, "EXAM03 Sole Verifier (Gets archived)", status="done", isDone=True,
             relatesTo=[{"listId": lid, "itemId": OWNER, "relation": "verifies"}]),
        item(LONE, "EXAM03 Orphan Done (Gets archived)", status="done", isDone=True),
    ], force=True)


def _archive_and_control(url, lid, data_dir):
    """Archive the temp list on the copy, capture the snapshot, then delete the
    archive file to reproduce the pre-fix view. Returns the fields to merge into out."""
    st, body = http_at(url, "POST", "/api/lists/%s/archive" % lid,
                       {"userId": ADMIN_ID, "confirm": True})
    archive = {"http": st, "moved": (body or {}).get("moved")}
    archive_file_ids = [
        i.get("itemId")
        for i in read_items_file(os.path.join(data_dir, "archive", lid + ".json"))
    ]
    after = _snapshot(url, lid)

    # Negative control: take the archive away — the pre-fix view where the graph
    # cannot see archived work. If the assertions above were vacuous, the owner
    # would already be a gap there.
    arc_path = os.path.join(data_dir, "archive", lid + ".json")
    negative_control = {"archive_file_existed": os.path.exists(arc_path)}
    if os.path.exists(arc_path):
        os.remove(arc_path)
    without_archive = _snapshot(url, lid)
    return {"archive": archive, "archive_file_ids": archive_file_ids,
            "after": after, "negative_control": negative_control,
            "without_archive": without_archive}


def run_scenario():
    """Replay the scenario; return the recorded facts. Used by the grader.

    The scenario is filed on a THROWAWAY temp list (created/deleted via the API),
    never the real `exam` list — so data/shared_lists/exam.json is left
    byte-identical. The old version appended the three scenario items to the real
    exam list and restored them with force-writes that bumped exam.json's
    updatedAt/updatedBy, dirtying the git tree after every commit. Archiving still
    happens on a private copy of data/ (so it cannot touch the project), exactly as
    before. See FROZEN.md §2.5 (test-hygiene maintenance approved under the freeze).
    """
    lid = create_temp_list("EXAM03-PROBE")
    base = snapshot(lid)
    out = {"list": lid, "list_id": lid,
           "ids": {"owner": OWNER, "verifier": VERIFIER, "lone": LONE}}
    tmp = temp_dir(prefix="lt_exam03_")
    inst = None
    try:
        _file_scenario(lid)

        # ---------- a private copy, so archiving cannot touch the project ----------
        # Copy the LIVE instance's data (not the hard-coded ROOT checkout) so the
        # throwaway temp list filed on :3000 is present in the private copy too.
        data_dir = os.path.join(tmp, "data")
        shutil.copytree(server_data_dir(), data_dir)
        backup_dir = os.path.join(tmp, "backup")
        inst = run_instance(data_dir, backup_dir, {"LITETASK_AUTO_ARCHIVE": "0"},
                            wait_after_ready=1.5, keep=True)
        out["instance_ready"] = inst["ready"]
        url = "http://localhost:%d" % inst["port"]

        out["before"] = _snapshot(url, lid)
        out.update(_archive_and_control(url, lid, data_dir))
    finally:
        if inst and inst.get("proc"):
            stop_instance(inst["proc"])
        shutil.rmtree(tmp, ignore_errors=True)
        # The scenario lived on a throwaway temp list; delete it so the live board
        # stays byte-clean (no force-write metadata bump on exam.json).
        try:
            delete_temp_list(lid)
        except Exception:
            pass
    out["base_ids"] = [i["itemId"] for i in base]
    return out


def yn(v):
    return {True: "Yes", False: "No", None: "-"}.get(v, str(v))


def _build_rows(r, b, a, n):
    """The before/after comparison table printed by the probe."""
    return [
        ("Scenario items on board",
         "%d items" % len([i for i in b["board_ids"] if i.startswith(PREFIX)]),
         "%d items" % len([i for i in a["board_ids"] if i.startswith(PREFIX)])),
        ("Scenario items in archive file",
         "0 items (no archive file)",
         "%d items" % len([i for i in r["archive_file_ids"] if i.startswith(PREFIX)])),
        ("GET /api/archive/exam",
         "HTTP %s" % b["archive_api_status"],
         "HTTP %s" % a["archive_api_status"]),
        ("Verifier node in graph",
         "archived=%s" % (b["verifier_node"] or {}).get("archived"),
         "archived=%s" % (a["verifier_node"] or {}).get("archived")),
        ("Carried verifies edge",
         "%s" % (b["verifier_edges"] or "—"),
         "%s" % (a["verifier_edges"] or "—")),
        ("Reverse trace reaches verifier",
         yn(VERIFIER in b["trace_ids"]),
         yn(VERIFIER in a["trace_ids"])),
        ("Is owner reported as gap?",
         "%s (scenario count=%s)" % (yn(OWNER in b["gap_ids"]), b["gap_count_scen"]),
         "%s (scenario count=%s)" % (yn(OWNER in a["gap_ids"]), a["gap_count_scen"])),
        ("Archived orphan reported as gap?",
         "%s (scenario count=%s)" % (yn(LONE in b["orphan_ids"]), b["orphan_count_scen"]),
         "%s (scenario count=%s)" % (yn(LONE in a["orphan_ids"]), a["orphan_count_scen"])),
        ("(Contrast) after deleting archive file",
         "—",
         "verifier node %s; owner %s gap (scenario count=%s)"
         % (yn(n["verifier_node"] is not None), yn(OWNER in n["gap_ids"]),
            n["gap_count_scen"])),
    ]


def main():
    r = run_scenario()
    b, a = r["before"], r["after"]
    n = r["without_archive"]

    print("Exam case 03 - Archiving moves storage, not evidence")
    print("list: %s (throwaway temp list; prefix %s; archive on data/ copy)"
          % (r["list_id"], PREFIX))
    print("instance ready: %s   archive HTTP %s moved=%s"
          % (r["instance_ready"], r["archive"]["http"], r["archive"]["moved"]))
    print()

    rows = _build_rows(r, b, a, n)
    print("%-28s %-26s %s" % ("Aspect", "Before Archive", "After Archive"))
    print("-" * 96)
    for row in rows:
        print("%-28s %-26s %s" % (row[0][:28], row[1][:26], row[2]))
    print()
    print("  Post-archive board IDs: %s" % [i for i in a["board_ids"]])
    print("  Archive file IDs       : %s" % r["archive_file_ids"])
    print("  Temp list restored     : %s"
          % ([i["itemId"] for i in get_items(r["list_id"])] == r["base_ids"]))
    print()
    print("ANSWER_JSON " + json.dumps(r, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
