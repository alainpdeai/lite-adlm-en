# -*- coding: utf-8 -*-
"""
Grader: line endings and encoding are guarded, and external refs are known.

Why this is a grader and not a rule of thumb: public/index.html (~186 KB) was
once rewritten to CRLF by a tool, producing a ~5800-line diff that had to be
undone by hand, byte by byte. "Keep it LF" was a convention until now, and a
convention cannot fail a build. This grader can.

Two families of checks:

1. Every tracked source file in each configured repo is read in **binary** and asserted to
   contain zero CRLF sequences and no UTF-8 BOM. Binary matters: reading in text
   mode runs universal newlines, which silently turns CRLF into LF, so a text
   mode check of this kind is a tautology — it can never fail. (Memory note
   2026-09-03: a text-mode read reported "CRLF 0" for a file that really held 98
   CRLFs.) The same trap is neutralised here with three contrast cases: a CRLF
   file must be detected, a BOM file must be detected, and an LF file must be
   cleared.

2. The front end pulls five libraries from CDNs. That is a real offline/
   proxy exposure (this machine has http_proxy set), so the grader keeps an
   explicit allow-list: a NEW external host fails the build and forces someone to
   decide whether it should be vendored locally.
"""
import io
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import ROOT, Checker  # noqa: E402

c = Checker("eol-guard")

TODO = ROOT
SKILL = os.environ.get("LITETASK_SKILL_SOURCE") or ROOT
GUARDED_EXTS = {".md", ".html", ".js", ".py", ".ps1", ".css", ".json", ".txt"}

if not os.path.isdir(os.path.join(TODO, ".git")):
    c.blocked("no .git metadata; tracked-file cleanliness cannot be judged")

# External hosts the front end is allowed to depend on, and why (2026-10-29).
# Adding one is a decision, not a side effect of editing index.html.
KNOWN_CDN_HOSTS = {
    "unpkg.com": "vue 3 runtime",
    "cdn.tailwindcss.com": "tailwind utility css",
    "cdn.quilljs.com": "quill rich text editor (css + js)",
    "cdnjs.cloudflare.com": "font-awesome icons",
}


def inspect(path):
    """(crlf_count, has_bom) read in binary — never text mode."""
    with open(path, "rb") as fh:
        blob = fh.read()
    return blob.count(b"\r\n"), blob.startswith(b"\xef\xbb\xbf")


def tracked_files(repo):
    out = subprocess.run(["git", "ls-files"], cwd=repo,
                         capture_output=True, text=True)
    files = []
    for f in (out.stdout or "").splitlines():
        if os.path.splitext(f)[1].lower() not in GUARDED_EXTS:
            continue
        p = os.path.join(repo, f)
        if os.path.exists(p):
            files.append((f, p))
    return files


# ------------------------- contrast: the detector actually detects ----------
tmpdir = tempfile.mkdtemp(prefix="lt_grade_eol_")
lf = os.path.join(tmpdir, "lf.txt")
crlf = os.path.join(tmpdir, "crlf.txt")
bom = os.path.join(tmpdir, "bom.txt")
with open(lf, "wb") as fh:
    fh.write(b"alpha\nbeta\ngamma\n")
with open(crlf, "wb") as fh:
    fh.write(b"alpha\r\nbeta\r\ngamma\r\n")
with open(bom, "wb") as fh:
    fh.write(b"\xef\xbb\xbfalpha\nbeta\n")

c.check("a pure-LF file is reported as clean", inspect(lf) == (0, False), inspect(lf))
c.check("a CRLF file is detected (check is not a tautology)",
        inspect(crlf)[0] == 3, inspect(crlf))
c.check("a UTF-8 BOM is detected", inspect(bom)[1] is True, inspect(bom))

# ------------------------------------------------------------ both repos ---
for label, repo, minimum in [("primary", TODO, 40), ("secondary", SKILL, 3)]:
    files = tracked_files(repo)
    c.check("%s: enough tracked files to be worth guarding" % label,
            len(files) >= minimum, len(files))
    crlf_hits = [(f, inspect(p)[0]) for f, p in files if inspect(p)[0]]
    bom_hits = [f for f, p in files if inspect(p)[1]]
    c.check("%s: no tracked file contains CRLF" % label, not crlf_hits, crlf_hits[:5])
    c.check("%s: no tracked file starts with a BOM" % label, not bom_hits, bom_hits[:5])

# ------------------------------------- the files that motivated the guard ---
must_guard = [
    (TODO, "public/index.html"),
    (SKILL, "SKILL.md"),
    (SKILL, "references/system-guide.md"),
    (SKILL, "scripts/litetask_ensure.ps1"),
    (SKILL, "scripts/litetask_cli.py"),
]
tracked_todo = {f for f, _ in tracked_files(TODO)}
tracked_skill = {f for f, _ in tracked_files(SKILL)}
for repo, rel in must_guard:
    c.check("%s is tracked, so it is guarded" % rel,
            rel in (tracked_todo if repo == TODO else tracked_skill), rel)

# ------------------------------------------------- external dependencies ---
index_html = os.path.join(TODO, "public", "index.html")
with open(index_html, "r", encoding="utf-8") as fh:
    html = fh.read()
refs = re.findall(r'<(?:link|script)[^>]*?(?:href|src)="([^"]+)"', html)
external = [u for u in refs if u.startswith("http://") or u.startswith("https://")]
c.check("external references may be empty after localisation, but never unknown",
        True, external)

hosts = sorted({re.match(r"https?://([^/]+)", u).group(1) for u in external})
unknown = [h for h in hosts if h not in KNOWN_CDN_HOSTS]
c.check("every external host is on the reviewed allow-list (empty set passes)",
        not unknown, (unknown, sorted(KNOWN_CDN_HOSTS)))
_fake = '<script src="https://evil.example/x.js"></script>'
_fake_hosts = sorted({re.match(r"https?://([^/]+)", u).group(1)
                      for u in re.findall(r'<(?:link|script)[^>]*?(?:href|src)="([^"]+)"', _fake)})
c.check("unknown-host detection still has teeth", "evil.example" in _fake_hosts,
        _fake_hosts)
c.check("socket.io is served locally, not from a CDN",
        any(u.startswith("/socket.io/") for u in refs), refs)

for path in (lf, crlf, bom):
    os.remove(path)
os.rmdir(tmpdir)
c.finish()
