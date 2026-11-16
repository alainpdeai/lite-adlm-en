#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a history-free delivery copy of this system from the current HEAD.

Why this exists
---------------
The working tree is de-identified, but ``.git`` history still carries early
commit messages and the names of files that were later deleted.  Rewriting
history is destructive (it changes every commit hash and cannot retroactively
scrub every old blob), so delivery is done with ``git archive HEAD`` instead:
the archive contains exactly the tracked files at HEAD and no repository
metadata at all.  The development checkout keeps its full history.

Usage (run from anywhere; paths are resolved from this file)
-----------------------------------------------------------
    python scripts/package_delivery.py                       # zip + unpacked dir
    python scripts/package_delivery.py --dir <dir>           # custom target dir
    python scripts/package_delivery.py --out <file.zip>      # custom zip path
    python scripts/package_delivery.py --no-zip              # unpacked dir only
    python scripts/package_delivery.py --verify <dir>        # verify an existing copy

Defaults: the zip and the unpacked directory are created *next to* the repo
(siblings), never inside it, so packaging cannot dirty the working tree.

Built-in verification (no project-specific names are hard-coded here)
--------------------------------------------------------------------
  * the delivery directory contains no ``.git`` directory;
  * its file set equals ``git ls-tree -r --name-only HEAD`` exactly;
  * every file is byte-identical to the corresponding archive member;
  * the zip passes ``ZipFile.testzip()`` (CRC check);
  * a generic scan REPORTS absolute machine paths / user-home paths in text
    files.  It matches path *shapes*, never a list of names, so this script
    itself stays free of project identifiers.  These are warnings, not errors:
    a browser-launch probe and a UI placeholder legitimately contain generic
    drive-letter examples.  Add --strict-paths to turn every hit into a failure.

Exit code is 0 only when the hard guarantees pass (plus path hits in strict
mode).  The development checkout's history is never rewritten.
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PARENT = os.path.dirname(REPO)
DEFAULT_ZIP = os.path.join(PARENT, "ADLM_delivery.zip")
DEFAULT_DIR = os.path.join(PARENT, "ADLM_delivery")

TEXT_EXT = {".md", ".json", ".js", ".py", ".html", ".css", ".ps1", ".sh",
            ".txt", ".yml", ".yaml", ".ts", ".tsx", ".gitignore",
            ".gitattributes"}
TEXT_NAMES = {"pre-commit", ".gitignore", ".gitattributes"}

# Path *shapes*, not names: a drive-letter path, or a Unix home directory.
# The negative lookbehind keeps "http://..." and "<PLACEHOLDER>/..." out.
ABS_PATH = re.compile(
    r"(?<![\w<])(?:[A-Za-z]:[\\/](?!/)|/(?:Users|home)/)[^\s\"'`|)\]%]{2,}")


def git(*argv):
    p = subprocess.run(["git", *argv], cwd=REPO, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(argv), p.stderr.strip()))
    return p.stdout


def build_zip(zip_path):
    os.makedirs(os.path.dirname(os.path.abspath(zip_path)), exist_ok=True)
    subprocess.run(["git", "archive", "--format=zip", "-o", zip_path, "HEAD"],
                   cwd=REPO, check=True)
    return zip_path


def extract(zip_path, dest):
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    elif os.path.exists(dest):
        raise RuntimeError("target exists and is not a directory: %s" % dest)
    os.makedirs(dest)
    with zipfile.ZipFile(zip_path) as z:
        bad = z.testzip()
        if bad:
            raise RuntimeError("zip CRC failure at member: %s" % bad)
        z.extractall(dest)
    return dest


def walk_files(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for f in filenames:
            rel = os.path.relpath(os.path.join(dirpath, f), root)
            out.append(rel.replace("\\", "/"))
    return sorted(out)


def scan_paths(root):
    hits = []
    for rel in walk_files(root):
        ext = os.path.splitext(rel)[1].lower()
        base = os.path.basename(rel)
        if ext not in TEXT_EXT and base not in TEXT_NAMES:
            continue
        path = os.path.join(root, rel)
        try:
            blob = open(path, "rb").read()
        except OSError:
            continue
        for m in ABS_PATH.finditer(blob.decode("utf-8", "replace")):
            hits.append((rel, m.group(0)[:90]))
    return hits


def verify(dest, zip_path=None, verbose=True, strict_paths=False):
    errors = []
    info = {}

    if not os.path.isdir(dest):
        return ["delivery directory does not exist: %s" % dest], info
    if os.path.isdir(os.path.join(dest, ".git")):
        errors.append("delivery directory still contains a .git directory")

    try:
        tracked = sorted(x.strip() for x in
                         git("ls-tree", "-r", "--name-only", "HEAD").splitlines()
                         if x.strip())
    except RuntimeError:
        # Verifying from inside the delivered copy is legitimate: it has no
        # .git, so the HEAD-tree comparison is simply unavailable there.
        tracked = None
    actual = walk_files(dest)
    info["tracked"] = len(tracked) if tracked is not None else "n/a"
    info["files"] = len(actual)
    if tracked is not None and sorted(actual) != tracked:
        missing = sorted(set(tracked) - set(actual))
        extra = sorted(set(actual) - set(tracked))
        errors.append("file set differs from HEAD (missing=%d extra=%d): %s %s"
                      % (len(missing), len(extra), missing[:5], extra[:5]))

    if zip_path and os.path.isfile(zip_path):
        with zipfile.ZipFile(zip_path) as z:
            members = [i for i in z.infolist() if not i.is_dir()]
            info["zip_members"] = len(members)
            checked = 0
            for m in members:
                disk = os.path.join(dest, m.filename)
                if not os.path.isfile(disk):
                    errors.append("missing extracted file: %s" % m.filename)
                    continue
                if hashlib.sha256(z.read(m)).digest() != \
                        hashlib.sha256(open(disk, "rb").read()).digest():
                    errors.append("byte mismatch: %s" % m.filename)
                checked += 1
            info["byte_checked"] = checked

    hits = scan_paths(dest)
    info["abs_path_hits"] = len(hits)
    info["abs_path_samples"] = hits[:10]
    if strict_paths:
        for rel, sample in hits[:10]:
            errors.append("absolute machine path in %s: %s" % (rel, sample))
        if len(hits) > 10:
            errors.append("... and %d more absolute-path hits" % (len(hits) - 10))

    if verbose:
        print("  HEAD tracked files     : %s" % info.get("tracked"))
        print("  HEAD tree comparison   : %s" %
              ("done" if info.get("tracked") != "n/a"
               else "skipped (no .git — expected inside a delivery copy)"))
        print("  delivered files        : %s" % info.get("files"))
        if "byte_checked" in info:
            print("  byte-identical to HEAD : %s" % info["byte_checked"])
        print("  .git present           : %s" %
              ("YES" if os.path.isdir(os.path.join(dest, ".git")) else "no"))
        print("  absolute-path hits     : %s (warnings%s)" %
              (info.get("abs_path_hits"),
               "; strict mode" if strict_paths else ", use --strict-paths to fail"))
        for rel, sample in info.get("abs_path_samples", []):
            print("    WARN %s -> %s" % (rel, sample))
    return errors, info


def main():
    ap = argparse.ArgumentParser(description="Build a history-free delivery copy")
    ap.add_argument("--out", default=DEFAULT_ZIP, help="zip output path")
    ap.add_argument("--dir", default=DEFAULT_DIR, help="unpacked directory")
    ap.add_argument("--no-zip", action="store_true", help="skip the zip artifact")
    ap.add_argument("--verify", metavar="DIR", default=None,
                    help="only verify an already-built delivery directory")
    ap.add_argument("--strict-paths", action="store_true",
                    help="treat absolute machine-path hits as failures")
    args = ap.parse_args()

    if args.verify:
        print("=== verify delivery copy: %s ===" % args.verify)
        zip_for_verify = (os.path.abspath(args.out)
                          if os.path.isfile(args.out) else None)
        errors, _ = verify(args.verify, zip_for_verify,
                           strict_paths=args.strict_paths)
        for e in errors:
            print("  FAIL  %s" % e)
        print("RESULT: %s" % ("FAIL (%d)" % len(errors) if errors else "PASS"))
        return 1 if errors else 0

    zip_path = None if args.no_zip else os.path.abspath(args.out)
    dest = os.path.abspath(args.dir)
    if os.path.abspath(dest) == REPO or dest.startswith(REPO + os.sep):
        print("FAIL: delivery directory must be OUTSIDE the repository")
        return 1
    if zip_path and (os.path.abspath(zip_path) == REPO or
                     zip_path.startswith(REPO + os.sep)):
        print("FAIL: zip output must be OUTSIDE the repository")
        return 1

    print("=== build history-free delivery copy ===")
    print("  repo     : %s" % REPO)
    print("  HEAD     : %s" % git("rev-parse", "--short", "HEAD").strip())
    if zip_path:
        build_zip(zip_path)
        print("  zip      : %s (%d bytes)" % (zip_path, os.path.getsize(zip_path)))
        extract(zip_path, dest)
    else:
        tmp_zip = os.path.join(PARENT, "_adlm_archive_tmp.zip")
        try:
            build_zip(tmp_zip)
            extract(tmp_zip, dest)
        finally:
            if os.path.exists(tmp_zip):
                os.remove(tmp_zip)
    print("  dir      : %s" % dest)

    print("=== verify ===")
    errors, _ = verify(dest, zip_path, strict_paths=args.strict_paths)
    for e in errors:
        print("  FAIL  %s" % e)
    print("RESULT: %s" % ("FAIL (%d)" % len(errors) if errors else "PASS"))
    print("\nPlease copy this directory when delivering (excluding .git); if version control is needed for target project, run git init yourself.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
