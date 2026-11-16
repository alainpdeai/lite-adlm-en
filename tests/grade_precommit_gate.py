# -*- coding: utf-8 -*-
"""
Grader: the local pre-commit gate is real (Continuous Integration P1).

This repository is local-only — no remote, no CI — and a full grading run is
~2m13s, so whether it runs was a matter of remembering to, and a missed run
produced no feedback. The gate fixes that: a fast subset on every commit, and a
failure blocks it.

What is asserted here:

* the hook is installed and executable in the configured repositories, and is
  byte-identical to its source — a stale copy would look installed while
  running old logic;
* a skip with no reason is REFUSED (silence is not a skip);
* a skip with a reason is allowed AND recorded, with the reason;
* a failing grading run makes the gate exit non-zero — which is what stops the
  commit. Proven hermetically with a stand-in runner that always fails, since
  breaking the real suite to test the gate would be absurd.

Everything runs in throwaway directories; the real repository is only read.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import ROOT, Checker, temp_dir  # noqa: E402

c = Checker("precommit-gate")

PM = os.environ.get("LITETASK_REPO") or ROOT
GATE = os.path.join(PM, "scripts", "precommit_grades.py")
HOOK_SRC = os.path.join(PM, "scripts", "pre-commit")


def run_gate(cwd, env_extra=None):
    env = dict(os.environ)
    for k in ("LITETASK_SKIP_GRADES", "LITETASK_SKIP_REASON", "LITETASK_REPO"):
        env.pop(k, None)
    env.update(env_extra or {})
    p = subprocess.run([sys.executable, GATE], cwd=cwd, env=env,
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# ------------------------------------------------------- 1. installed, current
c.check("the gate script exists", os.path.isfile(GATE), GATE)
c.check("the hook source exists", os.path.isfile(HOOK_SRC), HOOK_SRC)

with open(HOOK_SRC, "rb") as f:
    hook_bytes = f.read()

for repo in [ROOT, PM]:
    hook = os.path.join(repo, ".git", "hooks", "pre-commit")
    c.check("%s has a pre-commit hook" % os.path.basename(repo),
            os.path.isfile(hook), hook)
    c.check("%s's hook is executable (git ignores a non-executable hook)"
            % os.path.basename(repo),
            os.path.isfile(hook) and os.access(hook, os.X_OK), hook)
    if os.path.isfile(hook):
        with open(hook, "rb") as f:
            c.check("%s's hook is byte-identical to the source (not a stale "
                    "copy)" % os.path.basename(repo), f.read() == hook_bytes, hook)

with open(GATE, "r", encoding="utf-8") as f:
    gate_src = f.read()
c.check("the gate runs the FAST subset, not the full ~2m13s suite",
        '"--fast"' in gate_src or "'--fast'" in gate_src, "no --fast found")

# ------------------------------------------------- 2. skip must be justified
tmp = temp_dir(prefix="lt_grade_gate_")
os.makedirs(os.path.join(tmp, ".git"), exist_ok=True)
try:
    rc, out = run_gate(tmp, {"LITETASK_SKIP_GRADES": "1"})
    c.check("a skip with no reason is refused (exit non-zero)", rc != 0, (rc, out[:160]))

    rc2, out2 = run_gate(tmp, {"LITETASK_SKIP_GRADES": "1",
                               "LITETASK_SKIP_REASON": "grader: verifying the channel"})
    c.check("a skip with a reason is allowed (exit 0)", rc2 == 0, (rc2, out2[:160]))
    log = os.path.join(tmp, ".git", "litetask-grade-skip.log")
    c.check("the skip is recorded to a log file", os.path.isfile(log), log)
    if os.path.isfile(log):
        with open(log, "r", encoding="utf-8") as f:
            body = f.read()
        c.check("the log carries the reason, not just the fact of a skip",
                "grader: verifying the channel" in body, body[:200])
        c.check("the log carries a timestamp", any(ch.isdigit() for ch in body[:10]),
                body[:40])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# -------------------------------------- 3. a failing grade must block the commit
tmp2 = temp_dir(prefix="lt_grade_gatefail_")
try:
    tests = os.path.join(tmp2, "tests")
    os.makedirs(tests, exist_ok=True)
    with open(os.path.join(tests, "run_grade_checks.py"), "w", encoding="utf-8") as f:
        f.write("import sys\nsys.exit(1)   # stand-in: grading failed\n")
    rc3, out3 = run_gate(tmp2, {"LITETASK_REPO": tmp2})
    c.check("a failing grading run makes the gate exit non-zero (this is what "
            "stops the commit)", rc3 != 0, (rc3, out3[:200]))
    c.check("the gate says so, rather than failing silently",
            "FAILED" in out3 or "blocked" in out3, out3[:200])
finally:
    shutil.rmtree(tmp2, ignore_errors=True)

c.finish()
