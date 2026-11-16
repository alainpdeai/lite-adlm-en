# -*- coding: utf-8 -*-
"""
Exam case 03 — grader: archiving moves storage, it does not withdraw evidence.

The probe (`exam_case_03_archived_evidence.py`) prints what happens. This file is
the recorded answer, and it can fail.

Answer as filed on the exam entry — one question, eight things that could have
survived an archive or not:

    Aspect                      Before Archive      After Archive
    Board items                 3 items             1 item (open one)
    data/archive/<list>.json    -                   2 items (inc verifier)
    GET /api/archive/<list>     200 (empty)         200 (inc 2 items)
    Verifier node in graph      archived=false      archived=true
    Carried verifies edge       ['verifies']        ['verifies'] (persists)
    Reverse trace to verifier   Yes                 Yes
    Owner counted as gap?       No                  No
    Archived orphan gap?        Yes                 No (excluded from gaps)

and the reason the case exists:

    * Archiving moves storage, not evidence. A closed verifier moved to data/archive/ after
      still retains its verifies edge, and feature item remains covered.
    * Pre-fix buildLinkGraph() only read data/shared_lists; archiving erased items
      and relations from the graph: func-not-verified jumped from 0 to 18 as evidence was erased.
      and relations from the graph: func-not-verified jumped from 0 to 18 as evidence was erased.
    * Archived items never count as gaps themselves: otherwise archiving completed work would manufacture false gaps.

The last block is a negative control run *inside* the probe: on the same copy,
`data/archive/exam.json` is deleted, which reproduces the pre-fix view (the
graph cannot see archived work). There the verifier node disappears and the
owner does become a gap. Without that block the assertions above could pass
vacuously — e.g. if the coverage rule stopped working altogether.

Absolute counts are asserted only where they are a property of the scenario
(three scenario items); counts that depend on how many exam cases are filed are
asserted as membership or as "never increases", per §26 of
references/system-guide.md.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from exam_case_03_archived_evidence import (LONE, OWNER, PREFIX,  # noqa: E402
                                            VERIFIER, run_scenario)
from grade_lib import get_items, server_archive_dir              # noqa: E402

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


# The recorded answer. `moved` counts the whole exam list (filed cases included),
# so it is asserted against the archive file's contents rather than a literal.
EXPECTED = {
    "before": {
        "scenario_on_board": 3,
        "owner_archived": False,
        "verifier_archived": False,
        "verifier_edges": ["verifies"],
        "trace_reaches_verifier": True,
        "owner_is_gap": False,
        "lone_is_orphan": True,
        "gap_count_scen": 2,            # verifier + lone are themselves uncovered
        "orphan_count_scen": 1,         # lone
    },
    "after": {
        "scenario_on_board": 1,          # only the never-closed owner stays
        "scenario_in_archive_file": [LONE, VERIFIER],
        "owner_still_on_board": True,
        "verifier_off_board": True,
        "verifier_node_archived": True,
        # verifier_list_id is now the throwaway temp list's id; the check compares
        # against r["list_id"] at runtime (see the "keeps the list" assertion).
        "verifier_list_id": None,
        "owner_archived": False,
        "verifier_edges": ["verifies"],
        "trace_reaches_verifier": True,
        "owner_is_gap": False,
        "lone_is_orphan": False,
        "gap_count_scen": 0,
        "orphan_count_scen": 0,
    },
    "without_archive": {                # the pre-fix view, reproduced on purpose
        "verifier_node_gone": True,
        "owner_becomes_gap": True,
        "owner_becomes_orphan": True,
        "gap_count_scen": 1,            # the owner, and only the owner
        "orphan_count_scen": 1,
    },
}


def scen(ids):
    return sorted(i for i in ids if str(i).startswith(PREFIX))


def _check_instance_and_archive(r):
    check("the throwaway instance came up", r["instance_ready"] is True, r["instance_ready"])
    check("archiving the copy's exam list answered 200", r["archive"]["http"] == 200,
          r["archive"])
    check("every moved item landed in the archive file",
          r["archive"]["moved"] == len(r["archive_file_ids"]),
          (r["archive"]["moved"], len(r["archive_file_ids"])))


def _check_before(b):
    print()
    print("== before archiving ==")
    check("all three scenario items are on the board",
          len(scen(b["board_ids"])) == EXPECTED["before"]["scenario_on_board"],
          scen(b["board_ids"]))
    check("the owner is an active node", b["owner_node"]
          and b["owner_node"].get("archived") is EXPECTED["before"]["owner_archived"],
          b["owner_node"])
    check("the verifier is an active node", b["verifier_node"]
          and b["verifier_node"].get("archived") is EXPECTED["before"]["verifier_archived"],
          b["verifier_node"])
    check("the verifier carries its verifies edge",
          b["verifier_edges"] == EXPECTED["before"]["verifier_edges"], b["verifier_edges"])
    check("the backward trace reaches the verifier",
          (VERIFIER in b["trace_ids"]) is EXPECTED["before"]["trace_reaches_verifier"],
          b["trace_ids"])
    check("the owner is covered, not a gap",
          (OWNER in b["gap_ids"]) is EXPECTED["before"]["owner_is_gap"], b["gap_ids"])
    check("the unrelated closed item is an orphan while it is active",
          (LONE in b["orphan_ids"]) is EXPECTED["before"]["lone_is_orphan"], b["orphan_ids"])
    check("scenario-scoped gap count before archiving",
          b["gap_count_scen"] == EXPECTED["before"]["gap_count_scen"],
          (b["gap_count_scen"], b["gap_ids_scen"]))
    check("scenario-scoped orphan count before archiving",
          b["orphan_count_scen"] == EXPECTED["before"]["orphan_count_scen"],
          (b["orphan_count_scen"], b["orphan_ids_scen"]))


def _check_after(a, r):
    print()
    print("== after archiving ==")
    check("only the never-closed owner is left on the board",
          len(scen(a["board_ids"])) == EXPECTED["after"]["scenario_on_board"],
          scen(a["board_ids"]))
    check("the owner stayed on the board",
          (OWNER in a["board_ids"]) is EXPECTED["after"]["owner_still_on_board"],
          a["board_ids"])
    check("the verifier left the board",
          (VERIFIER not in a["board_ids"]) is EXPECTED["after"]["verifier_off_board"],
          a["board_ids"])
    check("both closed scenario items are in data/archive/exam.json",
          scen(r["archive_file_ids"]) == sorted(EXPECTED["after"]["scenario_in_archive_file"]),
          {"observed": scen(r["archive_file_ids"]),
           "expected": sorted(EXPECTED["after"]["scenario_in_archive_file"])})
    check("GET /api/archive/exam reads them back",
          a["archive_api_status"] == 200
          and set([VERIFIER, LONE]).issubset(set(a["archive_api_ids"])),
          (a["archive_api_status"], a["archive_api_ids"]))
    check("the archived verifier is still a node", a["verifier_node"] is not None,
          a["verifier_node"])
    check("and it is flagged archived", a["verifier_node"]
          and a["verifier_node"].get("archived") is EXPECTED["after"]["verifier_node_archived"],
          a["verifier_node"])
    check("it keeps the list it was archived from",
          a["verifier_node"]
          and a["verifier_node"].get("listId") == r["list_id"],
          a["verifier_node"])
    check("it keeps its title", a["verifier_node"]
          and a["verifier_node"].get("title") == "EXAM03 Sole Verifier (Gets archived)",
          (a["verifier_node"] or {}).get("title"))
    check("the owner is still flagged active", a["owner_node"]
          and a["owner_node"].get("archived") is EXPECTED["after"]["owner_archived"],
          a["owner_node"])
    check("its verifies edge survived the move",
          a["verifier_edges"] == EXPECTED["after"]["verifier_edges"], a["verifier_edges"])
    check("the backward trace still reaches the archived verifier",
          (VERIFIER in a["trace_ids"]) is EXPECTED["after"]["trace_reaches_verifier"],
          a["trace_ids"])


def _check_evidence_preserved(a, b):
    print()
    print("== the evidence still counts, and archiving makes no new gaps ==")
    check("the owner is STILL not a coverage gap",
          (OWNER in a["gap_ids"]) is EXPECTED["after"]["owner_is_gap"], a["gap_ids"])
    check("archiving never increases the gap count",
          a["gap_count"] <= b["gap_count"], (b["gap_count"], a["gap_count"]))
    check("scenario-scoped gap count drops to zero",
          a["gap_count_scen"] == EXPECTED["after"]["gap_count_scen"],
          (a["gap_count_scen"], a["gap_ids_scen"]))
    check("the archived item is not reported as an orphan",
          (LONE in a["orphan_ids"]) is EXPECTED["after"]["lone_is_orphan"], a["orphan_ids"])
    check("archiving never increases the orphan count",
          a["orphan_count"] <= b["orphan_count"], (b["orphan_count"], a["orphan_count"]))
    check("scenario-scoped orphan count drops to zero",
          a["orphan_count_scen"] == EXPECTED["after"]["orphan_count_scen"],
          (a["orphan_count_scen"], a["orphan_ids_scen"]))


def _check_negative_control(r):
    n = r["without_archive"]
    a = r["after"]
    print()
    print("== negative control: take the archive away (the pre-fix view) ==")
    check("the probe really had an archive file to delete",
          r["negative_control"]["archive_file_existed"] is True,
          r["negative_control"])
    check("without it, the verifier is no longer a node",
          (n["verifier_node"] is None) is EXPECTED["without_archive"]["verifier_node_gone"],
          n["verifier_node"])
    check("and the owner becomes a coverage gap — this is the bug, reproduced",
          (OWNER in n["gap_ids"]) is EXPECTED["without_archive"]["owner_becomes_gap"],
          n["gap_ids"])
    check("it becomes an orphan too (it lost its only relation)",
          (OWNER in n["orphan_ids"]) is EXPECTED["without_archive"]["owner_becomes_orphan"],
          n["orphan_ids"])
    check("the scenario-scoped gap count there is exactly one — the owner",
          n["gap_count_scen"] == EXPECTED["without_archive"]["gap_count_scen"]
          and n["gap_ids_scen"] == [OWNER],
          (n["gap_count_scen"], n["gap_ids_scen"]))
    check("and it is the only scenario orphan there",
          n["orphan_count_scen"] == EXPECTED["without_archive"]["orphan_count_scen"]
          and n["orphan_ids_scen"] == [OWNER],
          (n["orphan_count_scen"], n["orphan_ids_scen"]))
    check("so the assertions above are load-bearing: with/without differ",
          a["gap_count"] != n["gap_count"] or a["gap_ids"] != n["gap_ids"],
          {"after": a["gap_ids"], "without_archive": n["gap_ids"]})


def _check_no_collateral(r, baseline):
    print()
    print("== the working data is untouched ==")
    # The scenario ran on a throwaway temp list, so the *real* exam list is
    # untouched; we assert the temp list itself was restored (and is empty/deleted).
    final_ids = [i["itemId"] for i in get_items(r["list_id"])]
    check("scenario temp list restored to its pre-run id set",
          final_ids == r["base_ids"],
          {"before": r["base_ids"], "after": final_ids})
    check("no scenario item left behind",
          not scen(final_ids), scen(final_ids))
    # A human archiving a list from the UI is a legitimate state, so compare
    # against what was there before this exam case ran rather than asserting the
    # directory is empty.
    arch_dir = server_archive_dir()
    check("the working archive dir is unchanged by the exam case",
          os.listdir(arch_dir) == baseline,
          (baseline, os.listdir(arch_dir)))


def main():
    # Captured before anything runs, so the "no collateral damage" checks
    # compare against the real prior state instead of an assumed-empty one.
    arch_dir = server_archive_dir()
    baseline = sorted(os.listdir(arch_dir))
    r = run_scenario()
    b, a, n = r["before"], r["after"], r["without_archive"]

    print("Exam case 03 — grader")
    print()

    _check_instance_and_archive(r)
    _check_before(b)
    _check_after(a, r)
    _check_evidence_preserved(a, b)
    _check_negative_control(r)
    _check_no_collateral(r, baseline)

    print()
    if failures:
        print("RESULT exam-case-03: FAIL (%d of %d)" % (len(failures), checks[0]))
        for f in failures:
            print("   - " + f)
        return 1
    print("RESULT exam-case-03: PASS (%d checks) — recorded answer reproduces exactly."
          % checks[0])
    print("ANSWER_JSON " + json.dumps(
        {"before": {k: b.get(k) for k in
                    ("gap_count", "orphan_count", "verifier_edges",
                     "trace_ids", "board_ids")},
         "after": {k: a.get(k) for k in
                   ("gap_count", "orphan_count", "verifier_edges",
                    "trace_ids", "board_ids")},
         "without_archive": {k: n.get(k) for k in
                             ("gap_count", "orphan_count", "verifier_edges",
                              "trace_ids", "board_ids")}},
        ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
