#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Check the capability index at the top of references/system-guide.md (Knowledge Entry P2).

The guide passed 84 KB and 36 sections. That is the whole problem: an entry
point that large is an entry point you cannot find things in, and the 2026-10-29
incident it grew out of was exactly a misjudgement — a capability was assumed
missing when it had been implemented and documented all along.

So the guide now carries an index at the top, one row per capability:

    | Capability | File | Section (Title) | Anchor (Distinctive text in section) |

and this script re-derives every row:

  * the file exists;
  * the section heading still exists, and exactly once — duplicate section
    numbers are a real failure mode in this document (§31 and §32 each occur
    twice), so the index keys on the heading TEXT, never on the number;
  * the anchor text still occurs inside that section's range, i.e. between that
    heading and the next one. An anchor that merely exists somewhere in the file
    would pass while the explanation had moved somewhere else.

Exit 0 = the index still points where it says. Exit 1 = it has gone stale, with
the offending rows named. Run it from anywhere; `tests/grade_doc_index.py`
wraps it so a stale index fails the grading suite too.
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE = os.path.join(REPO, "references", "system-guide.md")
INDEX_HEADING_RE = re.compile(r"^##\s*0\.")
HEADING_RE = re.compile(r"^##\s+")
MIN_ROWS = 15


def strip_cell(s):
    s = s.strip()
    if s.startswith("`") and s.endswith("`") and len(s) > 1:
        s = s[1:-1]
    return s.strip()


def read_index(text):
    """Return the rows of the first markdown table under the §0 heading."""
    lines = text.splitlines()
    start = None
    for n, line in enumerate(lines):
        if INDEX_HEADING_RE.match(line):
            start = n
            break
    if start is None:
        return None, "no '## 0.' index heading found in system-guide.md"
    rows = []
    for line in lines[start:]:
        if HEADING_RE.match(line) and not INDEX_HEADING_RE.match(line):
            break                      # the next section ends the index
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        if set(cells[0]) <= set("-: "):
            continue                   # separator row
        if cells[0].lower().startswith("capability") or cells[0].strip().startswith("\u80fd\u529b"):
            continue                   # header row
        rows.append(cells)
    return rows, None


def norm_title(t):
    """Strip a leading '§12 ' / '12. ' / '§12 ' so all of them match '## 12. …'.

    The number may or may not be followed by a separator, because an index row
    is written by hand and '§19 Traceability' is as natural as '§19. …'.
    """
    t = re.sub(r"^§\s*", "", t.strip())
    t = re.sub(r"^\d+\s*[.、)]?\s*", "", t.strip())
    return t.strip()


def section_range(text, heading):
    """Return (start_offset, end_offset) of a `## ` section, or None."""
    lines = text.splitlines()
    target = None
    for n, line in enumerate(lines):
        if line.startswith("## ") and norm_title(line[3:]) == norm_title(heading):
            if target is not None:
                return None, "heading occurs more than once"
            target = n
    if target is None:
        return None, "heading not found"
    end = len(lines)
    for n in range(target + 1, len(lines)):
        if lines[n].startswith("## "):
            end = n
            break
    start_offset = len("\n".join(lines[:target])) + (1 if target else 0)
    end_offset = len("\n".join(lines[:end]))
    return (start_offset, end_offset), None


def main():
    if not os.path.exists(GUIDE):
        print("FAIL system-guide.md not found: %s" % GUIDE)
        return 1
    with open(GUIDE, encoding="utf-8") as f:
        text = f.read()

    rows, err = read_index(text)
    if err:
        print("FAIL %s" % err)
        return 1
    if len(rows) < MIN_ROWS:
        print("FAIL the index lists %d rows; at least %d are expected — an "
              "index that thin is not an index" % (len(rows), MIN_ROWS))
        return 1

    failures = []
    for cells in rows:
        cap, rel, sect, anchor = cells[0], cells[1], cells[2], cells[3]
        cap, rel = strip_cell(cap), strip_cell(rel)
        sect, anchor = strip_cell(sect), strip_cell(anchor)
        # "§12 Hiding completed work" -> heading text without the number
        heading = norm_title(sect)

        fpath = os.path.join(REPO, rel)
        if not os.path.exists(fpath):
            failures.append("%s -> missing file %s" % (cap, rel))
            continue
        with open(fpath, encoding="utf-8") as fh:
            ftext = fh.read()
        rng, why = section_range(ftext, heading)
        if rng is None:
            failures.append("%s -> section %r: %s" % (cap, heading, why))
            continue
        seg = ftext[rng[0]:rng[1]]
        if anchor not in seg:
            where = "elsewhere in the file" if anchor in ftext else "nowhere in the file"
            failures.append("%s -> anchor %r is %s (expected inside § %s)"
                            % (cap, anchor, where, heading))
            continue
        print("  ok   %-34s %s | %s" % (cap[:34], rel, heading[:44]))

    print()
    print("index rows checked: %d" % len(rows))
    if failures:
        print("RESULT doc-index: FAIL (%d of %d rows stale)"
              % (len(failures), len(rows)))
        for f in failures:
            print("   - " + f)
        return 1
    print("RESULT doc-index: PASS (%d rows)" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
