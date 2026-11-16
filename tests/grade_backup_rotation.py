# -*- coding: utf-8 -*-
"""
Grader for func item Startup backup rotation retention (Core Features)
(derives-from arch legacy P1: Startup backup backup/ unbounded accumulation cleanup,
 task_1793225064811c50c05).

Recorded claim: every successful launch snapshots data/'s JSON files into
LITETASK_BACKUP_DIR under a fixed-width ISO stamp, and pruneOldBackups() keeps
only the newest BACKUP_KEEP stamps (default 5, overridable via
LITETASK_BACKUP_KEEP) — deleting every older snapshot stamp while never
touching anything in backup/ whose name is not a snapshot.
"""
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import Checker, copy_data_dir, run_instance, temp_dir  # noqa: E402

c = Checker("backup-rotation")

STAMP_RE = re.compile(r"\.(\d{8}T\d{9}Z)\.json$")
KEEP_DEFAULT = 5


def stamps_in(backup_dir):
    found = set()
    for dirpath, _sub, files in os.walk(backup_dir):
        for f in files:
            m = STAMP_RE.search(f)
            if m:
                found.add(m.group(1))
    return found


tmp = temp_dir("lt_grade_rot_")
try:
    data_dir = copy_data_dir(tmp)
    backup_dir = os.path.join(tmp, "backup")

    print("== launch 1: a fresh backup dir gets exactly one stamp ==")
    r1 = run_instance(data_dir, backup_dir, {})
    c.check("instance 1 came up", r1["ready"], r1["output"][-300:])
    c.check("launch 1 logged a startup backup", "Startup backup" in r1["output"],
            r1["output"][-200:])
    s1 = stamps_in(backup_dir)
    c.check("fresh dir holds exactly 1 snapshot stamp", len(s1) == 1, sorted(s1))

    print()
    print("== plant 6 stale snapshots + one non-snapshot decoy ==")
    fake = ["2025010%dT000000000Z" % i for i in range(1, 7)]  # 20250101..20250106
    for st in fake:
        with open(os.path.join(backup_dir, "categories.%s.json" % st), "w",
                  encoding="utf-8") as f:
            f.write("{}")
    decoy_dir = os.path.join(backup_dir, "legacy_decoy_test")
    os.makedirs(decoy_dir, exist_ok=True)
    with open(os.path.join(decoy_dir, "keepme.json"), "w", encoding="utf-8") as f:
        f.write("{}")
    c.check("7 stamps present before launch 2 (1 real + 6 planted)",
            len(stamps_in(backup_dir)) == 7, sorted(stamps_in(backup_dir)))

    print()
    print("== launch 2: the default KEEP=5 prunes the 3 oldest stamps ==")
    r2 = run_instance(data_dir, backup_dir, {})
    c.check("instance 2 came up", r2["ready"], r2["output"][-300:])
    c.check("launch 2 logged the rotation", "Backup rotation" in r2["output"],
            r2["output"][-300:])
    s2 = stamps_in(backup_dir)
    c.check("exactly KEEP stamps remain (%d)" % KEEP_DEFAULT,
            len(s2) == KEEP_DEFAULT, sorted(s2))
    gone = [st for st in fake[:3] if st not in s2]
    c.check("the 3 oldest stale stamps were deleted", len(gone) == 3, gone)
    c.check("the boundary stamp 20250104 survives", "20250104T000000000Z" in s2,
            sorted(s2))
    c.check("both real stamps survive", s1 <= s2, sorted(s2))
    c.check("the non-snapshot decoy is untouched",
            os.path.isfile(os.path.join(decoy_dir, "keepme.json")), decoy_dir)

    print()
    print("== launch 3: LITETASK_BACKUP_KEEP=2 prunes every stale stamp ==")
    r3 = run_instance(data_dir, backup_dir, {"LITETASK_BACKUP_KEEP": "2"})
    c.check("instance 3 came up", r3["ready"], r3["output"][-300:])
    s3 = stamps_in(backup_dir)
    c.check("exactly 2 stamps remain", len(s3) == 2, sorted(s3))
    c.check("no planted stamp survives", not (set(fake) & s3),
            sorted(set(fake) & s3))
    c.check("the knob is real (env overrode the default 5)", len(s3) < len(s2),
            (len(s2), len(s3)))
    c.check("decoy still alive after three launches",
            os.path.isfile(os.path.join(decoy_dir, "keepme.json")), decoy_dir)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

c.check("temp instance tree removed", not os.path.isdir(tmp), tmp)
c.finish()
