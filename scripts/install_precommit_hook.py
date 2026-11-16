# -*- coding: utf-8 -*-
"""
Install the pre-commit gate (Continuous Integration P1).

    python scripts/install_precommit_hook.py                 # this repo
    python scripts/install_precommit_hook.py --repo <path>   # one repo

Copies scripts/pre-commit into <repo>/.git/hooks/pre-commit and marks it
executable, then verifies the copy is byte-identical to the source. Git ignores
a hook that is not executable, and a stale copy is worse than none — it would
look installed while running old logic — so both are checked here.

Local-only by design: this repository has no remote and no CI, so this hook
*is* the continuous integration.
"""
import os
import stat
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "pre-commit")

DEFAULT_REPOS = [
    os.environ.get("LITETASK_REPO") or os.path.dirname(HERE),
]


def install(repo):
    hooks = os.path.join(repo, ".git", "hooks")
    if not os.path.isdir(hooks):
        return "%s: not a git checkout (no %s)" % (repo, hooks)
    target = os.path.join(hooks, "pre-commit")
    with open(SOURCE, "rb") as f:
        src = f.read()
    with open(target, "wb") as f:
        f.write(src)
    os.chmod(target, os.stat(target).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    with open(target, "rb") as f:
        if f.read() != src:
            return "%s: copy is not byte-identical" % repo
    if not os.access(target, os.X_OK):
        return "%s: copy is not executable" % repo
    return "%s: installed %s (%d bytes, executable)" % (repo, target, len(src))


def main():
    args = sys.argv[1:]
    if "--repo" in args:
        i = args.index("--repo")
        repos = [args[i + 1]] if i + 1 < len(args) else []
    else:
        repos = DEFAULT_REPOS
    if not repos:
        print("usage: install_precommit_hook.py [--repo <path>]")
        return 1
    bad = 0
    for r in repos:
        msg = install(r)
        print(msg)
        if "installed" not in msg:
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
