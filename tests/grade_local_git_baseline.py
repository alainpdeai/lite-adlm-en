# Auto-generated
# -*- coding: utf-8 -*-
"""
Grader for the local git baseline of this repository.

Recorded claim: the repository checkout is a real git repository — initialised,
carrying real history, with a backup remote (origin, GitHub private repo,
added 2026-11-09 per user decision) whose main branch matches local HEAD, and
core.autocrlf pinned to false so git never rewrites line endings.
LITETASK_REPO can point this grader at another checkout.
"""
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import ROOT, Checker  # noqa: E402

c = Checker("local-git-baseline")

REPOS = [
    ("repo", os.environ.get("LITETASK_REPO") or ROOT),
]


def git(repo_path, *argv):
    p = subprocess.run(["git", "-C", repo_path, *argv],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=30)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


for name, path in REPOS:
    print("== %s (%s) ==" % (name, path))
    rc, out, _ = git(path, "rev-parse", "--is-inside-work-tree")
    c.check("%s is a git repository" % name, rc == 0 and out == "true", (rc, out))

    rc, out, _ = git(path, "rev-list", "--count", "HEAD")
    c.check("%s carries real history (>= 1 commits)" % name,
            rc == 0 and int(out or "0") >= 1, out)

    # 2026-11-09: user decided to push a private GitHub backup (origin).
    # The baseline moved from "local-only" to "backup remote configured and
    # in sync": local main must equal origin/main, and the working tree must
    # not carry unpushed commits relative to it.
    rc, out, _ = git(path, "remote")
    c.check("%s has the backup remote (origin) configured" % name,
            rc == 0 and "origin" in out.split(), out or "(empty)")

    rc, out, err = git(path, "fetch", "origin", "--quiet")
    rc, local, _ = git(path, "rev-parse", "HEAD")
    rc2, remote, _ = git(path, "rev-parse", "origin/main") if rc == 0 else (1, "", "")
    c.check("%s local HEAD == origin/main (backup in sync)" % name,
            rc == 0 and rc2 == 0 and local == remote, (local, remote))

    rc, out, _ = git(path, "config", "core.autocrlf")
    c.check("%s pins core.autocrlf=false (line endings never rewritten)" % name,
            out == "false", out)

    rc, out, err = git(path, "log", "--oneline", "-1")
    c.check("%s HEAD resolves to a commit" % name, rc == 0 and bool(out),
            (rc, err[-150:]))

c.finish()
