# -*- coding: utf-8 -*-
"""
Exam case 01 — grader for the five-state transition matrix.

The probe (exam_case_01_status_flow.py) prints what the server does. This file
decides whether that matches the answer recorded on the exam entry. The two are
kept separate on purpose: the probe stays a probe (it never fails), the grader
is the thing that can fail — so "exam 01 is done" is a verifiable claim, not a
narrative one.

Expected answer, as recorded on the exam entry:
    22 accepted / 3 rejected.

The rejected three, and why:
    open     -> verified   must start work before it can be verified
    blocked  -> verified   same
    verified -> open       verified work does not go back to "not started"

Known divergence (documented, not a failure):
    statusFlow in categories.json declares no self-transitions, yet all five
    self-transitions are accepted, because sanitizeStatus() only consults the
    table inside `if (next !== prev)`. The grader asserts this divergence is
    *still there* — if someone later "fixes" either side, this exam must be
    re-derived rather than silently going stale.

Exit code 0 = observed behaviour matches the recorded answer.
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import exam_case_01_status_flow as probe  # noqa: E402

STATES = probe.STATES


def data_hashes():
    """Byte-level fingerprint of every file under data/ — the evidence that the
    grader left the real board alone (not just 'the ids came back')."""
    out = {}
    root = os.path.join(os.path.dirname(HERE), "data")
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            p = os.path.join(dirpath, fn)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = hashlib.sha256(f.read()).hexdigest()
    return out

# The recorded answer. 25 cells.
EXPECTED = {
    "open":        {"open": True,  "in-progress": True,  "blocked": True,
                    "verified": False, "done": True},
    "in-progress": {"open": True,  "in-progress": True,  "blocked": True,
                    "verified": True,  "done": True},
    "blocked":     {"open": True,  "in-progress": True,  "blocked": True,
                    "verified": False, "done": True},
    "verified":    {"open": False, "in-progress": True,  "blocked": True,
                    "verified": True,  "done": True},
    "done":        {"open": True,  "in-progress": True,  "blocked": True,
                    "verified": True,  "done": True},
}

REJECT_REASON_MUST_CONTAIN = "Allowed"   # server error text lists the allowed set

failures = []
checks = [0]


def check(cond, msg):
    checks[0] += 1
    if not cond:
        failures.append(msg)
    print(("  ok   " if cond else "  FAIL ") + msg)
    return cond


def _check_status_matrix(observed, details, flow):
    """The recorded answer: 25 cells, the rejected three, counts, divergence."""
    n_ok = 0
    for frm in STATES:
        for to in STATES:
            got = observed[frm][to]
            want = EXPECTED[frm][to]
            if got == want:
                n_ok += 1
            else:
                failures.append("cell %s -> %s : expected %s, observed %s (detail: %s)"
                                % (frm, to, want, got, details[(frm, to)]))
    check(n_ok == 25, "all 25 cells match the recorded answer (%d/25)" % n_ok)

    # -------- the rejected three: shape of the refusal --------
    for frm, to in [("open", "verified"), ("blocked", "verified"), ("verified", "open")]:
        d = details[(frm, to)]
        check(isinstance(d, str) and REJECT_REASON_MUST_CONTAIN in d,
              "%s -> %s rejected with a reason listing the allowed set: %s"
              % (frm, to, (d or "")[:70]))

    # -------- counts --------
    acc = sum(1 for f in STATES for t in STATES if observed[f][t])
    rej = 25 - acc
    check((acc, rej) == (22, 3), "counts: %d accepted / %d rejected (expected 22/3)" % (acc, rej))

    # -------- declared vs observed divergence (expected to persist) --------
    diverge = []
    for frm in STATES:
        allowed = flow.get(frm, [])
        for to in STATES:
            if observed[frm][to] is None:
                continue
            if (to in allowed) != observed[frm][to]:
                diverge.append((frm, to))
    check(diverge == [(s, s) for s in STATES],
          "divergence is exactly the 5 self-transitions: %s"
          % ", ".join("%s->%s" % d for d in diverge))
    check(sum(len(v) for v in flow.values()) == 17,
          "statusFlow still declares 17 legal transitions (got %d)"
          % sum(len(v) for v in flow.values()))


def _check_no_collateral(after_ids, before_ids, real_before):
    """The grader leaves the real board byte-identical."""
    check(after_ids == before_ids,
          "exam list restored: before=%s after=%s" % (before_ids, after_ids))
    real_after = data_hashes()
    changed = sorted(k for k in real_before
                     if real_before.get(k) != real_after.get(k))
    check(real_after == real_before,
          "the real data/ tree is byte-identical after the run (was the probe "
          "isolated?) — changed: %s" % (changed or "nothing"))


def main():
    # The probe runs on a private instance (a copy of data/ on a free port), so
    # "no collateral damage" can be asserted against the REAL files as well:
    # hash them here and compare at the end.
    real_before = data_hashes()

    probe.ensure_base()
    # Snapshot first. The probe empties the list while it works; the grader puts
    # back exactly what was there. Restoring "to empty" here would delete the
    # real exam entry.
    before = probe.get_items()
    before_ids = [i["itemId"] for i in before]

    observed, details = {}, {}
    try:
        for frm in STATES:
            observed[frm] = {}
            for to in STATES:
                ok, detail = probe.probe(frm, to)
                observed[frm][to] = ok
                details[(frm, to)] = detail
                if ok is None:
                    failures.append("probe error %s -> %s : %s" % (frm, to, detail))
        # read the declaration while the instance is still up
        flow = probe.declared_flow()
    finally:
        probe.api("PUT", "/api/lists/" + probe.LIST,
                  {"type": "UPDATE_ITEMS", "items": before, "force": True,
                   "confirm": True})
        after_ids = [i["itemId"] for i in probe.get_items()]
        probe.teardown()

    print("Exam case 01 — grader")
    print()

    _check_status_matrix(observed, details, flow)
    _check_no_collateral(after_ids, before_ids, real_before)

    print()
    if failures:
        print("RESULT: FAIL (%d problem(s))" % len(failures))
        for f in failures:
            print("  - " + f)
        return 1
    print("RESULT exam-case-01: PASS (%d checks) — recorded answer reproduces exactly."
          % checks[0])
    print("ANSWER_JSON " + json.dumps(observed, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
