# -*- coding: utf-8 -*-
"""Extract & initialize a clean Lite ADLM system from upstream runtime + governance assets.

Selective copy:
  - runtime code (server.js, lib/, public/, package*.json)
  - quality gate assets (tests/, docs/)
  - governance assets (GOAL.md, SKILL.md, FROZEN.md, references/, scripts/)
  - data seed: data/categories.json only (class definitions, NO task items)
Excluded: node_modules, *.log, project.tar.gz, backup/,
          data/shared_lists/*, data/archive/*, data/users*, data/archive-snapshots/*,
          __pycache__, *.pyc, tests temp artifacts (_artifacts, _exam_backup_*, *.png, _out_*.txt).
"""
import os
import shutil
import json
import fnmatch

SRC_TODO = os.environ.get("ADLM_SRC_RUNTIME") or r"<UPSTREAM_RUNTIME_ROOT>"
SRC_PM = os.environ.get("ADLM_SRC_GOVERNANCE") or r"<UPSTREAM_GOVERNANCE_ROOT>"
DST = os.environ.get("ADLM_DST") or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_IGNORE_NAMES = {"__pycache__"}
DEFAULT_IGNORE_PATTERNS = ["*.pyc"]


def copytree(src, dst, extra_names=None, extra_patterns=None):
    names = set(DEFAULT_IGNORE_NAMES) | (extra_names or set())
    pats = list(DEFAULT_IGNORE_PATTERNS) + (extra_patterns or [])

    def _ig(dirpath, entries):
        drop = set()
        for n in entries:
            if n in names:
                drop.add(n)
                continue
            if any(fnmatch.fnmatch(n, p) for p in pats):
                drop.add(n)
        return drop

    shutil.copytree(src, dst, ignore=_ig, copy_function=shutil.copy2)


def copy_file(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def banner(msg):
    print("== " + msg + " ==")


# safety: never clobber an existing non-empty target
if os.path.exists(DST) and any(os.scandir(DST)):
    raise SystemExit("ABORT: %s already has content; refusing to overwrite." % DST)
os.makedirs(DST, exist_ok=True)

# 1) runtime root files
banner("runtime root")
copy_file(os.path.join(SRC_TODO, "server.js"), os.path.join(DST, "server.js"))
copy_file(os.path.join(SRC_TODO, "package-lock.json"), os.path.join(DST, "package-lock.json"))

# 1b) package.json renamed
banner("package.json (rename -> lite-adlm)")
with open(os.path.join(SRC_TODO, "package.json"), encoding="utf-8") as f:
    pkg = json.load(f)
pkg["name"] = "lite-adlm"
pkg["description"] = "Lite ADLM - Lightweight Web Task Manager / Structured Memory (Standalone Deployable System)"
with open(os.path.join(DST, "package.json"), "w", encoding="utf-8") as f:
    json.dump(pkg, f, indent=2, ensure_ascii=False)
    f.write("\n")

# 2) lib / public
banner("lib/")
copytree(os.path.join(SRC_TODO, "lib"), os.path.join(DST, "lib"))
banner("public/")
copytree(os.path.join(SRC_TODO, "public"), os.path.join(DST, "public"))

# 3) tests (exclude temp artifacts)
banner("tests/")
copytree(
    os.path.join(SRC_TODO, "tests"),
    os.path.join(DST, "tests"),
    extra_names={"_artifacts"},
    extra_patterns=["_exam_backup_*.json", "*.png", "_out_*.txt"],
)

# 4) docs
banner("docs/")
copytree(os.path.join(SRC_TODO, "docs"), os.path.join(DST, "docs"))

# 5) governance markdown
banner("governance md")
for fn in ["GOAL.md", "SKILL.md", "FROZEN.md"]:
    copy_file(os.path.join(SRC_PM, fn), os.path.join(DST, fn))

# 6) references
banner("references/")
copytree(os.path.join(SRC_PM, "references"), os.path.join(DST, "references"))

# 7) scripts (exclude pycache)
banner("scripts/")
copytree(os.path.join(SRC_PM, "scripts"), os.path.join(DST, "scripts"))

# 8) data seed: categories.json only + .gitkeep
banner("data seed (categories.json only)")
dstdat = os.path.join(DST, "data")
os.makedirs(dstdat, exist_ok=True)
src_cat = os.path.join(SRC_TODO, "data", "categories.json")
if os.path.exists(src_cat):
    copy_file(src_cat, os.path.join(dstdat, "categories.json"))
else:
    print("WARN: categories.json not found at", src_cat)
with open(os.path.join(dstdat, ".gitkeep"), "w", encoding="utf-8") as f:
    f.write("")

# report
banner("RESULT tree")
total = 0
for root, dirs, files in os.walk(DST):
    if ".git" in root:
        continue
    rel = os.path.relpath(root, DST)
    if rel == ".":
        rel = "<root>"
    total += len(files)
    print("%-30s %d files" % (rel + "/", len(files)))
print("TOTAL files copied:", total)
