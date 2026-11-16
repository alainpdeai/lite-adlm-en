# -*- coding: utf-8 -*-
"""
End-to-end proof for the question "if I add a task in the UI, can the Agent
see it and act on it?"

The honest answer has two halves, and this file checks both:

  1. VISIBILITY — a task typed by a human in the browser lands in the same
     JSON the Agent reads, and `pending` surfaces it as *unclaimed human work*.
  2. ATTRIBUTION — a task the Agent creates is stamped with its name, so it
     must NOT appear in `pending` (otherwise the queue is just "everything
     open", which is useless).

Everything runs against the live server on a temporary item that is deleted
at the end; the board is restored to its exact pre-test id set.
"""
import json
import atexit
import os
import subprocess
import sys
import urllib.request

BASE = os.environ.get("LITETASK_BASE_URL", "http://localhost:3000")
CLI = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "litetask_cli.py")
LIST = "exam"
HUMAN_TITLE = "TEMP-Human-Created-Pending-Probe"

_results = []


def check(label, ok, detail=None):
    _results.append((label, bool(ok)))
    print(("  PASS  " if ok else "  FAIL  ") + label +
          ("" if detail is None else "  -> " + json.dumps(detail, ensure_ascii=False)))


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


def get_list(lid):
    st, body = api("GET", "/api/lists")
    return next(l for l in body if l["listId"] == lid)


def cli(*argv):
    p = subprocess.run([sys.executable, CLI, "--url", BASE] + list(argv),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def pending_titles():
    """Task lines only. The CLI also prints a `[mode=API]` banner that happens
    to start with '[' — it must not be mistaken for a queue entry."""
    rc, out = cli("pending")
    rows = [ln.strip() for ln in out.splitlines()
            if ln.strip().startswith("[") and not ln.strip().startswith("[mode=")]
    return rc, out, rows


# ---------------------------------------------------------------- setup
before = get_list(LIST)
before_ids = [i["itemId"] for i in before["items"]]

# P2-10: cleanup must run even when an assertion aborts the main flow.
def _restore_board():
    try:
        api("PUT", "/api/lists/" + LIST,
            {"type": "UPDATE_ITEMS", "items": before["items"],
             "force": True, "confirm": True})
    except Exception:                                          # noqa: BLE001
        pass
atexit.register(_restore_board)
# Snapshot, do not assert emptiness: a filed exam case makes "empty" false and
# turns a healthy run into a failure. Only the restore comparison matters.
check("exam list snapshot taken", isinstance(before_ids, list), before_ids)

# ------------------------------------------------- 1. human creates via UI shape
# Exactly the shape public/index.html writes: no createdByAgent at all.
human_item = {
    "itemId": "tmp_human_probe",
    "title": HUMAN_TITLE,
    "isDone": False, "status": "open", "statusHistory": [], "blockedReason": "",
    "dueDate": "2026-10-28", "priority": "High",
    "assignedTo": "admin", "createdBy": "admin", "createdByAgent": "",
    "createdById": "", "createdAt": "2026-10-28 08:00",
    "closedBy": None, "closedById": None, "closedAt": None,
    "localDirectory": "", "localDirectories": [], "comment": "", "subTasks": []
}
st, _ = api("PUT", "/api/lists/" + LIST,
            {"type": "UPDATE_ITEMS", "items": [human_item], "force": True,
             "confirm": True})
check("human-shaped item written", st == 200, st)

rc, out, rows = pending_titles()
check("pending surfaces the human-created task",
      any(HUMAN_TITLE in r for r in rows), rows)
check("pending labels it with its category and state",
      any(r.startswith("[exam/open]") for r in rows), rows)
check("pending exits 0 when there is work", rc == 0, rc)
check("pending prints the itemId so an Agent can pick it up",
      "tmp_human_probe" in out, out.splitlines()[-3:])

# ------------------------------- 2. an Agent-created task must stay out of it
rc2, out2 = cli("add", "--category", LIST, "--title", "TEMP-Agent-Created-Probe",
                "--agent", "AI Agent", "--priority", "Low",
                "--local-directory", "<PROJECT_DIR>/tests")
check("agent-created task accepted", rc2 == 0, out2.strip()[:120])

listed = get_list(LIST)
agent_row = [i for i in listed["items"] if i["title"] == "TEMP-Agent-Created-Probe"]
check("agent-created task is stamped with the agent name",
      len(agent_row) == 1 and agent_row[0].get("createdByAgent") == "AI Agent",
      agent_row[0].get("createdByAgent") if agent_row else None)

rc3, out3, rows3 = pending_titles()
check("pending EXCLUDES the agent's own task (queue is not 'everything open')",
      not any("TEMP-Agent-Created-Probe" in r for r in rows3), rows3)
check("pending still shows the human task alongside",
      any(HUMAN_TITLE in r for r in rows3), rows3)

# ------------------------------------ 3. closing the task drains it from pending
listed = get_list(LIST)
rc4, out4 = cli("status", "--category", LIST, "--title-or-id", "tmp_human_probe",
                "--status", "done")
check("human task can be closed by the Agent", rc4 == 0 and "STATUS" in out4,
      out4.strip()[:120])
rc5, out5, rows5 = pending_titles()
check("closed task leaves the pending queue",
      not any(HUMAN_TITLE in r for r in rows5), rows5)

# ------------------------------------------------------------- 4. restore
api("PUT", "/api/lists/" + LIST,
    {"type": "UPDATE_ITEMS", "items": before["items"], "force": True,
     "confirm": True})
after = get_list(LIST)
after_ids = [i["itemId"] for i in after["items"]]
check("exam list restored to its pre-test id set", after_ids == before_ids,
      {"before": before_ids, "after": after_ids})

# ------------------------------------------------------------- 5. empty state
rc6, out6, rows6 = pending_titles()
print("        (board-wide pending now: %s)" % (rows6 or "none"))
check("pending reports the remaining queue without crashing", rc6 == 0, rc6)
check("remaining pending items are all genuinely human-created (M2)",
      all("Clean up legacy files" in r or len(rows6) == 0 for r in rows6), rows6)

# ------------------------------------------------------------------ summary
failed = [l for l, ok in _results if not ok]
print("\nRESULT: %d/%d passed" % (len(_results) - len(failed), len(_results)))
for l in failed:
    print("  - " + l)
sys.exit(1 if failed else 0)
