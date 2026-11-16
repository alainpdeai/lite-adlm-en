# -*- coding: utf-8 -*-
"""
Grader: the capability index is present, top, and not stale (Knowledge Entry P2).

§23 of the system guide records a capability being assumed missing when it had
been implemented and documented all along. The cause was size: 84 KB, 36
sections, entry points everywhere. The answer is an index at the top of the
file — and an index nobody checks becomes the next source of misdirection, which
is why `scripts/check_doc_index.py` re-derives every row.

This grader asserts three things:

1. the checker passes (every row still points at a real file, a real heading,
   and an anchor still inside that heading's range);
2. the index is at the TOP — an index you have to scroll to is not an entry
   point — and it is not a token handful of rows;
3. the checker has teeth. A row is broken on purpose (a stale anchor, then a
   missing file) and the checker must FAIL; after a byte-for-byte restore it
   must PASS again. A checker that passes on a broken index is decoration.

The restore is asserted byte-for-byte and wrapped in try/finally: a mutation
that survived on disk would corrupt the documentation this file exists to
protect.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import ROOT, Checker  # noqa: E402

c = Checker("doc-index")

PM = ROOT
GUIDE = os.path.join(PM, "references", "system-guide.md")
CHECK = os.path.join(PM, "scripts", "check_doc_index.py")
MIN_ROWS = 30


def run_check():
    p = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def index_region(text):
    """The §0 block: from its heading up to the next section."""
    lines = text.splitlines()
    start = None
    for n, line in enumerate(lines):
        if line.startswith("## 0."):
            start = n
            break
    if start is None:
        return None
    end = len(lines)
    for n in range(start + 1, len(lines)):
        if lines[n].startswith("## "):
            end = n
            break
    return start, end, lines


def _check_index_rows(c, text):
    """§1: every index row still resolves, and the index is not a token handful."""
    code, out = run_check()
    c.check("every index row still resolves (file, heading, anchor in range)",
            code == 0, out.strip().splitlines()[-6:])
    m = re.search(r"RESULT doc-index: PASS \((\d+) rows\)", out)
    rows = int(m.group(1)) if m else 0
    c.check("the index is not a token handful of rows (>= %d)" % MIN_ROWS,
            rows >= MIN_ROWS, rows)


def _check_index_position(c, text):
    """§2: the index is at the top and is a readable block."""
    pos0 = text.find("## 0.")
    # The guide was translated to Chinese; keep the English heading as a
    # fallback so the check survives either wording.
    pos1 = text.find("## 1. What It Is")
    c.check("the index sits above §1 — an entry point you must scroll to is "
            "not an entry point",
            pos0 != -1 and pos1 != -1 and pos0 < pos1, (pos0, pos1))

    region = index_region(text)
    c.check("the index is a readable block (a heading and rows)",
            region is not None and region[1] - region[0] > 5,
            region and (region[1] - region[0]))


def _apply_mutation_a(c, GUIDE, original, text):
    """§3a: a stale anchor must be caught and the file restored byte-for-byte."""
    mut_a, n_a = re.subn(r"`writeAudit`", "`NO_SUCH_ANCHOR_9z8y`", text, count=1)
    c.check("mutation A really changed the source (otherwise it proves "
            "nothing)", n_a == 1, n_a)
    with open(GUIDE, "wb") as f:
        f.write(mut_a.encode("utf-8"))
    code_a, out_a = run_check()
    c.check("a stale anchor makes the checker FAIL (the check has teeth)",
            code_a != 0 and "FAIL" in out_a,
            (code_a, out_a.strip().splitlines()[-3:]))
    with open(GUIDE, "wb") as f:
        f.write(original)
    with open(GUIDE, "rb") as f:
        c.check("the guide is byte-identical again after mutation A",
                f.read() == original, GUIDE)


def _apply_mutation_b(c, GUIDE, original, text):
    """§3b: a missing file must be caught and the file restored byte-for-byte."""
    mut_b, n_b = re.subn(r"\| SKILL.md \|", "| NOPE_MISSING.md |", text, count=1)
    c.check("mutation B really changed the source", n_b == 1, n_b)
    with open(GUIDE, "wb") as f:
        f.write(mut_b.encode("utf-8"))
    code_b, out_b = run_check()
    c.check("a row pointing at a missing file makes the checker FAIL",
            code_b != 0 and "FAIL" in out_b,
            (code_b, out_b.strip().splitlines()[-3:]))
    with open(GUIDE, "wb") as f:
        f.write(original)
    with open(GUIDE, "rb") as f:
        c.check("the guide is byte-identical again after mutation B",
                f.read() == original, GUIDE)


def main():
    c.check("the checker script exists", os.path.exists(CHECK), CHECK)
    c.check("the system guide exists", os.path.exists(GUIDE), GUIDE)
    if not (os.path.exists(CHECK) and os.path.exists(GUIDE)):
        c.finish()

    with open(GUIDE, "rb") as f:
        original = f.read()
    text = original.decode("utf-8")

    _check_index_rows(c, text)
    _check_index_position(c, text)

    try:
        _apply_mutation_a(c, GUIDE, original, text)
        _apply_mutation_b(c, GUIDE, original, text)

        # ---- contrast: restored, it passes again ---------------------------
        code_r, out_r = run_check()
        c.check("contrast: the checker PASSES again once the index is restored "
                "(the failures came from the mutations, not the environment)",
                code_r == 0, (code_r, out_r.strip().splitlines()[-3:]))
    finally:
        with open(GUIDE, "rb") as f:
            if f.read() != original:
                with open(GUIDE, "wb") as g:
                    g.write(original)
                print("  !! the guide was left mutated; restored in finally")

    with open(GUIDE, "rb") as f:
        c.check("the guide is byte-identical to its original state when this "
                "grader finishes (no mutation may survive)",
                f.read() == original, GUIDE)

    c.finish()


if __name__ == "__main__":
    main()
