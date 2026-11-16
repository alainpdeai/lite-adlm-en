# -*- coding: utf-8 -*-
"""
Pre-commit gate: run the fast grading subset and block the commit if it fails.

Continuous Integration P1. This repository is local-only by design — no remote, no CI — and
a full grading run is ~2m13s, long enough that whether it
runs is a matter of remembering to. A missed run used to produce no feedback at
all. This gate fixes that: the fast subset (~19s, see FAST_SET in
tests/run_grade_checks.py) runs on every commit, and a failure stops it.

Skip channel. A commit sometimes has to go through ungraded (half-finished
work, a repo that owns no graders). Skipping must be explicit AND justified:

    LITETASK_SKIP_GRADES=1 LITETASK_SKIP_REASON="why" git commit ...

The flag without a reason is refused, and every skip is appended to
.git/litetask-grade-skip.log with a timestamp — so "the gate was skipped"
stays auditable instead of quietly becoming a habit.

Offline. This machine carries an http_proxy that breaks localhost calls, and
the graders reach the server on 127.0.0.1. Every proxy variable is cleared for
the child process and NO_PROXY is pinned, so nothing here can be diverted or
stalled by a proxy. Nothing in this path touches the network.
"""
import os
import subprocess
import sys
import time

# Where the graders live, derived from this file. LITETASK_REPO overrides it
# so the hook is not welded to one checkout.
TODO_REPO = os.environ.get("LITETASK_REPO") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
RUNNER = os.path.join(TODO_REPO, "tests", "run_grade_checks.py")

SKIP_FLAG = "LITETASK_SKIP_GRADES"
SKIP_REASON = "LITETASK_SKIP_REASON"
PROXY_VARS = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
              "ALL_PROXY", "all_proxy")


def clean_env():
    """Offline by construction: no proxy can intercept 127.0.0.1."""
    env = dict(os.environ)
    for v in PROXY_VARS:
        env.pop(v, None)
    env["NO_PROXY"] = "localhost,127.0.0.1"
    env["no_proxy"] = "localhost,127.0.0.1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def skip_log_path():
    # git runs hooks with cwd = the repository root
    return os.path.join(os.getcwd(), ".git", "litetask-grade-skip.log")


def main():
    if os.environ.get(SKIP_FLAG):
        reason = (os.environ.get(SKIP_REASON) or "").strip()
        if not reason:
            print("litetask gate: %s is set but %s is empty." % (SKIP_FLAG, SKIP_REASON))
            print("  skipping is allowed, but never silently. re-run with:")
            print("    %s=1 %s=\"why this commit skips grading\" git commit ..."
                  % (SKIP_FLAG, SKIP_REASON))
            return 1
        try:
            with open(skip_log_path(), "a", encoding="utf-8") as f:
                f.write("%s  %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"), reason))
        except OSError as e:
            print("litetask gate: could not record the skip reason (%s)" % e)
            return 1
        print("litetask gate: SKIPPED, reason recorded -> %s" % skip_log_path())
        print("  reason: %s" % reason)
        return 0

    if not os.path.isfile(RUNNER):
        print("litetask gate: no graders at %s" % RUNNER)
        print("  point LITETASK_REPO at the checkout that owns tests/, or skip with")
        print("    %s=1 %s=\"...\"" % (SKIP_FLAG, SKIP_REASON))
        print("  not blocking: a missing gate is a configuration problem, not a regression")
        return 0

    print("litetask gate: running the fast grading subset ...")
    p = subprocess.run([sys.executable, RUNNER, "--fast"],
                       env=clean_env(), cwd=TODO_REPO)
    if p.returncode != 0:
        print()
        print("litetask gate: FAILED — commit blocked.")
        print("  fix the failure above, or commit with an explicit recorded reason:")
        print("    %s=1 %s=\"...\" git commit ..." % (SKIP_FLAG, SKIP_REASON))
        return 1
    print("litetask gate: green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
