"""CLI `unlink` (inverse of `link`) — API mode, against the real server.

Operates on a throwaway task so the three real lists are never mutated.
Every edge case is exercised, then the temp task is removed and the list is
verified byte-for-byte identical (item ids) to what it was before.
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
TMP = "tmp_unlink_test"
TARGET_A = "arch:task_arch_b1"
TARGET_B = "arch:task_17931398547122b65eb"

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
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def get_func():
    # the server only exposes the collection route; single-list GET does not exist
    for l in api("/api/lists"):
        if l.get("listId") == "func":
            return l
    raise SystemExit("list func not found")


def put_func(items, rev):
    return api("/api/lists/func", "PUT",
               {"type": "UPDATE_ITEMS", "items": items, "baseRev": rev})


def cli(*args):
    p = subprocess.run([sys.executable, CLI, "--url", BASE] + list(args),
                       capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def edges_of(item_id):
    for i in get_func()["items"]:
        if i["itemId"] == item_id:
            return i.get("relatesTo") or []
    return None


def as_keys(edges):
    return sorted("%s/%s[%s]" % (e.get("listId"), e.get("itemId"),
                                 e.get("relation")) for e in edges or [])


print("=== setup ===")
base = get_func()
base_ids = [i["itemId"] for i in base["items"]]
put_func([{"itemId": TMP, "title": "UNLINK-TEST temp", "status": "done",
           "priority": "Low", "relatesTo": []}] + base["items"], base["rev"])
check("temp task created", edges_of(TMP) is not None, TMP)

rc, out = cli("link", "--category", "func", "--title-or-id", TMP,
              "--relates", TARGET_A + ":related",
              "--relates", TARGET_B + ":related")
check("link attached 2 edges", rc == 0, out)
check("2 edges present", len(edges_of(TMP)) == 2, as_keys(edges_of(TMP)))

print("=== case A: no target, no relation -> must refuse ===")
rc, out = cli("unlink", "--category", "func", "--title-or-id", TMP)
check("A exits non-zero", rc != 0, "rc=%d %s" % (rc, out))
check("A says it refuses", "refusing" in out, out)
check("A left all 2 edges intact", len(edges_of(TMP)) == 2, as_keys(edges_of(TMP)))

print("=== case B: target + wrong relation -> no match ===")
rc, out = cli("unlink", "--category", "func", "--title-or-id", TMP,
              "--target", TARGET_A, "--relation", "derives-from")
check("B exits non-zero", rc != 0, "rc=%d %s" % (rc, out))
check("B reports no matching edge", "no matching edge" in out, out)
check("B left all 2 edges intact", len(edges_of(TMP)) == 2, as_keys(edges_of(TMP)))

print("=== case C: single target -> removes exactly that edge ===")
rc, out = cli("unlink", "--category", "func", "--title-or-id", TMP,
              "--target", TARGET_A)
check("C exits 0", rc == 0, "rc=%d %s" % (rc, out))
check("C reports removed 1", "removed 1 edge" in out, out)
left = edges_of(TMP)
check("C leaves 1 edge", len(left) == 1, as_keys(left))
check("C removed the named target, not the other one",
      as_keys(left) == ["arch/task_17931398547122b65eb[related]"], as_keys(left))

print("=== case D: relation only (no target) -> drops whole relation type ===")
rc, out = cli("unlink", "--category", "func", "--title-or-id", TMP,
              "--relation", "related")
check("D exits 0", rc == 0, "rc=%d %s" % (rc, out))
check("D leaves 0 edges", len(edges_of(TMP)) == 0, as_keys(edges_of(TMP)))

print("=== case E: unknown target -> refuses without touching anything ===")
put_func([{"itemId": TMP, "title": "UNLINK-TEST temp", "status": "done",
           "priority": "Low", "relatesTo": [
               {"listId": "arch", "itemId": "task_arch_b1", "relation": "related"}]}]
         + [i for i in get_func()["items"] if i["itemId"] != TMP], get_func()["rev"])
rc, out = cli("unlink", "--category", "func", "--title-or-id", TMP,
              "--target", "arch:does_not_exist")
check("E exits non-zero", rc != 0, "rc=%d %s" % (rc, out))
check("E left the real edge intact", len(edges_of(TMP)) == 1, as_keys(edges_of(TMP)))

print("=== case F: unknown task -> item-not-found, not a crash ===")
rc, out = cli("unlink", "--category", "func", "--title-or-id", "nope_missing",
              "--target", TARGET_A)
check("F exits non-zero", rc != 0, "rc=%d %s" % (rc, out))
check("F reports item not found", "not found" in out, out)

print("=== cleanup ===")
cur = get_func()
put_func([i for i in cur["items"] if i["itemId"] != TMP], cur["rev"])
final = get_func()
check("temp task gone", not any(i["itemId"] == TMP for i in final["items"]),
      [i["itemId"] for i in final["items"] if i["itemId"] == TMP])
check("func list size back to base", len(final["items"]) == len(base_ids),
      "%d vs %d" % (len(final["items"]), len(base_ids)))
check("func item ids identical to before the test",
      [i["itemId"] for i in final["items"]] == base_ids)

print("=== data integrity of the real F4 unlink (not part of the temp task) ===")
f4 = None
for i in final["items"]:
    if i["itemId"] == "task_func_f4":
        f4 = i
check("F4 exists", f4 is not None)
check("F4 has no outgoing edges", not (f4 or {}).get("relatesTo"),
      (f4 or {}).get("relatesTo"))
all_lists = api("/api/lists")
arch = [l for l in all_lists if l.get("listId") == "arch"][0]
b2 = [i for i in arch["items"] if i["itemId"] == "task_17931398547122b65eb"]
check("B2 arch node still present", len(b2) == 1)
inbound = 0
for l in all_lists:
    for i in l["items"]:
        for r in i.get("relatesTo") or []:
            if r.get("itemId") == "task_17931398547122b65eb":
                inbound += 1
check("B2 still has inbound edges (derives-from survives)", inbound >= 1, inbound)

# graph-level truth: the F4 -> B2 edge is gone from the link graph itself
graph = api("/api/links")
edges = graph.get("edges", [])
f4_out = [e for e in edges
          if e.get("from", {}).get("itemId") == "task_func_f4"]
check("link graph has no outgoing edge from F4", len(f4_out) == 0,
      [json.dumps(e, ensure_ascii=False) for e in f4_out][:3])
check("link graph still carries the rest of the edges", len(edges) >= 20, len(edges))
print("        (link graph now: %d edges, %d nodes)"
      % (len(edges), len(graph.get("nodes", []))))

print("\n=== %d passed, %d failed ===" % (passed, len(failed)))
if failed:
    for f in failed:
        print("  FAILED: " + f)
    sys.exit(1)
print("ALL GREEN")
