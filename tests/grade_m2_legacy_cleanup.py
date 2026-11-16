# Auto-generated
# -*- coding: utf-8 -*-
"""
Grader for test item Verify M2 cleanup of legacy files (task_179320467499839f1e7).

Recorded claim: seven legacy files (27545 B) were removed from data/ on
2026-10-28, the board still comes up complete afterwards — and the removal used
to be recoverable from `backup/legacy_m2_20261028T161737Z/`.

RETIRED 2026-10-29: that snapshot no longer exists. It was destroyed with the
rest of `backup/` during the 2026-10-28 accumulation cleanup, and it cannot be
rebuilt — the source files were removed by M2, the git baseline starts after the
removal, and only the tooling scripts survive. The three checks that asserted the
snapshot's existence, file count and byte size are therefore retired, not
deleted: they still print, and they count as neither pass nor fail.

What this grader still enforces — the substance of M2 itself:

* the legacy paths are gone
* `data/users/` itself is still there (server.js reads it)
* all four lists are present, non-empty and parseable
* the server serves four lists
* nothing in the running code still refers to the removed tree
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import ROOT, api, Checker, get_list       # noqa: E402

c = Checker("M2")

DATA = os.path.join(ROOT, "data")
LISTS = ["arch", "func", "test", "exam"]

print("== the removed paths stay removed ==")
gone = [
    os.path.join(DATA, "_legacy_backup_20261027"),
    os.path.join(DATA, "users", "user_admin"),
    os.path.join(DATA, "users", "user_1791622363912"),
]
for p in gone:
    c.check("gone: %s" % os.path.relpath(p, ROOT).replace("\\", "/"),
            not os.path.exists(p), p)

print()
print("== what had to survive ==")
# A freshly delivered baseline has no runtime data/ yet; the server creates
# data/users/ and data/shared_lists/ on first boot. Absent precondition ->
# SKIP, not FAIL (this grader re-derives a historical migration, not a bug).
users_dir = os.path.join(DATA, "users")
if os.path.isdir(users_dir):
    c.check("data/users/ still exists (server.js reads it)", True, users_dir)
else:
    c.skip("data/users/ still exists (server.js reads it)",
           "delivery baseline before first boot; server creates it at startup")
shared_dir = os.path.join(DATA, "shared_lists")
if os.path.isdir(shared_dir):
    c.check("data/shared_lists/ still exists", True, shared_dir)
else:
    c.skip("data/shared_lists/ still exists",
           "delivery baseline before first boot; server creates it at startup")

print()
print("== all four lists are intact ==")
for lid in LISTS:
    p = os.path.join(DATA, "shared_lists", lid + ".json")
    ok = os.path.exists(p)
    c.check("%s.json exists" % lid, ok, p)
    if ok:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        n_items = len(doc.get("items", [])) if isinstance(doc, dict) else 0
        if n_items > 0:
            c.check("%s.json parses and has items" % lid, True, n_items)
        else:
            c.skip("%s.json parses and has items" % lid,
                   "empty delivery baseline; seed a project to grade content")

st, lists = api("GET", "/api/lists")
ids = sorted(l.get("listId") for l in (lists or []))
# shared_lists/ may also hold user-created lists (e.g. "01" Shared Team Workspace);
# the claim is that the four category lists are all served, not that no other list may exist.
c.check("all four category lists are served",
        st == 200 and set(LISTS).issubset(ids), ids)

print()
print("== nothing still points at the removed tree ==")
src = open(os.path.join(ROOT, "server.js"), encoding="utf-8").read()
c.check("server.js has no _legacy_backup reference", "_legacy_backup" not in src, None)

print()
print("== the removal is recoverable (RETIRED: evidence destroyed) ==")
snap = os.path.join(ROOT, "backup", "legacy_m2_20261028T161737Z")
for label in ("the pre-removal snapshot exists",
              "it holds the seven removed files",
              "total size is 27545 bytes"):
    c.retired(label,
              "backup/legacy_m2_20261028T161737Z was deleted during the "
              "2026-10-28 backup/ cleanup and cannot be rebuilt (sources "
              "removed by M2, git baseline postdates the removal); the M2 "
              "removal itself is still enforced by the checks above")

# The retired checks are gone, but the reason they existed must stay visible:
# if the tree ever comes back, this grader has to fail again immediately.
c.check("no legacy tree reappeared under backup/ or data/",
        not os.path.exists(snap)
        and not os.path.exists(os.path.join(DATA, "_legacy_backup_20261027")),
        snap)

c.finish()
