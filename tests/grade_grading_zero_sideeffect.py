# -*- coding: utf-8 -*-
"""
Grader: grading must leave the production lists byte-identical, and an
idempotent write must not be recorded as an update.

The problem this file exists for (recorded 2026-10-29): a full grading run used
to leave `data/shared_lists/exam.json` and `test.json` modified — items
unchanged, `rev` unchanged, but `updatedAt` bumped — so every regression
produced a "data changed" commit in which the real business change was buried
under metadata noise.

Root cause: `UPDATE_ITEMS` bumped `updatedAt` unconditionally, so writing back
byte-identical items was recorded as an update. The fix (server side) is an
idempotent no-op write. Two properties are asserted here:

A. Idempotency, on a throwaway list: writing the same items again changes
   nothing — not `rev`, not `updatedAt`. Contrast: writing *different* items
   must still bump `updatedAt`, or "writes are simply disabled" would pass.

B. Zero side effects on production: after running every grader that talks to
   the live server, each production list keeps its `rev` (the recorded
   acceptance criterion: items unchanged) and the set of list ids is unchanged
   (no leaked temp list).

Why (B) is `rev` and not `updatedAt`: one of those graders,
grade_a1_archive_threshold.py, *genuinely* modifies the real `test` list
(pushes it over the archive threshold) and then restores it. That is a real
write, so `updatedAt` is supposed to move; what must not happen is the items
ending up different. Checking `updatedAt` there would fail for a legitimate
reason and drown the property we actually care about.
"""
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (ROOT, Checker, api, create_temp_list,  # noqa: E402
                       delete_temp_list, get_list, put_items, temp_item)

c = Checker("grading-zero-sideeffect")

# The graders that talk to the live server on :3000. They are the only ones that
# can touch production data; hermetic graders run private node instances and are
# irrelevant here.
PROBE_GRADERS = [
    "grade_a1_archive_threshold.py",   # the one that writes the real `test` list
    "grade_b3_concurrency_core.py",
    "grade_f1_status_flow.py",
    "grade_f2_multipath_and_backup.py",
    "grade_f3_trace_and_gaps.py",
]


def fingerprint():
    """{listId: {"rev":..., "updatedAt":...}} for every production list."""
    st, lists = api("GET", "/api/lists")
    if st != 200 or not isinstance(lists, list):
        return None, (st, lists)
    return ({l.get("listId"): {"rev": l.get("rev"), "updatedAt": l.get("updatedAt")}
             for l in lists}, None)


def stamp_of(lid):
    l = get_list(lid)
    return None if l is None else {"rev": l.get("rev"),
                                   "updatedAt": l.get("updatedAt")}


def run_grader(name):
    """Run one grader; return (passed, seconds, output). Whether its own
    assertions pass is run_grade_checks.py's business — here we only care
    whether running it disturbed production."""
    t0 = time.time()
    p = subprocess.run([sys.executable, os.path.join(HERE, name)],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    out = (p.stdout or "") + (p.stderr or "")
    m = re.search(r"RESULT .*?: (PASS|FAIL)", out)
    passed = (m.group(1) == "PASS") if m else (p.returncode == 0)
    return passed, time.time() - t0, out


# ============================================ A. idempotency, on a temp list
print("== an idempotent write is not an update (throwaway list) ==")
LID = create_temp_list("GRADE-TEMP idempotent")
try:
    items_a = [temp_item("idem-01", title="idempotency probe", status="open")]
    st, _ = put_items(LID, items_a, force=True)
    c.check("the first write of the probe items succeeded", st == 200, st)
    s1 = stamp_of(LID)

    time.sleep(0.05)   # so a bumped updatedAt cannot collide with the previous one
    st2, _ = put_items(LID, items_a, force=True)     # identical content again
    c.check("the identical re-write is accepted (200, not an error)", st2 == 200, st2)
    s2 = stamp_of(LID)

    c.check("writing byte-identical items did not change rev",
            s1 and s2 and s1["rev"] == s2["rev"], (s1, s2))
    c.check("writing byte-identical items did not bump updatedAt "
            "(the metadata-only churn that buried real changes)",
            s1 and s2 and s1["updatedAt"] == s2["updatedAt"], (s1, s2))

    # contrast: writes are not simply disabled. Different content must still be
    # recorded, otherwise "skip every write" would satisfy the checks above.
    items_b = items_a + [temp_item("idem-02", title="a real change",
                                   status="open")]
    st3, _ = put_items(LID, items_b, force=True)
    c.check("a genuinely different write still succeeds", st3 == 200, st3)
    s3 = stamp_of(LID)
    c.check("a genuinely different write still changes rev (contrast: writes "
            "are not disabled)",
            s1 and s3 and s1["rev"] != s3["rev"], (s1, s3))
    c.check("a genuinely different write still bumps updatedAt (contrast)",
            s1 and s3 and s1["updatedAt"] != s3["updatedAt"], (s1, s3))
finally:
    delete_temp_list(LID)
c.check("the throwaway list is gone again", get_list(LID) is None, LID)


# ============================================== B. production is left alone
print()
before, err = fingerprint()
c.check("the production server answers /api/lists", before is not None, err)
if before is None:
    c.finish()

c.check("the baseline fingerprint is not empty (a vacuous 'nothing changed' "
        "would otherwise pass)", len(before) >= 4, sorted(before)[:6])
c.check("every baseline rev is a non-empty string",
        all(isinstance(v["rev"], str) and v["rev"] for v in before.values()),
        {k: v["rev"] for k, v in list(before.items())[:4]})

# contrast, without writing anything: mutating a copy in memory must compare
# unequal, or the comparison could not detect a change at all.
mutated = {k: dict(v) for k, v in before.items()}
first = sorted(mutated)[0]
mutated[first]["updatedAt"] = "1999-01-01T00:00:00.000Z"
c.check("the comparison can detect an updatedAt change (contrast, in memory "
        "only)", mutated != before, first)

print()
print("== running the graders that write to the live server ==")
for name in PROBE_GRADERS:
    passed, secs, _out = run_grader(name)
    print("     ran %-34s %s (%.1fs)" % (name, "PASS" if passed else "FAIL", secs))

print()
after, err2 = fingerprint()
c.check("the production server still answers afterwards", after is not None, err2)
if after is None:
    c.finish()

c.check("the set of list ids is unchanged (no leaked temp list)",
        sorted(after) == sorted(before),
        (sorted(set(after) - set(before)), sorted(set(before) - set(after))))

rev_changed = sorted(k for k in set(before) & set(after)
                     if before[k]["rev"] != after[k]["rev"])
c.check("every production list kept its rev (items unchanged by grading)",
        not rev_changed, rev_changed[:5])

c.finish()
