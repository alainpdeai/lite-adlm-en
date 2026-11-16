# -*- coding: utf-8 -*-
"""
Exam case 01 — the five-state transition matrix.

This is the *executable answer* to the exam entry "Five-state Machine Flow Matrix" in the
exam list. It is deliberately not a pass/fail unit test: it is a probe that
produces the ground truth, so the recorded answer can be re-derived at any time
instead of being trusted.

Why this case is worth having:
  `statusFlow` in categories.json *declares* which transitions are legal. The
  server *implements* the check in sanitizeStatus(). A declaration and an
  implementation are two different things, and where they disagree you have a
  bug — or at least a documented divergence nobody can see without running this.

Method:
  For every (from, to) pair over the five states, create a temp task already in
  `from` (creating at an arbitrary state is allowed: when an item is new the
  server has no previous status for it, so prev == next and the flow check is
  skipped by construction), then PUT the same item with `to`. The second write
  is where the flow table is consulted.

  Self-transitions (from == to) are the interesting part: the check only runs
  `if (next !== prev)`, so they never reach the table at all.

Where it runs (2026-10-31): against a PRIVATE instance started by this module —
a copy of data/ on a free port — instead of the live board. The probe empties
and refills the list 25 times, and every one of those writes bumped the real
exam.json's updatedAt even though items and rev were restored afterwards; the
copy makes that residue impossible. The list the probe works on is still a copy
of the real `exam` list, so nothing about the case changes: same content, same
server code, same 25 answers. Set LITETASK_EXAM01_BASE=http://host:port to aim
it at a server of your own (that is the only way to probe the live board now).
"""
import json
import os
import shutil
import sys
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import ROOT, copy_data_dir, run_instance, stop_instance, temp_dir  # noqa: E402

BASE = os.environ.get("LITETASK_EXAM01_BASE") or "http://localhost:3000"
LIST = "exam"
STATES = ["open", "in-progress", "blocked", "verified", "done"]

# Set when this module started the instance it is talking to.
_OWNED = None


def ensure_base():
    """Start a throwaway instance on a copy of data/ — unless one was handed to us."""
    global BASE, _OWNED
    if os.environ.get("LITETASK_EXAM01_BASE") or _OWNED:
        return BASE
    tmp = temp_dir(prefix="lt_exam01_")
    data_dir = copy_data_dir(tmp)
    inst = run_instance(data_dir, os.path.join(tmp, "backup"),
                        {"LITETASK_AUTO_ARCHIVE": "0"},
                        wait_after_ready=1.5, timeout=60, keep=True)
    if not inst["ready"]:
        stop_instance(inst["proc"])
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError("exam-01 probe could not start its private instance: "
                           + inst["output"][-300:])
    BASE = "http://127.0.0.1:%d" % inst["port"]
    _OWNED = (inst["proc"], tmp)
    return BASE


def teardown():
    global _OWNED
    if not _OWNED:
        return
    proc, tmp = _OWNED
    _OWNED = None
    stop_instance(proc)
    shutil.rmtree(tmp, ignore_errors=True)


def api(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "null")


def get_items():
    _, body = api("GET", "/api/lists")
    return next(l for l in body if l["listId"] == LIST)["items"]


def write(item, force=True):
    payload = {"type": "UPDATE_ITEMS", "items": [item]}
    if force:
        payload["force"] = True
        payload["confirm"] = True
    return api("PUT", "/api/lists/" + LIST, payload)


def clear():
    """Empty the list — items: [], an empty ITEM LIST.

    Not write([]): that wraps the argument and sends items: [[]], one element
    that is an empty array. Before the server validated item shapes it stored
    that junk as a pseudo-item, which happened to look like "emptied"; with
    schema validation in place it is correctly refused as an item with no
    itemId/title, the list keeps its previous contents, and every later probe
    starts from a stale state. Clearing means an empty list, so send one.
    """
    return api("PUT", "/api/lists/" + LIST,
               {"type": "UPDATE_ITEMS", "items": [], "force": True,
                # Hard gate: dropping the probe item needs an affirmative confirm.
                "confirm": True})


def probe(from_state, to_state):
    """Return (accepted, detail): can an item go from_state -> to_state?"""
    # Empty the list first. Otherwise the first PUT is not a create but a
    # transition from whatever the previous probe left behind, and the starting
    # state is no longer under our control.
    clear()
    base = {
        "itemId": "exam_probe", "title": "exam-probe", "isDone": False,
        "status": from_state, "statusHistory": [], "blockedReason": "",
        "dueDate": "2026-10-28", "priority": "Medium", "assignedTo": "admin",
        "createdBy": "admin", "createdByAgent": "", "createdById": "",
        "createdAt": "2026-10-28 00:00", "closedBy": None, "closedById": None,
        "closedAt": None, "localDirectory": "", "localDirectories": [],
        "comment": "", "subTasks": []
    }
    st1, b1 = write(base)
    if st1 != 200:
        return None, "setup failed %s %s" % (st1, b1)

    attempt = dict(base, status=to_state)
    st2, b2 = write(attempt, force=True)
    if st2 == 400 and isinstance(b2, dict) and b2.get("code") == "INVALID_TRANSITION":
        return False, b2.get("error", "")
    if st2 == 200:
        return True, ""
    return None, "unexpected %s %s" % (st2, b2)


def declared_flow():
    _, cats = api("GET", "/api/categories")
    return cats.get("statusFlow", {})


def _probe_all():
    """Probe every (from, to) transition; return the observed matrix."""
    observed = {}
    for frm in STATES:
        row = {}
        for to in STATES:
            ok, detail = probe(frm, to)
            row[to] = ok
            if ok is None:
                print("  !! %s -> %s : %s" % (frm, to, detail))
        observed[frm] = row
    return observed


def _print_matrix(observed):
    """Print the what-the-server-actually-does matrix."""
    hdr = "%-13s" % "from \\ to" + "".join("%-14s" % s for s in STATES)
    print(hdr)
    print("-" * len(hdr))
    for frm in STATES:
        cells = []
        for to in STATES:
            v = observed[frm][to]
            cells.append("%-14s" % ("ACCEPT" if v else ("reject" if v is False else "??")))
        print("%-13s" % frm + "".join(cells))


def _print_divergence(observed, flow):
    """Compare observed behaviour against the declared statusFlow; return it."""
    print()
    print("Declared statusFlow vs observed behaviour:")
    diverge = []
    for frm in STATES:
        allowed = flow.get(frm, [])
        for to in STATES:
            declared_ok = to in allowed
            actual_ok = observed[frm][to]
            if actual_ok is None:
                continue
            if declared_ok != actual_ok:
                diverge.append((frm, to, declared_ok, actual_ok))
    if diverge:
        for frm, to, d, a in diverge:
            print("  DIVERGE %s -> %s : declared=%s observed=%s" % (
                frm, to, "legal" if d else "illegal",
                "accepted" if a else "rejected"))
    else:
        print("  none — implementation matches the declaration exactly")
    return diverge


def main():
    ensure_base()
    # Snapshot the whole list, not just the ids: the restore below must put back
    # exactly what was there. (An earlier version restored a hardcoded empty
    # list and silently deleted a real exam entry.)
    before_items = get_items()
    before_ids = [i["itemId"] for i in before_items]
    flow = declared_flow()

    print("Exam case 01 — five-state transition matrix")
    print("server: %s   list: %s   (%s)" % (
        BASE, LIST,
        "private instance on a copy of data/" if _OWNED else "external server"))
    print()

    observed = _probe_all()
    _print_matrix(observed)
    diverge = _print_divergence(observed, flow)

    n_ok = sum(1 for f in STATES for t in STATES if observed[f][t])
    print()
    print("observed: %d accepted / %d rejected of %d transitions" % (
        n_ok, 25 - n_ok, 25))
    print("declared legal: %d" % sum(len(v) for v in flow.values()))

    # -------- restore --------
    api("PUT", "/api/lists/" + LIST,
        {"type": "UPDATE_ITEMS", "items": before_items, "force": True,
         "confirm": True})
    after_ids = [i["itemId"] for i in get_items()]
    print()
    print("exam list restored: before=%s after=%s  %s" % (
        before_ids, after_ids,
        "OK" if before_ids == after_ids else "MISMATCH"))

    # machine-readable answer, for pasting into the exam entry
    print()
    print("ANSWER_JSON " + json.dumps(
        {f: {t: observed[f][t] for t in STATES} for f in STATES},
        ensure_ascii=False))
    print("DIVERGE_JSON " + json.dumps(diverge, ensure_ascii=False))
    teardown()


if __name__ == "__main__":
    sys.exit(main())
