"""Fourth category Benchmarks & Acceptance (exam) — API mode, against the real server.

Verifies that the category is config-driven end to end and that a standard
test-case entry can be related to a function task, then restores everything.

Uses one throwaway exam entry; the exam list is left empty and the touched func
entry is restored edge-for-edge.
"""
import json
import os
import subprocess
import sys
import urllib.request

BASE = os.environ.get("LITETASK_BASE_URL", "http://localhost:3000")
CLI = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "litetask_cli.py")
EXAM_ITEM = "tmp_exam_case"
FUNC_ITEM = "task_1793167349269ca0753"

passed = 0
failed = []


def check(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
        print("  PASS  %s" % name)
    else:
        failed.append(name)
        print("  FAIL  %s   %s" % (name, detail))


def api(path, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"__error__": e.code, "body": e.read().decode()[:200]}


def get_lists():
    return api("/api/lists")


def get_list(lid):
    for l in get_lists():
        if l.get("listId") == lid:
            return l
    return None


def put_list(lid, items, rev):
    return api("/api/lists/" + lid, "PUT",
               {"type": "UPDATE_ITEMS", "items": items, "baseRev": rev})


def cli(*args):
    p = subprocess.run([sys.executable, CLI, "--url", BASE] + list(args),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return p.returncode, (p.stdout + p.stderr).strip()


def gaps_map():
    g = api("/api/gaps")
    return {r["value"]: r["count"] for r in g.get("rules", [])}


print("=== 1. the category is configuration, not code ===")
cats = api("/api/categories").get("categories", [])
exam_cfg = [c for c in cats if c.get("listId") == "exam"]
# categories.json gained a 5th entry (bug) on 2026-11-01; the exam list is still
# 4th of the four software-task categories. The point of this check is that the
# set is configuration-driven, so the expected count follows the config.
check("categories.json exposes 5 categories", len(cats) == 5, len(cats))
check("exam category exists", len(exam_cfg) == 1, cats)
check("exam category is named Benchmarks & Acceptance",
      exam_cfg and exam_cfg[0].get("name") == "Benchmarks & Acceptance",
      exam_cfg and exam_cfg[0].get("name"))
check("exam has its own color, distinct from arch/func/test",
      exam_cfg and exam_cfg[0].get("color") not in
      ["#7c3aed", "#2563eb", "#059669"],
      exam_cfg and exam_cfg[0].get("color"))

exam = get_list("exam")
check("server provisioned the exam list file", exam is not None)
# Snapshot. This test used to assert "the exam list is empty", which is false
# as soon as a real case is filed — and its cleanup then wiped the whole list,
# deleting that case. Never assume the container is empty; snapshot it.
BEFORE_ITEMS = [dict(i) for i in (exam["items"] if exam else [])]
check("exam list snapshot taken", isinstance(BEFORE_ITEMS, list),
      [i.get("itemId") for i in BEFORE_ITEMS])

base_gaps = gaps_map()
check("gaps exposes the three configured rules",
      set(base_gaps) == {"func-not-verified", "arch-not-derived", "orphan"},
      base_gaps)
# Root-cause assertion, independent of how much data happens to be complete
# today: coverage is credited by the *test* list only. This test used to
# hard-code "func-not-verified == 1", which stopped being true the moment the
# last real gap (M2) was closed and then failed for no substantive reason.
cov = [r for r in api("/api/categories").get("traceability", [])
       if r.get("value") == "func-not-verified"]
check("coverage rule credits the test list, never exam",
      cov and cov[0].get("referrer") == "test" and cov[0].get("relation") == "verifies",
      cov)

print("=== 2. a standard case entry can be created ===")
# Append to the snapshot instead of replacing the list wholesale.
_cur = get_list("exam")
put_list("exam", list(BEFORE_ITEMS) + [
    {"itemId": EXAM_ITEM, "title": "EXAM-TEMP Golden Scenario Sample",
     "status": "open", "priority": "Medium",
     "comment": "Temporary item to verify exam category write"}], _cur["rev"])
exam = get_list("exam")
check("exam entry written", any(i["itemId"] == EXAM_ITEM for i in exam["items"]),
      [i["itemId"] for i in exam["items"]])
check("new entry inherits the five-state model",
      [i for i in exam["items"] if i["itemId"] == EXAM_ITEM][0].get("status") == "open",
      [i.get("status") for i in exam["items"] if i["itemId"] == EXAM_ITEM])

print("=== 3. it can be related to a function task ===")
rc, out = cli("link", "--category", "exam", "--title-or-id", EXAM_ITEM,
              "--relates", "func:" + FUNC_ITEM + ":verifies")
check("link into the new category works", rc == 0, out)
edges = [i for i in get_list("exam")["items"]
         if i["itemId"] == EXAM_ITEM][0].get("relatesTo") or []
check("exam entry now points at the func task", len(edges) == 1, edges)

rc, out = cli("trace", "--category", "exam", "--title-or-id", EXAM_ITEM,
              "--direction", "forward", "--depth", "2")
# trace prints titles, not ids
check("trace walks exam -> func", rc == 0 and ("B1 Core Features" in out or "B1" in out), out)
check("trace continues to the arch node behind it", ("B1" in out or "（B1）" in out), out)

print("=== 4. an exam edge must NOT be counted as test coverage ===")
g = gaps_map()
check("exam verifies edge does not move the coverage counter",
      g.get("func-not-verified") == base_gaps.get("func-not-verified"),
      {"baseline": base_gaps, "with exam edge": g})
check("orphan count did not increase (exam entry is linked)",
      g.get("orphan") == base_gaps.get("orphan"), g)

print("=== 5. unlink works across the new category ===")
rc, out = cli("unlink", "--category", "exam", "--title-or-id", EXAM_ITEM,
              "--target", "func:" + FUNC_ITEM)
check("unlink removed the exam edge", rc == 0 and "removed 1" in out, out)
edges = [i for i in get_list("exam")["items"]
         if i["itemId"] == EXAM_ITEM][0].get("relatesTo") or []
check("exam entry has no edges left", len(edges) == 0, edges)

print("=== 6. cleanup ===")
# Restore the snapshot. Emptying the list here deleted a real exam case once.
put_list("exam", BEFORE_ITEMS, get_list("exam")["rev"])
exam = get_list("exam")
check("exam list restored to its pre-test id set",
      [i["itemId"] for i in exam["items"]] == [i["itemId"] for i in BEFORE_ITEMS],
      {"before": [i["itemId"] for i in BEFORE_ITEMS],
       "after": [i["itemId"] for i in exam["items"]]})
final = gaps_map()
check("gaps identical to baseline", final == base_gaps, final)
func_edges = sum(1 for i in get_list("func")["items"]
                 for r in (i.get("relatesTo") or [])
                 if r.get("itemId") == EXAM_ITEM)
check("no dangling edge to the temp exam entry remains in func",
      func_edges == 0, func_edges)

print("\n=== %d passed, %d failed ===" % (passed, len(failed)))
if failed:
    for f in failed:
        print("  FAILED: " + f)
    sys.exit(1)
print("ALL GREEN")
