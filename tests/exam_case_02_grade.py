# -*- coding: utf-8 -*-
"""
Exam case 02 — grader for the four conflict resolutions.

The probe (`exam_case_02_conflict_paths.py`) prints what happens. This file is
the recorded answer, and it can fail.

Answer as filed on the exam entry:

    1. Adopt Mine   PUT baseRev=R1 + force        200   rev moves   A wins, B's edit is gone
    2. Keep Server  no write                       -    rev holds   B's version stays
    3. Merge        PUT baseRev=R2 (fresh)        200   rev moves   both edits survive
    4. Cancel       no write                       -    rev holds   identical to (2)

and the point of the case:

    * the revision token is sha256(JSON.stringify(items)).slice(0,16) — a digest,
      not a version counter. Writing identical content leaves it unchanged, so
      "resolving" a conflict can legitimately leave the rev exactly where it was.
    * two of the four resolutions issue no write at all, and those two are
      indistinguishable server-side: both leave the same rev and the same bytes.
      The difference between "take the server's" and "cancel" is a UI decision,
      not a server one.

Absolute rev values are deliberately not asserted: the scenario runs on a
throwaway temp list (created/deleted via the API, never the real `exam` list — see
exam_case_02_conflict_paths.run_paths), so the digest covers only the scenario
items and the real board is left byte-identical. What is asserted is the
*relationship* between content and rev, which is the property under test.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from exam_case_02_conflict_paths import PREFIX, run_paths   # noqa: E402
from grade_lib import get_list, delete_temp_list            # noqa: E402

failures = []
checks = [0]


def check(label, cond, detail=""):
    checks[0] += 1
    if not cond:
        failures.append(label)
        print("  FAIL %s   %s" % (label, detail))
    else:
        print("  ok   %s" % label)
    return bool(cond)


# The recorded answer: scenario items left on disk per resolution.
EXPECTED = {
    "take_mine": {
        "http": 200, "rev_moves": True,
        "items": {
            "A Added Task": ("Medium", ""),
            "Common Task": ("Medium", "Comment written by A"),
            "Other Task": ("Medium", ""),
        },
    },
    "take_server": {
        "http": None, "rev_moves": False,
        "items": {
            "B Added Task": ("Medium", ""),
            "Common Task": ("High", "Comment written by B"),
            "Other Task": ("Medium", ""),
        },
    },
    "merge": {
        "http": 200, "rev_moves": True,
        "items": {
            "A Added Task": ("Medium", ""),
            "B Added Task": ("Medium", ""),
            "Common Task": ("High", "Comment written by A"),
            "Other Task": ("Medium", ""),
        },
    },
    "cancel": {
        "http": None, "rev_moves": False,
        "items": {
            "B Added Task": ("Medium", ""),
            "Common Task": ("High", "Comment written by B"),
            "Other Task": ("Medium", ""),
        },
    },
}

LABEL = {"take_mine": "1. Adopt Mine", "take_server": "2. Keep Server",
         "merge": "3. Merge", "cancel": "4. Cancel"}


def as_map(content):
    return {cid[len(PREFIX):]: (prio, comment) for cid, prio, comment in content}


def _check_409(meta):
    """The 409 both resolutions start from: it must carry everything to retry."""
    body = meta["body409"] or {}
    diff = body.get("diff") or {}
    counts = diff.get("counts") or {}
    check("the loser's save is refused with 409", meta["http409"] == 409, meta["http409"])
    check("code is REV_CONFLICT", body.get("code") == "REV_CONFLICT", body.get("code"))
    check("409 returns the server's rev so the client can retry",
          body.get("serverRev") == meta["r2"], (body.get("serverRev"), meta["r2"]))
    check("409 carries the server's items", isinstance(body.get("items"), list),
          type(body.get("items")).__name__)
    check("diff reports added / removed / changed",
          all(counts.get(k, 0) >= 1 for k in ("added", "removed", "changed")), counts)
    check("diff reports the changed fields", counts.get("fields", 0) >= 1, counts)


def _check_resolutions(paths):
    """Each resolution, on disk and in the rev."""
    for key, want in EXPECTED.items():
        p = paths[key]
        got = as_map(p["content"])
        check("%s: on-disk content matches the recorded answer" % LABEL[key],
              got == want["items"], {"expected": want["items"], "observed": got})
        moved = p["rev_before"] != p["rev_after"]
        check("%s: rev %s" % (LABEL[key], "moves" if want["rev_moves"] else "holds"),
              moved == want["rev_moves"], (p["rev_before"], p["rev_after"]))
        if want["http"] is not None:
            check("%s: HTTP %s" % (LABEL[key], want["http"]),
                  p["http"] == want["http"], p["http"])
        check("%s: rev == sha256(items)" % LABEL[key], p["rev_is_digest"], p["rev_after"])


def _check_digest_property(result, paths):
    """The two things this case exists to show."""
    check("Keep Server and Cancel leave the same rev (both write nothing)",
          paths["take_server"]["rev_after"] == paths["cancel"]["rev_after"],
          (paths["take_server"]["rev_after"], paths["cancel"]["rev_after"]))
    check("Keep Server and Cancel leave the same bytes",
          paths["take_server"]["content"] == paths["cancel"]["content"], None)
    check("rev is a digest, not a counter: identical content -> identical rev",
          result["rev_is_a_digest"]["unchanged"] is True, result["rev_is_a_digest"])


def _check_merge_outcomes(paths):
    """The three write outcomes are genuinely different."""
    sigs = {k: tuple(sorted(as_map(paths[k]["content"]).items())) for k in EXPECTED}
    check("Adopt Mine / Merge / Server produce three different results",
          len(set(sigs.values())) == 3,
          {k: len(v) for k, v in sigs.items()})
    check("Merge keeps both clients' new items",
          "A Added Task" in as_map(paths["merge"]["content"])
          and "B Added Task" in as_map(paths["merge"]["content"]),
          sorted(as_map(paths["merge"]["content"])))
    check("Merge keeps B's priority and A's comment (a real merge, not one side)",
          as_map(paths["merge"]["content"]).get("Common Task") == ("High", "Comment written by A"),
          as_map(paths["merge"]["content"]).get("Common Task"))
    check("Adopt Mine discards B's edit",
          as_map(paths["take_mine"]["content"]).get("Common Task") == ("Medium", "Comment written by A"),
          as_map(paths["take_mine"]["content"]).get("Common Task"))


def _check_no_collateral(meta):
    """The scenario ran on a throwaway temp list, so the real exam list is untouched."""
    final_ids = [i["itemId"] for i in get_list(meta["list_id"])["items"]]
    check("scenario temp list restored to its pre-run id set",
          final_ids == meta["base_ids"],
          {"before": meta["base_ids"], "after": final_ids})
    check("no scenario item left behind",
          not [i for i in final_ids if str(i).startswith(PREFIX)],
          [i for i in final_ids if str(i).startswith(PREFIX)])


def main():
    result, meta = run_paths(cleanup=False)
    paths = result["paths"]

    try:
        print("Exam case 02 — grader")
        print()

        # ---------- the 409 both resolutions start from ----------
        _check_409(meta)

        # ---------- each resolution, on disk and in the rev ----------
        _check_resolutions(paths)

        # ---------- the two things this case exists to show ----------
        _check_digest_property(result, paths)

        # ---------- the three write outcomes are genuinely different ----------
        _check_merge_outcomes(paths)

        # ---------- no collateral damage ----------
        _check_no_collateral(meta)

        print()
        if failures:
            print("RESULT exam-case-02: FAIL (%d of %d)" % (len(failures), checks[0]))
            for f in failures:
                print("   - " + f)
            return 1
        print("RESULT exam-case-02: PASS (%d checks) — recorded answer reproduces exactly."
              % checks[0])
        print("ANSWER_JSON " + json.dumps(
            {k: {"http": v["http"], "rev_moves": v["rev_before"] != v["rev_after"],
                 "items": as_map(v["content"])} for k, v in paths.items()},
            ensure_ascii=False))
        return 0
    finally:
        # Always tear down the throwaway temp list, pass or fail.
        try:
            delete_temp_list(meta["list_id"])
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
