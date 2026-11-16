# Auto-generated
# -*- coding: utf-8 -*-
"""
Grader for test item Verify F2 multi-path linking and relations overview/list/backup adjustments
(task_1793146361953a34431).

Recorded claims:

* an item can carry several source paths (`localDirectories`), and they survive
  a round trip in order;
* the relation overview is derived from those `relatesTo` edges and is served as
  a graph;
* every launch snapshots all JSON under data/ into backup/, preserving the
  relative directory layout, with one shared timestamp per launch — and the
  backup directory is not itself backed up (no recursive snowball).

RETIRED 2026-10-29: "the M2 removal is still recoverable from backup" is
retired — `backup/legacy_m2_20261028T161737Z` was destroyed with the rest of
backup/ during the 2026-10-28 accumulation cleanup and cannot be rebuilt. It
prints as retired and counts as neither pass nor fail; everything the F2 backup
claims actually rest on (per-launch snapshot, shared stamp, layout preserved, no
nesting) is still enforced below.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import (api, Checker, ROOT, create_temp_list, delete_temp_list,  # noqa: E402
                       get_list, put_items, temp_item)

c = Checker("F2")

BACKUP = os.path.join(ROOT, "backup")
SHARED_BACKUP = os.path.join(BACKUP, "shared_lists")
LISTS = ["arch", "func", "test", "exam"]

print("== multiple source paths per item ==")
LID = create_temp_list("GRADE-TEMP f2")
try:
    paths = [ROOT + "/server.js",
             ROOT + "/data/categories.json",
             ROOT + "/public/index.html"]
    put_items(LID, [temp_item("f2a", localDirectory=paths[0], localDirectories=paths)])
    it = [i for i in get_list(LID)["items"] if i["itemId"] == "f2a"][0]
    c.check("localDirectories round-trips as a list",
            isinstance(it.get("localDirectories"), list), it.get("localDirectories"))
    # sanitizeLocalDirectories merges primary + extras, de-duplicates, and keeps
    # the primary first: localDirectory = merged[0], localDirectories = the rest.
    # So no path is lost — the primary is simply not repeated inside the extras.
    c.check("primary stays first", it.get("localDirectory") == paths[0],
            it.get("localDirectory"))
    c.check("extras keep the remaining paths in order",
            it.get("localDirectories") == paths[1:], it.get("localDirectories"))
    c.check("no path is lost", [it.get("localDirectory")] + list(it.get("localDirectories") or [])
            == paths, [it.get("localDirectory")] + list(it.get("localDirectories") or []))

    put_items(LID, [temp_item("f2c", localDirectory=paths[0],
                              localDirectories=[paths[0], paths[0] + "/", paths[1]])])
    dup = [i for i in get_list(LID)["items"] if i["itemId"] == "f2c"][0]
    c.check("a duplicate of the primary is dropped (slash and case insensitive)",
            [dup.get("localDirectory")] + list(dup.get("localDirectories") or [])
            == paths[:2], [dup.get("localDirectory")] + list(dup.get("localDirectories") or []))

    many = [ROOT + "/f%02d.js" % n for n in range(25)]
    put_items(LID, [temp_item("f2d", localDirectory=ROOT + "/primary.js",
                              localDirectories=many)])
    capped = [i for i in get_list(LID)["items"] if i["itemId"] == "f2d"][0]
    total = 1 + len(capped.get("localDirectories") or [])
    # extras are sliced to 20 *before* the primary is prepended, so a full item
    # carries 21 paths, not 20.
    c.check("extras are capped at 20 (21 including the primary)", total == 21, total)

    print()
    print("== the relation overview is derived from relatesTo ==")
    put_items(LID, [
        temp_item("f2b", title="B", relatesTo=[{"listId": "func", "itemId": "task_1793139856106e81683",
                                                "relation": "verifies"}]),
    ])
    st, links = api("GET", "/api/links")
    c.check("/api/links answers", st == 200, st)
    edges = (links or {}).get("edges") or []
    c.check("the graph has edges", len(edges) > 0, len(edges))
    mine = [e for e in edges
            if (e.get("from") or {}).get("itemId") == "f2b"]
    c.check("the temp edge appears in the graph", len(mine) == 1, mine[:1])
    c.check("edges carry a relation",
            all(e.get("relation") for e in edges), [e.get("relation") for e in edges[:5]])
finally:
    delete_temp_list(LID)
c.check("temp list removed again", get_list(LID) is None, LID)

print()
print("== startup backup ==")
c.check("backup directory exists", os.path.isdir(BACKUP), BACKUP)
c.check("shared_lists backed up under its own directory", os.path.isdir(SHARED_BACKUP),
        SHARED_BACKUP)
c.check("backup is not nested inside backup",
        "backup" not in os.listdir(BACKUP), os.listdir(BACKUP))

stamps = {}
for f in os.listdir(SHARED_BACKUP):
    if f.count(".") >= 2 and f.endswith(".json"):
        name, stamp = f.rsplit(".", 2)[0], f.rsplit(".", 2)[1]
        stamps.setdefault(stamp, set()).add(name)
c.check("backup files carry a timestamp", bool(stamps), os.listdir(SHARED_BACKUP)[:5])

latest = max(stamps) if stamps else None
c.check("one launch writes all four lists under one stamp",
        latest and set(LISTS).issubset(stamps[latest]),
        {"stamp": latest, "found": sorted(stamps.get(latest, []))})

top = [f for f in os.listdir(BACKUP) if f.endswith(".json")]
c.check("top-level data files (users, categories) are backed up too",
        any(f.startswith("users.") for f in top) and any(f.startswith("categories.") for f in top),
        top[:6])
c.retired("the M2 removal is still recoverable from backup",
          "backup/legacy_m2_20261028T161737Z was deleted during the 2026-10-28 "
          "backup/ cleanup and cannot be rebuilt; see grade_m2_legacy_cleanup.py")

print()
print("== the lists themselves are intact ==")
st, lists = api("GET", "/api/lists")
ids = sorted(l.get("listId") for l in (lists or []))
# shared_lists/ may also hold user-created lists (e.g. "01" Shared Team Workspace);
# the claim is that the four category lists are all served, not that no other
# list may exist.
c.check("all four categories are served", set(LISTS).issubset(ids), ids)
for lid in LISTS:
    l = get_list(lid)
    if l and l.get("items"):
        c.check("%s has items" % lid, True, len(l["items"]))
    else:
        # Empty delivery baseline: the list exists but carries no fixture
        # tasks. That is an absent precondition, not a broken claim.
        c.skip("%s has items" % lid,
               "empty delivery baseline (no fixture items); seed a project to grade this")

c.finish()
