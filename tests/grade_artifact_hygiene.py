# -*- coding: utf-8 -*-
"""
Grader for func item Browser screenshot self-cleanup (Core Features)
(derives-from arch legacy P1: tests/ leftover artifact cleanup,
 task_1793225065344e08326).

Recorded claim: browser_lib.js writes screenshots under
tests/_artifacts/<run_id>/ — never into tests/ itself — and pruneArtifacts()
keeps only the newest ARTIFACT_KEEP_RUNS (3) run directories, deleting older
runs while never touching anything in _artifacts/ that is not a run directory.
"""
import glob
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import Checker, ROOT  # noqa: E402

c = Checker("artifact-hygiene")

ART = os.path.join(ROOT, "tests", "_artifacts")
RUN_ID_RE = re.compile(r"^\d{8}T\d{9}Z_pid\d+$")
KEEP = 3
MY_RUN = "20991231T235999999Z_pid424242"   # sorts newest, so it always survives
PLANTED = ["2025010%dT000000000Z_pid%d" % (i, 2000 + i) for i in range(1, 6)]
OLDEST_PLANTED = PLANTED[:3]              # always inside the prune window


def run_dirs():
    if not os.path.isdir(ART):
        return set()
    return {d for d in os.listdir(ART)
            if os.path.isdir(os.path.join(ART, d)) and RUN_ID_RE.match(d)}


def load_lib(run_id):
    env = dict(os.environ)
    env["LITETASK_RUN_ID"] = run_id
    return subprocess.run(
        ["node", "-e",
         'const lib = require("./tests/browser_lib.js");'
         ' console.log("SHOTS=" + lib.SHOTS);'],
        cwd=ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60)


before = run_dirs()
shots_before = set(glob.glob(os.path.join(ROOT, "tests", "shot_*.png")))
decoy_dir = os.path.join(ART, "not-a-run-dir")

try:
    os.makedirs(ART, exist_ok=True)
    for d in PLANTED:
        os.makedirs(os.path.join(ART, d), exist_ok=True)
        with open(os.path.join(ART, d, "shot_planted.png"), "w",
                  encoding="utf-8") as f:
            f.write("x")
    os.makedirs(decoy_dir, exist_ok=True)
    with open(os.path.join(decoy_dir, "keepme.txt"), "w", encoding="utf-8") as f:
        f.write("x")

    print("== require browser_lib.js with a fresh LITETASK_RUN_ID ==")
    p = load_lib(MY_RUN)
    c.check("browser_lib.js loads cleanly", p.returncode == 0, p.stderr[-300:])
    shots_line = [l for l in p.stdout.strip().splitlines()
                  if l.startswith("SHOTS=")]
    c.check("a SHOTS= line was printed", bool(shots_line), p.stdout[-200:])
    c.check("SHOTS resolves inside tests/_artifacts/<run_id>",
            bool(shots_line) and shots_line[-1].endswith(MY_RUN)
            and "_artifacts" in shots_line[-1], shots_line)

    after = run_dirs()
    c.check("run directories are bounded to the newest %d" % KEEP,
            len(after) == KEEP, sorted(after))
    c.check("this run's directory survived", MY_RUN in after, sorted(after))
    c.check("the 3 oldest planted runs were pruned",
            not (set(OLDEST_PLANTED) & after),
            sorted(set(OLDEST_PLANTED) & after))
    c.check("only known runs remain (nothing unexpected appeared)",
            not (after - before - set(PLANTED) - {MY_RUN}),
            sorted(after - before - set(PLANTED) - {MY_RUN}))
    c.check("non-run-dir content is untouched",
            os.path.isfile(os.path.join(decoy_dir, "keepme.txt")), decoy_dir)

    print()
    print("== the same run id twice shares one directory ==")
    p2 = load_lib(MY_RUN)
    c.check("second load with the same id exits 0", p2.returncode == 0,
            p2.stderr[-200:])
    line1 = [l for l in p.stdout.strip().splitlines() if l.startswith("SHOTS=")]
    line2 = [l for l in p2.stdout.strip().splitlines() if l.startswith("SHOTS=")]
    c.check("SHOTS is identical for the same run id",
            bool(line1) and line1 == line2, (line1, line2))
    c.check("no duplicate run directory was created",
            sum(1 for d in run_dirs() if d == MY_RUN) == 1, None)

    print()
    print("== tests/ itself stays clean ==")
    shots_after = set(glob.glob(os.path.join(ROOT, "tests", "shot_*.png")))
    c.check("requiring browser_lib wrote no shot_*.png into tests/",
            shots_after == shots_before, sorted(shots_after - shots_before))
finally:
    for d in PLANTED:
        shutil.rmtree(os.path.join(ART, d), ignore_errors=True)
    shutil.rmtree(os.path.join(ART, MY_RUN), ignore_errors=True)
    shutil.rmtree(decoy_dir, ignore_errors=True)

c.check("planted artifacts removed again",
        not (set(PLANTED) & run_dirs()) and not os.path.isdir(decoy_dir), None)
c.finish()
