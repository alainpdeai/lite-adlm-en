# -*- coding: utf-8 -*-
"""
P1-3 grader: delivery baseline is verdictable, or honestly BLOCKED.

Exit codes: 0 = PASS/PARTIAL, 1 = FAIL, 3 = BLOCKED (no .git).

When .git is absent the only truthful result is BLOCKED: the grader must not
print "working tree clean" or "hook installed", because neither is knowable.
"""
import hashlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("LITETASK_REPO") or os.path.dirname(HERE)
NAME = "delivery-baseline"


def sh(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def finish(result, checks, failures, code):
    print()
    print("RESULT %s: %s (%d checks)" % (NAME, result, checks))
    for f in failures:
        print("   - " + f)
    sys.exit(code)


def main():
    passed, failed = [], []

    def check(label, cond, detail=""):
        if cond:
            passed.append(label)
            print("  ok   %s" % label)
        else:
            failed.append(label)
            print("  FAIL %s   %s" % (label, detail))

    print("== probe ==")
    git_dir = os.path.join(ROOT, ".git")
    git_ok = os.path.isdir(git_dir)
    print("  $ test -d .git -> %s" % ("present" if git_ok else "MISSING"))
    if not git_ok:
        st = sh(["git", "status", "--porcelain"])
        print("  $ git status --porcelain 2>&1")
        print("    " + ((st.stdout or st.stderr).strip() or "(empty)"))
        print()
        print("  BLOCKED: .git metadata is missing; working-tree cleanliness and")
        print("  hook installation cannot be judged. Restore .git, then re-run this")
        print("  grader. See docs/records/p1_delivery_baseline.md.")
        finish("BLOCKED", 1, ["git metadata missing (BLOCKED, not PASS)"], 3)

    # ------------------------------------------------ git available branch
    st = sh(["git", "status", "--porcelain"])
    dirty = [line for line in (st.stdout or "").splitlines() if line.strip()]
    check("git status is readable", st.returncode == 0, st.stderr[:200])

    records = os.path.join(ROOT, "docs", "records", "p1_delivery_baseline.md")
    exceptions = ""
    if os.path.exists(records):
        with open(records, encoding="utf-8", errors="replace") as f:
            exceptions = f.read()
    missing = [line for line in dirty if line.split()[-1].replace("\\", "/") not in exceptions]
    check("working tree clean OR every change has an exception row",
          not missing, missing[:5])

    deletions = [line for line in dirty if re.match(r"^\s*D\s+docs/", line)]
    docs_ok = True
    for line in deletions:
        path = line.split()[-1]
        row = [x for x in exceptions.splitlines() if path in x]
        if not row:
            docs_ok = False
    check("every docs deletion has a disposition row", docs_ok, deletions[:5])

    hook = os.path.join(git_dir, "hooks", "pre-commit")
    src = os.path.join(ROOT, "scripts", "pre-commit")
    check("pre-commit hook exists", os.path.isfile(hook), hook)
    if os.path.isfile(hook) and os.path.isfile(src):
        h1 = hashlib.sha256(open(hook, "rb").read()).hexdigest()
        h2 = hashlib.sha256(open(src, "rb").read()).hexdigest()
        check("hook is byte-identical to scripts/pre-commit", h1 == h2, (h1[:8], h2[:8]))
    else:
        check("hook is byte-identical to scripts/pre-commit", False, "missing file")

    executable = os.access(hook, os.X_OK) if os.path.exists(hook) else False
    if not executable and os.name == "nt":
        print("  note: Windows has no POSIX execute bit; equivalent command:")
        print("        python scripts/precommit_grades.py")

    # ------------------------------------------------------- bypass traces
    # Two sources are echoes, not usage: (a) the disposition record itself must
    # be able to *name* the forbidden option in order to forbid it, and (b) the
    # raw grader logs under tests/_artifacts/_gate print the assertion text
    # verbatim on every run. What must not appear is an actual usage trace in
    # the hand-written records.
    records_abs = os.path.abspath(records)
    raw_logs = os.path.abspath(os.path.join(ROOT, "tests", "_artifacts", "_gate"))
    trace = ""
    for base in (os.path.join(ROOT, "docs", "records"),
                 os.path.join(ROOT, "tests", "_artifacts")):
        if not os.path.isdir(base):
            continue
        for dp, _dn, fs in os.walk(base):
            dp_abs = os.path.abspath(dp)
            if dp_abs == raw_logs or dp_abs.startswith(raw_logs + os.sep):
                continue
            for f in fs:
                if f.endswith((".md", ".txt")):
                    path = os.path.join(dp, f)
                    if os.path.abspath(path) == records_abs:
                        continue
                    try:
                        trace += open(path, encoding="utf-8", errors="replace").read()
                    except Exception:
                        pass
    check("no --no-verify / hook-removal traces in delivery records",
          "--no-verify" not in trace, "bypass trace found")

    if failed:
        finish("FAIL", len(passed) + len(failed), failed, 1)
    if not executable and os.name == "nt":
        print("  PARTIAL: hook exists and matches, but POSIX execute bit is not testable")
        finish("PARTIAL", len(passed) + len(failed), failed, 0)
    finish("PASS", len(passed) + len(failed), failed, 0)


if __name__ == "__main__":
    main()