# AI-generated
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the self-contained Skill delivery package (LiteADLM).

Layout produced under dist/skill/LiteADLM/ (all files count toward the
platform's 40-file / 30 MB limits):

    SKILL.md                     # from repo root (usage contract)
    user.txt                     # submission metadata (unchanged by this script)
    LICENSE                      # Apache-2.0
    server.js                    # esbuild bundle: server.js + lib/ (31 modules) -> single file
    package.json                 # minimal: deps only, start script
    public/                      # index.html + vendor/ (VENDOR.json pins sha256)
    config/site.json             # brand + admin seed
    data/categories.json         # category seed (no task items)
    references/system-guide.md   # full contract doc
    scripts/litetask_cli.py      # deterministic CLI
    scripts/litetask_ensure.ps1  # one-shot idempotent launcher

The bundle keeps node_modules external (--packages=external): the evaluator
runs `npm install` once. __dirname references inside lib/ are rewritten
because after bundling the module root moves up one level.

Usage:
    python scripts/build_skill_package.py           # build into dist/skill/LiteADLM
    python scripts/build_skill_package.py --verify  # build + file-count/size budget check

Idempotent: dist/skill/LiteADLM is recreated from scratch each run.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DIST = os.path.join(REPO, "dist", "skill", "LiteADLM")

MAX_FILES = 40
MAX_BYTES = 30 * 1024 * 1024

KEEP_FILES = {
    "SKILL.md", "user.txt", "LICENSE",
}

VENDOR_DIR = os.path.join("public", "vendor")


def log(msg):
    print("[build-skill] " + msg)


def rewrite_lib_dirnames(tmp_lib):
    """lib modules use path.join(__dirname, '..', X) for repo-root paths.
    After bundling, the single file sits at the package root, so those
    references must become path.join(__dirname, X)."""
    fixes = [
        ("backup.js", re.compile(r"path\.join\(__dirname, '\.\.'\)"), "__dirname"),
        ("config.js", re.compile(r"path\.join\(__dirname, '\.\.', '(data|backup|config)'\)"),
         r"path.join(__dirname, '\1')"),
        ("csp.js", re.compile(r"path\.join\(__dirname, '\.\.', 'public', 'index\.html'\)"),
         r"path.join(__dirname, 'public', 'index.html')"),
    ]
    patched = []
    for name, pattern, repl in fixes:
        p = os.path.join(tmp_lib, name)
        if not os.path.isfile(p):
            continue
        with open(p, "r", encoding="utf-8", newline="") as f:
            src = f.read()
        out, n = pattern.subn(repl, src)
        if n:
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(out)
            patched.append("%s (%d)" % (name, n))
    return patched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true",
                    help="check file count and size budgets after build")
    args = ap.parse_args()

    esbuild_bin = os.path.join(REPO, "node_modules", "esbuild", "bin", "esbuild")
    if not os.path.isfile(esbuild_bin):
        log("FAIL: esbuild not found at %s (npm install --save-dev esbuild)" % esbuild_bin)
        return 1
    node = shutil.which("node")
    if not node:
        node = r"C:\Program Files\nodejs\node.exe"
        if not os.path.isfile(node):
            log("FAIL: node not found")
            return 1

    # fresh work dir (never delete the old target in place; move aside instead)
    work = os.path.join(REPO, "tests", "_artifacts", "_skill_build")
    if os.path.isdir(work):
        stamp = str(int(os.path.getmtime(work)))
        shutil.move(work, work + ".old-" + stamp)
    os.makedirs(os.path.join(work, "lib"))

    # 1) lib/ with __dirname rewrites + server.js entry
    for f in os.listdir(os.path.join(REPO, "lib")):
        if f.endswith(".js"):
            shutil.copy2(os.path.join(REPO, "lib", f), os.path.join(work, "lib", f))
    patched = rewrite_lib_dirnames(os.path.join(work, "lib"))
    log("lib __dirname rewrites: " + (", ".join(patched) if patched else "none"))
    shutil.copy2(os.path.join(REPO, "server.js"), os.path.join(work, "server.js"))

    # 2) esbuild bundle (31 modules -> one file, node_modules external)
    out_bundle = os.path.join(work, "server.js")
    cmd = [node, esbuild_bin, os.path.join(work, "server.js"), "--bundle",
           "--platform=node", "--packages=external",
           "--outfile=" + out_bundle + ".bundled"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log("FAIL: esbuild: " + (r.stderr or r.stdout)[:400])
        return 1
    os.replace(out_bundle + ".bundled", out_bundle)
    bundle_bytes = os.path.getsize(out_bundle)
    log("server.js bundle: %d bytes" % bundle_bytes)
    # staging lib/ must NOT enter the package: the bundle replaces it
    shutil.move(os.path.join(work, "lib"),
                os.path.join(REPO, "tests", "_artifacts", "_skill_lib_staging"))
    assert not os.path.exists(os.path.join(work, "lib")), "staging lib still present"

    # 3) minimal package.json
    with open(os.path.join(REPO, "package.json"), encoding="utf-8") as f:
        pkg = json.load(f)
    minimal = {
        "name": pkg["name"],
        "version": pkg["version"],
        "private": True,
        "description": pkg.get("description", ""),
        "main": "server.js",
        "engines": pkg.get("engines", {"node": ">=18"}),
        "scripts": {"start": "node server.js"},
        "dependencies": pkg.get("dependencies", {}),
    }
    with open(os.path.join(work, "package.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(minimal, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # 4) static assets: public/ (index.html + vendor), config/site.json, data seed
    shutil.copytree(os.path.join(REPO, "public"), os.path.join(work, "public"))
    os.makedirs(os.path.join(work, "config"))
    shutil.copy2(os.path.join(REPO, "config", "site.json"),
                 os.path.join(work, "config", "site.json"))
    os.makedirs(os.path.join(work, "data"))
    shutil.copy2(os.path.join(REPO, "data", "categories.json"),
                 os.path.join(work, "data", "categories.json"))

    # 5) docs + CLI scripts
    os.makedirs(os.path.join(work, "references"))
    shutil.copy2(os.path.join(REPO, "references", "system-guide.md"),
                 os.path.join(work, "references", "system-guide.md"))
    os.makedirs(os.path.join(work, "scripts"))
    for f in ("litetask_cli.py", "litetask_ensure.ps1"):
        shutil.copy2(os.path.join(REPO, "scripts", f),
                     os.path.join(work, "scripts", f))

    # 6) skill meta files (keep user.txt byte-identical)
    for f in ("SKILL.md", "LICENSE"):
        shutil.copy2(os.path.join(REPO, f), os.path.join(work, f))
    user_src = os.path.join(DIST, "user.txt")
    if os.path.isfile(user_src):
        shutil.copy2(user_src, os.path.join(work, "user.txt"))
    else:
        log("FAIL: existing user.txt not found in dist (build preserves it)")
        return 1

    # 7) publish: swap work dir into dist (old target moved aside, not deleted)
    if os.path.isdir(DIST):
        stamp = str(int(os.path.getmtime(DIST)))
        shutil.move(DIST, DIST + ".old-" + stamp)
    parent = os.path.dirname(DIST)
    os.makedirs(parent, exist_ok=True)
    shutil.move(work, DIST)
    log("published: " + DIST)

    # 8) optional budget verify
    if args.verify:
        files = []
        for dp, _dn, fn in os.walk(DIST):
            for n in fn:
                files.append(os.path.relpath(os.path.join(dp, n), DIST).replace("\\", "/"))
        total = sum(os.path.getsize(os.path.join(DIST, f)) for f in files)
        zpath = os.path.join(REPO, "tests", "_artifacts", "_skill_pkg_check.zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                z.write(os.path.join(DIST, f), f)
        zbytes = os.path.getsize(zpath)
        os.remove(zpath)
        print()
        print("  files        : %d (limit %d)" % (len(files), MAX_FILES))
        print("  uncompressed : %d bytes" % total)
        print("  zip size     : %d bytes (limit %d)" % (zbytes, MAX_BYTES))
        for f in sorted(files):
            print("    %8d  %s" % (os.path.getsize(os.path.join(DIST, f)), f))
        if len(files) > MAX_FILES or zbytes > MAX_BYTES:
            log("FAIL: over budget")
            return 1
        log("budget check PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
