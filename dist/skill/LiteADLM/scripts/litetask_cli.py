# AI generated
#!/usr/bin/env python3
"""LiteTask PM CLI — deterministic helper for AI Agents to drive the
LiteTask-based software-project-management system at the repository root.

Two backends:
  1. API mode (default): if http://localhost:3000 is reachable, logs in as
     admin and uses PUT /api/lists/:id (type=UPDATE_ITEMS) to apply changes.
  2. File mode (fallback): edits data/shared_lists/<listId>.json directly.

Pure standard library (no pip installs). Usage:

  python litetask_cli.py categories
  python litetask_cli.py list --category func
  python litetask_cli.py add --category func --title "Example Task" --priority High \
        --local-directory "<PROJECT_DIR>/src/solver" --comment "example" \
        --relates arch:task_arch_001:derives-from
  python litetask_cli.py add --category func --title "Subtask" --parent "Example Task"
  python litetask_cli.py status --category func --title-or-id "Example Task" --status in-progress
  python litetask_cli.py status --category func --title-or-id "Example Task" --done true   # legacy: -> done/in-progress
  python litetask_cli.py statuses                          # print the legal transitions
  python litetask_cli.py priority --category func --title-or-id "Example Task" --priority Low
  python litetask_cli.py link --category func --title-or-id "Example Task" \
        --relates test:task_test_001:verifies
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

# Resolve the repository root from this file; LITETASK_REPO lets the CLI
# target another checkout without any machine-specific constant.
DEFAULT_ROOT = os.environ.get("LITETASK_REPO") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
DEFAULT_URL = "http://localhost:3000"
ADMIN_USER = "admin"
ADMIN_PASS = "admin"
ADMIN_ID = "user_admin"
VALID_PRIORITIES = {"High", "Medium", "Low"}
# F1 workflow states (mirrors data/categories.json)
VALID_STATUSES = ["open", "in-progress", "blocked", "verified", "done"]
CLOSED_STATUSES = {"done"}
STATUS_FLOW = {
    "open": ["in-progress", "blocked", "done"],
    "in-progress": ["open", "blocked", "verified", "done"],
    "blocked": ["open", "in-progress", "done"],
    "verified": ["in-progress", "blocked", "done"],
    "done": ["open", "in-progress", "blocked", "verified"],
}
DEFAULT_ASSIGNEE = "user_admin"
DEFAULT_CREATOR_ID = "user_1791622363912"
# Which AI Agent is doing the work. Override per-run with --agent (or LITETASK_AGENT).
DEFAULT_AGENT = os.environ.get("LITETASK_AGENT", "AI Agent")


def now_ts():
    return time.strftime("%Y-%m-%d %H:%M", time.localtime())


def gen_id():
    return "task_%d%s" % (int(time.time() * 1000), os.urandom(3).hex())


# ----------------------------- file backend -----------------------------
def file_path(root, list_id):
    return os.path.join(root, "data", "shared_lists", "%s.json" % list_id)


def read_file(root, list_id):
    with open(file_path(root, list_id), "r", encoding="utf-8") as f:
        return json.load(f)


def write_file_atomic(root, list_id, data):
    """Serialize then os.replace with retry to survive NTFS AV/share locks."""
    p = file_path(root, list_id)
    tmp = p + ".tmp"
    s = json.dumps(data, ensure_ascii=False, indent=2)
    last = None
    for attempt in range(1, 8):
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(s)
            os.replace(tmp, p)
            return
        except (PermissionError, OSError) as e:
            last = e
            time.sleep(min(attempt, 5))
    raise last


# ----------------------------- api backend -----------------------------
def _post(url, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def _put(url, payload, allow_status=()):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in allow_status:
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                return {"code": "HTTP_%d" % e.code}
        raise


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def _delete(url, payload, allow_status=()):
    """DELETE with a body — the item endpoint reads `confirm` from it."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in allow_status:
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                return {"code": "HTTP_%d" % e.code}
        raise


def server_reachable(url):
    """Alive probe: /api/health is anonymous in both modes; 200 and 503 both mean
    "the server is running" (503 only says its data tree is unhealthy)."""
    try:
        req = urllib.request.Request(url + "/api/health", method="GET")
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status in (200, 503)
    except urllib.error.HTTPError as e:
        return e.code in (200, 503)
    except Exception:
        return False


# --------------------------- item helpers -------------------------------
def find_item(items, key):
    key_l = key.lower()
    stack = list(items)
    while stack:
        it = stack.pop()
        if it.get("itemId") == key or key_l in it.get("title", "").lower():
            return it
        stack.extend(it.get("subTasks", []) or [])
    return None


def make_item(title, priority, local_directory, comment, extra_dirs=None, agent=None):
    dirs = [d for d in ([local_directory] + list(extra_dirs or [])) if d and d.strip()]
    return {
        "itemId": gen_id(),
        "title": title,
        "isDone": False,
        "status": "open",
        "statusHistory": [],
        "blockedReason": "",
        "dueDate": "",
        "priority": priority,
        "assignedTo": DEFAULT_ASSIGNEE,
        "createdBy": DEFAULT_ASSIGNEE,
        "createdByAgent": agent or DEFAULT_AGENT,
        "createdById": DEFAULT_CREATOR_ID,
        "createdAt": now_ts(),
        "closedBy": None,
        "closedById": None,
        "closedAt": None,
        "localDirectory": dirs[0] if dirs else "",
        "localDirectories": dirs[1:],
        "comment": comment or "",
        "subTasks": [],
        "relatesTo": [],
    }


def parse_relates(specs):
    out = []
    for s in specs or []:
        parts = s.split(":")
        if len(parts) >= 2 and parts[0] and parts[1]:
            out.append({
                "listId": parts[0],
                "itemId": parts[1],
                "relation": parts[2] if len(parts) >= 3 and parts[2] else "related",
            })
    return out


# ----------------------------- operations -------------------------------
def op_add(args, ctx):
    data = ctx["read"](args.category)
    items = data.setdefault("items", [])
    new = make_item(args.title, args.priority, args.local_directory, args.comment, args.extra_dir, args.agent)
    new["relatesTo"] = parse_relates(args.relates)
    if args.parent:
        parent = find_item(items, args.parent)
        if not parent:
            sys.exit("ERROR: parent '%s' not found in %s" % (args.parent, args.category))
        parent.setdefault("subTasks", []).append(new)
    else:
        items.append(new)
    ctx["write"](args.category, data)
    print("ADDED %s -> %s (id=%s)" % (args.category, args.title, new["itemId"]))
    # The id is already on stdout. Returning it here made main()'s sys.exit(rc)
    # treat a *successful* add as a failure: sys.exit("task_...") prints the id
    # to stderr and exits 1. That breaks the project rule "a non-zero exit code
    # is drift" — every add looked like it had failed. Found 2026-10-29.
    return 0


def status_of(it):
    v = it.get("status")
    if isinstance(v, str) and v in VALID_STATUSES:
        return v
    return "done" if it.get("isDone") else "open"


def dirs_of(it):
    return [d for d in ([it.get("localDirectory")] + list(it.get("localDirectories") or [])) if d]


def set_dirs(it, dirs):
    """F2: primary path stays localDirectory; extras go to localDirectories."""
    seen, uniq = set(), []
    for d in dirs:
        p = str(d or "").strip()
        if not p:
            continue
        k = p.rstrip("/\\").lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    it["localDirectory"] = uniq[0] if uniq else ""
    it["localDirectories"] = uniq[1:]


def op_path(args, ctx):
    data = ctx["read"](args.category)
    it = find_item(data.get("items", []), args.title_or_id)
    if not it:
        sys.exit("ERROR: item '%s' not found" % args.title_or_id)
    dirs = dirs_of(it)
    changed = False
    if args.add:
        for a in args.add:
            if a not in dirs:
                dirs.append(a)
                changed = True
    if args.remove:
        for r in args.remove:
            if r.isdigit() and 1 <= int(r) <= len(dirs):
                dirs[int(r) - 1] = ""
                changed = True
            elif r in dirs:
                dirs[dirs.index(r)] = ""
                changed = True
            else:
                sys.exit("ERROR: path '%s' not found (use 1-based index or exact text)" % r)
        dirs = [d for d in dirs if d]
    if args.primary:
        if args.primary not in dirs:
            dirs.insert(0, args.primary)
        else:
            dirs.remove(args.primary)
            dirs.insert(0, args.primary)
        changed = True
    if changed:
        set_dirs(it, dirs)
        ctx["write"](args.category, data)
    print("PATHS of '%s' (%d):" % (it.get("title"), len(dirs_of(it))))
    for i, d in enumerate(dirs_of(it), start=1):
        print("  [%d]%s %s" % (i, " primary" if i == 1 else "", d))


def apply_status(it, value):
    """Set the workflow state and keep isDone/closed* in lockstep."""
    it["status"] = value
    if value != "blocked":
        it["blockedReason"] = ""
    if value in CLOSED_STATUSES:
        it["isDone"] = True
        if not it.get("closedAt"):
            it["closedAt"] = now_ts()
        if not it.get("closedBy"):
            it["closedBy"] = DEFAULT_ASSIGNEE
        if not it.get("closedById"):
            it["closedById"] = DEFAULT_CREATOR_ID
    else:
        it["isDone"] = False
        it["closedBy"] = None
        it["closedById"] = None
        it["closedAt"] = None


def op_status(args, ctx):
    if args.status:
        if args.status not in VALID_STATUSES:
            sys.exit("ERROR: --status must be one of %s" % "/".join(VALID_STATUSES))
        value = args.status
    elif args.done is not None:
        value = "done" if args.done.lower() in ("true", "1", "yes") else "in-progress"
    else:
        sys.exit("ERROR: pass either --status <state> or --done <true|false>")

    data = ctx["read"](args.category)
    it = find_item(data.get("items", []), args.title_or_id)
    if not it:
        sys.exit("ERROR: item '%s' not found" % args.title_or_id)

    prev = status_of(it)
    # API mode: the server validates transitions and owns statusHistory.
    # FILE mode (server down): enforce the same flow and record the trail here.
    if prev != value and ctx.get("mode") == "FILE":
        allowed = STATUS_FLOW.get(prev)
        if allowed is not None and value not in allowed:
            sys.exit("ERROR: illegal transition %s -> %s (allowed: %s)"
                     % (prev, value, "/".join(allowed)))
        hist = it.get("statusHistory")
        if not isinstance(hist, list):
            hist = []
        hist.append({"from": prev, "to": value, "at": now_ts(), "by": DEFAULT_CREATOR_ID})
        it["statusHistory"] = hist[-20:]
    if args.reason is not None:
        it["blockedReason"] = args.reason
    apply_status(it, value)

    res = ctx["write"](args.category, data)
    if isinstance(res, dict) and res.get("code") == "INVALID_TRANSITION":
        sys.exit("ERROR: illegal transition %s -> %s : %s"
                 % (prev, value, res.get("error", "")))
    print("STATUS %s : %s -> %s (isDone=%s)" % (it["title"], prev, value, it["isDone"]))


def op_statuses(args, ctx):
    print("Statuses (F1):")
    for s in VALID_STATUSES:
        mark = " [closed]" if s in CLOSED_STATUSES else ""
        print("  %s%s" % (s, mark))
    print("Legal transitions:")
    for src, dsts in STATUS_FLOW.items():
        print("  %s -> %s" % (src, ", ".join(dsts)))


def op_priority(args, ctx):
    if args.priority not in VALID_PRIORITIES:
        sys.exit("ERROR: priority must be one of High/Medium/Low")
    data = ctx["read"](args.category)
    it = find_item(data.get("items", []), args.title_or_id)
    if not it:
        sys.exit("ERROR: item '%s' not found" % args.title_or_id)
    it["priority"] = args.priority
    ctx["write"](args.category, data)
    print("PRIORITY %s -> %s" % (it["title"], args.priority))


def op_link(args, ctx):
    rels = parse_relates(args.relates)
    if not rels:
        sys.exit("ERROR: no valid --relates given")
    data = ctx["read"](args.category)
    it = find_item(data.get("items", []), args.title_or_id)
    if not it:
        sys.exit("ERROR: item '%s' not found" % args.title_or_id)
    existing = {(r.get("listId"), r.get("itemId")) for r in it.get("relatesTo", [])}
    for r in rels:
        if (r["listId"], r["itemId"]) not in existing:
            it.setdefault("relatesTo", []).append(r)
    ctx["write"](args.category, data)
    print("LINK %s -> %s" % (it["title"],
          json.dumps(it.get("relatesTo", []), ensure_ascii=False)))


def op_unlink(args, ctx):
    """Inverse of `link`. `link` is append-only, so it can never fix a wrong
    edge — unlink removes edges by target and/or relation type.

    Targeting is MANDATORY: a bare `unlink` with neither --target nor
    --relation exits with an error instead of wiping every edge.
    """
    targets = parse_relates(args.target)
    if not targets and not args.relation:
        sys.exit("ERROR: unlink needs at least one --target <list:itemId> "
                 "(or --relation <type> to drop a whole relation type); "
                 "refusing to remove everything")
    data = ctx["read"](args.category)
    it = find_item(data.get("items", []), args.title_or_id)
    if not it:
        sys.exit("ERROR: item '%s' not found" % args.title_or_id)
    before = list(it.get("relatesTo", []) or [])
    tset = {(r["listId"], r["itemId"]) for r in targets}

    def keep(r):
        if targets:
            if (r.get("listId"), r.get("itemId")) not in tset:
                return True
            # explicit targets: --relation additionally narrows the match
            return bool(args.relation) and r.get("relation", "related") != args.relation
        return r.get("relation", "related") != args.relation

    after = [r for r in before if keep(r)]
    removed = [r for r in before if not keep(r)]
    if not removed:
        sys.exit("ERROR: no matching edge on '%s' (targets=%s relation=%s)" % (
            it["title"], sorted("%s/%s" % t for t in tset) or "-", args.relation or "-"))
    it["relatesTo"] = after
    ctx["write"](args.category, data)
    print("UNLINK %s: removed %d edge(s), %d left" % (it["title"], len(removed), len(after)))
    for r in removed:
        print("       - %s/%s [%s]" % (r.get("listId"), r.get("itemId"),
                                       r.get("relation", "related")))


def _print_tree(items, indent=0):
    for it in items:
        pad = "  " * indent
        print("%s[%s] %s  P=%s  S=%s" % (
            pad,
            "x" if it.get("isDone") else " ",
            it.get("title"),
            it.get("priority"),
            status_of(it),
        ))
        dirs = [it.get("localDirectory")] + list(it.get("localDirectories") or [])
        dirs = [d for d in dirs if d]
        if dirs:
            print("%s   dir[1]: %s" % (pad, dirs[0]))
            for i, d in enumerate(dirs[1:], start=2):
                print("%s   dir[%d]: %s" % (pad, i, d))
        for r in it.get("relatesTo", []) or []:
            print("%s   --[%s]--> %s/%s" % (pad, r.get("relation"),
                  r.get("listId"), r.get("itemId")))
        _print_tree(it.get("subTasks", []) or [], indent + 1)


def op_list(args, ctx):
    if args.category:
        data = ctx["read"](args.category)
        _print_tree(data.get("items", []))
    else:
        for l in ctx["read_all"]():
            print("[%s] %s (%s)" % (l.get("listId"), l.get("listName"), l.get("category")))
            _print_tree(l.get("items", []), indent=2)


def op_pending(args, ctx):
    """Unclaimed work a human typed into the board.

    A task is "pending" when it is not closed AND it carries no agent name —
    i.e. a human created it through the UI. Anything the Agent creates goes
    through `add --agent …`, which stamps `createdByAgent`, so it never shows
    up here. This is the queue an Agent should drain when asked "is there new
    work for me?".
    """
    open_states = {"open", "blocked", "in-progress"}
    rows = []
    for l in ctx["read_all"]():
        for it in l.get("items", []):
            st = it.get("status") or ("done" if it.get("isDone") else "open")
            if st not in open_states:
                continue
            if (it.get("createdByAgent") or "").strip():
                continue
            rows.append((l.get("listId"), st, it))
    if not rows:
        print("PENDING: none — no unclaimed human-created task on the board.")
        return
    print("PENDING %d unclaimed task(s) created by a human:" % len(rows))
    for lid, st, it in rows:
        print("  [%s/%s] %s" % (lid, st, it.get("title")))
        print("      itemId=%s  priority=%s  due=%s" % (
            it.get("itemId"), it.get("priority"), it.get("dueDate")))
        if args.verbose and it.get("comment"):
            print("      note: %s" % it["comment"].strip().replace("\n", " ")[:160])


def op_init(args, ctx):
    """Standalone-mode bootstrap: create the five category list files.

    Idempotent — an existing list file is never overwritten, so re-running
    init on a working tree is a no-op. Server mode does this automatically on
    startup; in file mode (no Node service) this is the one-time setup step.
    """
    if ctx["mode"] != "FILE":
        print("INIT: skipped — the running server bootstraps lists itself.")
        return 0
    root = args.root
    cats = ctx["categories"]().get("categories", [])
    if not cats:
        sys.exit("ERROR: %s has no categories.json — copy the seed there first."
                 % os.path.join(root, "data"))
    created = 0
    now = time.strftime("%Y-%m-%d %H:%M")
    for c in cats:
        lid = c.get("listId")
        if not lid:
            continue
        p = os.path.join(root, "data", "shared_lists", "%s.json" % lid)
        if os.path.exists(p):
            continue
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"listId": lid, "listName": c.get("name") or c.get("type"),
                       "category": c.get("type"), "owner": "admin",
                       "createdAt": now, "items": []},
                      f, ensure_ascii=False, indent=2)
            f.write("\n")
        created += 1
        print("INIT: created %s (%s)" % (lid, c.get("name") or c.get("type")))
    if not created:
        print("INIT: all %d category list(s) already present — nothing to do."
              % len(cats))
    else:
        print("INIT: %d list(s) created under %s" % (created, os.path.join(root, "data", "shared_lists")))
    return 0


def op_categories(args, ctx):
    cats = ctx["categories"]()
    print("Categories:")
    for c in cats.get("categories", []):
        print("  %s : %s (%s)" % (c.get("listId"), c.get("name"), c.get("type")))
    print("Relations:")
    for r in cats.get("relations", []):
        rid = r.get("value") if "value" in r else r.get("relation")
        print("  %s : %s" % (rid, r.get("label", r.get("desc", r.get("description", "")))))


def build_graph(lists):
    nodes = {}
    edges = []

    def visit(list_id, list_name, it):
        if not it or not it.get("itemId"):
            return
        nodes[it["itemId"]] = {
            "itemId": it["itemId"], "listId": list_id,
            "listName": list_name, "title": it.get("title", "Untitled"),
        }
        for r in it.get("relatesTo", []) or []:
            if r and r.get("listId") and r.get("itemId"):
                edges.append({
                    "from": {"listId": list_id, "itemId": it["itemId"]},
                    "to": {"listId": r["listId"], "itemId": r["itemId"]},
                    "relation": r.get("relation", "related"),
                })
        for s in it.get("subTasks", []) or []:
            visit(list_id, list_name, s)

    for l in lists:
        for it in l.get("items", []) or []:
            visit(l.get("listId"), l.get("listName"), it)
    return {"nodes": list(nodes.values()), "edges": edges}


# --------------------------- F3: trace & gaps ---------------------------
REL_LABELS = {
    "related": "Related", "derives-from": "Derives from", "verifies": "Verifies",
    "depends-on": "Depends on", "blocks": "Blocks",
}


def trace_graph(graph, root_id, direction="back", depth=3):
    """Cycle-safe BFS over the relation graph (same algorithm as /api/trace)."""
    nodes = {n["itemId"]: n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])
    if root_id not in nodes:
        sys.exit("ERROR: item not found in the relation graph: %s" % root_id)
    back = direction != "forward"
    forward = direction != "back"
    visited = {root_id}
    items = []
    frontier = [(root_id, [])]
    for d in range(1, depth + 1):
        nxt = []
        for cur_id, path in frontier:
            steps = []
            if forward:
                steps += [(e["to"]["itemId"], e["relation"], "forward")
                          for e in edges if e["from"]["itemId"] == cur_id]
            if back:
                steps += [(e["from"]["itemId"], e["relation"], "back")
                          for e in edges if e["to"]["itemId"] == cur_id]
            for other_id, relation, direction_step in steps:
                if other_id in visited:
                    continue
                n = nodes.get(other_id)
                if not n:
                    continue
                visited.add(other_id)
                new_path = path + [{"itemId": other_id, "listId": n["listId"],
                                    "title": n.get("title"), "relation": relation,
                                    "direction": direction_step}]
                items.append({"itemId": n["itemId"], "listId": n["listId"],
                              "title": n.get("title"), "depth": d, "path": new_path})
                nxt.append((other_id, new_path))
        if not nxt:
            break
        frontier = nxt
    return {"items": items, "count": len(items)}


def gap_rules(graph, rules, owner=None, referrer=None, relation=None, rule_value=None):
    """Coverage-gap computation (same semantics as /api/gaps)."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if owner:
        rules = [{"value": "adhoc",
                  "label": "%s task not referenced by %s" % (owner, referrer or "any list"),
                  "owner": owner, "referrer": referrer, "relation": relation}]
    elif rule_value:
        rules = [r for r in rules if r.get("value") == rule_value]
    out = []
    for rule in rules:
        if not rule.get("owner") or rule["owner"] == "*":
            linked = set()
            for e in edges:
                linked.add(e["from"]["itemId"])
                linked.add(e["to"]["itemId"])
            items = [n for n in nodes if n["itemId"] not in linked]
        else:
            covered = set()
            for e in edges:
                if rule.get("relation") and e["relation"] != rule["relation"]:
                    continue
                if rule.get("referrer") and e["from"]["listId"] != rule["referrer"]:
                    continue
                covered.add(e["to"]["itemId"])
            items = [n for n in nodes
                     if n["listId"] == rule["owner"] and n["itemId"] not in covered]
        out.append({"value": rule.get("value"), "label": rule.get("label"),
                    "owner": rule.get("owner"), "referrer": rule.get("referrer"),
                    "relation": rule.get("relation"), "count": len(items), "items": items})
    return {"rules": out}


def path_text(path):
    if not path:
        return ""
    out = "This item"
    for p in path:
        arrow = " <-[" if p["direction"] == "back" else " ->["
        out += arrow + REL_LABELS.get(p["relation"], p["relation"]) + "] " + str(p.get("title"))
    return out


def op_trace(args, ctx):
    data = ctx["read"](args.category)
    it = find_item(data.get("items", []), args.title_or_id)
    if not it:
        sys.exit("ERROR: item '%s' not found" % args.title_or_id)
    res = ctx["trace"](args.category, it["itemId"], args.direction, args.depth)
    items = res.get("items", [])
    print("TRACE %s (depth %d) of '%s' -> %d hit(s)" % (
        args.direction, args.depth, it.get("title"), len(items)))
    for t in items:
        print("  [%d hops] [%s] %s" % (t["depth"], t.get("listId"), t.get("title")))
        print("         %s" % path_text(t.get("path")))


def op_gaps(args, ctx):
    res = ctx["gaps"](owner=args.owner, referrer=args.referrer,
                      relation=args.relation, rule=args.rule)
    rules = res.get("rules", [])
    if not rules:
        print("No traceability rules configured (categories.json -> traceability).")
        return
    for r in rules:
        print("GAP %s: %d item(s)  (owner=%s referrer=%s relation=%s)" % (
            r.get("label"), r.get("count"), r.get("owner"), r.get("referrer"), r.get("relation")))
        for it in r.get("items", []):
            print("   - [%s] %s" % (it.get("listId"), it.get("title")))


def op_links(args, ctx):
    g = ctx["links"]()
    edges = g.get("edges", [])
    title_of = {n["itemId"]: n for n in g.get("nodes", [])}
    print("Relation graph: %d edges" % len(edges))
    for e in edges:
        f = title_of.get(e["from"]["itemId"], {})
        t = title_of.get(e["to"]["itemId"], {})
        # Archived nodes are still in the graph (their relations still count),
        # but they are no longer on the board — say so instead of hiding it.
        fmark = " (archived)" if f.get("archived") else ""
        tmark = " (archived)" if t.get("archived") else ""
        print("  [%s] %s%s  --[%s]-->  [%s] %s%s" % (
            f.get("listName", e["from"]["listId"]), f.get("title", e["from"]["itemId"]), fmark,
            e["relation"],
            t.get("listName", e["to"]["listId"]), t.get("title", e["to"]["itemId"]), tmark,
        ))


# ----------------------------- contexts ---------------------------------
# B3 follow-up: set by --force; lets a write overwrite a conflicting server copy.
FORCE_WRITE = False


def _short(v, n=48):
    if v is None:
        return "(empty)"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, list):
        s = ", ".join(str(x) for x in v)
    else:
        s = str(v)
    return s if len(s) <= n else s[: n - 1] + "…"


def format_conflict_diff(diff):
    """Render the 409 REV_CONFLICT diff payload as a compact text report."""
    if not isinstance(diff, dict):
        return "       (server sent no diff payload)"
    lines = []
    for it in diff.get("added", []) or []:
        lines.append("       + mine-only    %s  %s" % (it.get("itemId"), _short(it.get("title"), 40)))
    for it in diff.get("removed", []) or []:
        lines.append("       - server-only  %s  %s" % (it.get("itemId"), _short(it.get("title"), 40)))
    for c in diff.get("changed", []) or []:
        lines.append("       ~ changed      %s" % _short(c.get("title"), 40))
        for f in c.get("fields", []) or []:
            lines.append("           %-10s mine=%-24s server=%s"
                         % (f.get("label") or f.get("field"),
                            _short(f.get("mine"), 24), _short(f.get("server"), 24)))
    counts = diff.get("counts") or {}
    if not lines:
        lines.append("       (content is identical — only the revision token differs)")
    lines.append("       summary: +%s / -%s / ~%s items, %s fields"
                 % (counts.get("added", 0), counts.get("removed", 0),
                    counts.get("changed", 0), counts.get("fields", 0)))
    return "\n".join(lines)


def api_ctx(url):
    _post(url + "/api/login", {"username": ADMIN_USER, "password": ADMIN_PASS})

    def read(cat):
        lists = _get(url + "/api/lists")
        for l in lists:
            if l.get("listId") == cat:
                return l
        ids = [l.get("listId") for l in lists]
        sys.exit("ERROR: category '%s' not found (server has: %s)" % (cat, ids))

    def write(cat, data):
        # B3: send the rev we loaded with (optimistic concurrency). If the list
        # changed underneath us the server answers 409 instead of clobbering it.
        payload = {"type": "UPDATE_ITEMS", "items": data.get("items", []), "userId": ADMIN_ID}
        if data.get("rev"):
            payload["baseRev"] = data["rev"]
        # B3 follow-up: --force skips the rev check (use after reading the diff).
        if FORCE_WRITE:
            payload["force"] = True
            # Security boundary P2-C hard gate: --force is the operator's explicit decision to
            # overwrite, which is exactly what `confirm: true` asserts.
            payload["confirm"] = True
        # 400 = server refused the payload (e.g. F1 INVALID_TRANSITION); return it
        # so the caller can report the exact violation instead of raising.
        resp = _put(url + "/api/lists/" + cat, payload, allow_status=(409, 400))
        if isinstance(resp, dict) and resp.get("code") == "REV_CONFLICT":
            sys.exit("ERROR: REV_CONFLICT — '%s' changed since this command loaded it "
                     "(another tab/user/direct file edit).\n%s\n"
                     "Re-run to pick up the latest, or add --force to overwrite with this version."
                     % (cat, format_conflict_diff(resp.get("diff"))))
        return resp

    def read_all():
        return _get(url + "/api/lists")

    def categories():
        return _get(url + "/api/categories")

    def links():
        return _get(url + "/api/links")

    def archive(cat):
        # Security boundary P2-C hard gate: the server needs an affirmative confirm. The CLI
        # is an operator typing the command (and --dry-run exists for looking
        # first), so `litetask archive <cat>` *is* the confirmation.
        return _post(url + "/api/lists/" + cat + "/archive",
                     {"userId": ADMIN_ID, "confirm": True})

    def read_archive(cat):
        return _get(url + "/api/archive/" + cat)

    def unarchive(cat, item_ids=None):
        payload = {"userId": ADMIN_ID}
        if item_ids:
            payload["itemIds"] = list(item_ids)
        return _post(url + "/api/lists/" + cat + "/unarchive", payload)

    # Item-level write P3-B: change one item without uploading the whole list.
    def item_add(cat, item):
        return _post(url + "/api/lists/" + cat + "/items",
                     {"userId": ADMIN_ID, "item": item})

    def item_update(cat, iid, item, rev=None):
        payload = {"userId": ADMIN_ID, "item": item}
        if rev:
            payload["baseRev"] = rev
        return _put(url + "/api/lists/%s/items/%s" % (cat, urllib.parse.quote(str(iid))), payload,
                    allow_status=(409, 400, 404))

    def item_delete(cat, iid):
        # Hard gate: the CLI command *is* the confirmation, as with `archive`.
        return _delete(url + "/api/lists/%s/items/%s" % (cat, urllib.parse.quote(str(iid))),
                       {"userId": ADMIN_ID, "confirm": True},
                       allow_status=(400, 403, 404))

    def trace(cat, item_id, direction, depth):
        qs = urllib.parse.urlencode({"listId": cat, "itemId": item_id,
                                     "direction": direction, "depth": depth})
        return _get(url + "/api/trace?" + qs)

    def integrity():
        # P3-D + P3-E: read-only data-quality report (see op_lint).
        return _get(url + "/api/integrity")

    def gaps(owner=None, referrer=None, relation=None, rule=None):
        params = {}
        if owner:
            params["owner"] = owner
            if referrer:
                params["referrer"] = referrer
            if relation:
                params["relation"] = relation
        elif rule:
            params["rule"] = rule
        qs = urllib.parse.urlencode(params)
        return _get(url + "/api/gaps" + ("?" + qs if qs else ""))

    return {"mode": "API", "read": read, "write": write, "read_all": read_all,
            "categories": categories, "links": links, "archive": archive,
            "read_archive": read_archive, "unarchive": unarchive,
            "trace": trace, "gaps": gaps,
            # Item-level write P3-B — absent in file mode, which is exactly how
            # op_item() decides which branch to take.
            "item_add": item_add, "item_update": item_update,
            "item_delete": item_delete, "integrity": integrity}


def file_ctx(root):
    def read(cat):
        try:
            return read_file(root, cat)
        except FileNotFoundError:
            sys.exit("ERROR: category file %s.json not found under %s" % (cat, root))

    def write(cat, data):
        write_file_atomic(root, cat, data)

    def read_all():
        out = []
        d = os.path.join(root, "data", "shared_lists")
        if not os.path.isdir(d):
            return out
        for fn in os.listdir(d):
            if fn.endswith(".json"):
                with open(os.path.join(d, fn), "r", encoding="utf-8") as f:
                    out.append(json.load(f))
        out.sort(key=lambda x: x.get("listId", ""))
        return out

    def categories():
        p = os.path.join(root, "data", "categories.json")
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"categories": [], "relations": []}

    def links():
        return build_graph(read_all())

    def trace(cat, item_id, direction, depth):
        return trace_graph(build_graph(read_all()), item_id, direction, depth)

    def gaps(owner=None, referrer=None, relation=None, rule=None):
        cfg = categories()
        return gap_rules(build_graph(read_all()), cfg.get("traceability", []),
                         owner, referrer, relation, rule)

    return {"mode": "FILE", "read": read, "write": write, "read_all": read_all,
            "categories": categories, "links": links, "trace": trace, "gaps": gaps}


# ------------------------------- main -----------------------------------
def split_closed(items, cat):
    """A1: split items into (kept, moved) — everything isDone leaves the active file."""
    kept, moved = [], []
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    for it in items or []:
        if it.get("isDone"):
            m = dict(it)
            m["archivedAt"] = stamp
            m["archivedFrom"] = cat
            moved.append(m)
            continue
        open_subs = []
        for s in it.get("subTasks") or []:
            if s.get("isDone"):
                m = dict(s)
                m["archivedAt"] = stamp
                m["archivedFrom"] = cat
                m["parentItemId"] = it.get("itemId")
                m["parentTitle"] = it.get("title")
                moved.append(m)
            else:
                open_subs.append(s)
        it2 = dict(it)
        it2["subTasks"] = open_subs
        kept.append(it2)
    return kept, moved


def op_archive(args, ctx):
    """Move closed work into data/archive/<category>.json (A1)."""
    cat = args.category
    if hasattr(ctx, "get") and callable(ctx.get("archive")):
        # API mode — server does the work under its write lock
        if args.dry_run:
            data = ctx["read"](cat)
            kept, moved = split_closed(data.get("items", []), cat)
            print("DRY-RUN: Archiving %d items, %d items remaining in main list:" % (len(moved), len(kept)))
            for m in moved:
                print("   -", m["title"])
            return
        r = ctx["archive"](cat)
        print("ARCHIVE %s -> moved=%s remaining=%s archiveCount=%s"
              % (cat, r.get("moved"), r.get("remaining"), r.get("archiveCount")))
        return

    # File mode (server down): do it locally
    data = ctx["read"](cat)
    kept, moved = split_closed(data.get("items", []), cat)
    if args.dry_run:
        print("DRY-RUN: Archiving %d items, %d items remaining in main list:" % (len(moved), len(kept)))
        for m in moved:
            print("   -", m["title"])
        return
    if not moved:
        print("ARCHIVE %s -> No completed items to archive" % cat)
        return
    adir = os.path.join(args.root, "data", "archive")
    os.makedirs(adir, exist_ok=True)
    apath = os.path.join(adir, "%s.json" % cat)
    archive = {"listId": cat, "listName": data.get("listName", ""), "items": []}
    if os.path.exists(apath):
        with open(apath, "r", encoding="utf-8") as f:
            archive = json.load(f)
    archive.setdefault("items", []).extend(moved)
    archive["lastArchivedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(apath, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)
    data["items"] = kept
    write_file_atomic(args.root, cat, data)
    print("ARCHIVE %s -> moved=%d remaining=%d archiveCount=%d"
          % (cat, len(moved), len(kept), len(archive["items"])))


# ----------------------------- lint (P3-D + P3-E) ---------------------------
def op_lint(args, ctx):
    """Dangling relatesTo edges and itemIds that are not unique.

    Read-only, and deliberately so: this is the report the strict variant
    ("refuse an edge whose target does not exist") would be based on. Printing
    it first is the cheap half; refusing writes is a separate decision.
    """
    if not callable(ctx.get("integrity")):
        sys.exit("ERROR: lint needs the server (GET /api/integrity). "
                 "Start it with `litetask server ensure` and re-run.")
    r = ctx["integrity"]()
    dangling = r.get("danglingEdges") or []
    dups = r.get("duplicateItemIds") or []

    print("INTEGRITY %s — %d list(s), %d item(s)"
          % (r.get("checkedAt", "")[:19], r.get("lists", 0), r.get("items", 0)))

    if not dangling and not dups:
        print("  clean: no dangling relations, no duplicate itemIds")
        return 0

    if dangling:
        print("  DANGLING RELATIONS (%d) — the target does not exist:" % len(dangling))
        for d in dangling:
            print("    %s/%s (%s) -%s-> %s/%s   [%s]"
                  % (d.get("listId"), d.get("itemId"), (d.get("title") or "")[:32],
                     d.get("relation") or "?", (d.get("target") or {}).get("listId"),
                     (d.get("target") or {}).get("itemId"), d.get("reason")))
    if dups:
        print("  DUPLICATE ITEM IDS (%d) — one id, several items:" % len(dups))
        for d in dups:
            where = ", ".join("%s(%s)" % (o.get("listId"), (o.get("title") or "")[:24])
                              for o in d.get("occurrences", []))
            print("    %s x%d %s   %s" % (d.get("itemId"), d.get("count"),
                                          "[Cross-list]" if d.get("crossList") else "[Same-list]",
                                          where))
    # Exit code carries the verdict so a script can gate on it.
    return 1 if (args.strict and (dangling or dups)) else 0


# ----------------------------- item (P3-B) ----------------------------------
# One item at a time, instead of `read the list -> patch -> upload everything`.
# The point is not convenience: a whole-list PUT from a stale copy is how items
# get dropped, and it is why the body limit had to be raised to 16 MB in the
# first place. These commands send exactly one item and let the server apply
# every guard (schema, F1 status machine, rev concurrency) to it.
def find_item_by_id(items, item_id):
    """(parent_list, index, item) or (None, None, None) — subtasks included.

    Deliberately NOT called find_item: that name is already taken by the
    title-or-id lookup used by `status` / `priority` / `link`. Shadowing it
    would have silently broken every one of those commands — this one matches
    itemIds exactly, which is a different question.
    """
    def walk(arr):
        for n, it in enumerate(arr or []):
            if str(it.get("itemId")) == str(item_id):
                return arr, n, it
            hit = walk(it.get("subTasks") or [])
            if hit[2] is not None:
                return hit
        return None, None, None
    return walk(items)


def op_item(args, ctx):
    cat = args.category
    data = ctx["read"](cat)
    items = data.get("items", [])

    if args.item_cmd == "get":
        _, _, it = find_item_by_id(items, args.id)
        if it is None:
            sys.exit("ERROR: item %s not found in %s" % (args.id, cat))
        print(json.dumps(it, ensure_ascii=False, indent=2))
        return 0

    if args.item_cmd == "add":
        if args.file:
            with open(args.file, "r", encoding="utf-8") as f:
                item = json.load(f)
        elif args.json:
            item = json.loads(args.json)
        else:
            sys.exit("ERROR: --json '{...}' or --file <path> is required")
        if not item.get("itemId"):
            sys.exit("ERROR: the item needs an itemId")
        if callable(ctx.get("item_add")):
            r = ctx["item_add"](cat, item)
            print("ITEM ADD %s -> rev=%s items=%s" % (r.get("itemId") or item["itemId"],
                                                      r.get("rev"), r.get("items")))
            return 0
        if find_item_by_id(items, item["itemId"])[2] is not None:
            sys.exit("ERROR: itemId %s already exists in %s" % (item["itemId"], cat))
        data["items"] = items + [item]
        ctx["write"](cat, data)
        print("ITEM ADD %s -> rev=%s items=%d (file mode)"
              % (item["itemId"], data.get("rev"), len(data["items"])))
        return 0

    if args.item_cmd == "status":
        _, _, it = find_item_by_id(items, args.id)
        if it is None:
            sys.exit("ERROR: item %s not found in %s" % (args.id, cat))
        nxt = dict(it, status=args.status)
        if callable(ctx.get("item_update")):
            r = ctx["item_update"](cat, args.id, nxt, data.get("rev"))
            if isinstance(r, dict) and r.get("code") == "INVALID_TRANSITION":
                sys.exit("ERROR: %s" % r.get("error"))
            if isinstance(r, dict) and r.get("code") == "REV_CONFLICT":
                sys.exit("ERROR: '%s' changed since this command loaded it; re-run "
                         "(or use the whole-list write with --force)" % cat)
            print("ITEM STATUS %s -> %s (rev=%s)" % (args.id, args.status, r.get("rev")))
            return 0
        nxt["isDone"] = args.status == "done"
        data["items"] = items
        ctx["write"](cat, data)
        print("ITEM STATUS %s -> %s (file mode)" % (args.id, args.status))
        return 0

    if args.item_cmd == "rm":
        arr, idx, it = find_item_by_id(items, args.id)
        if it is None:
            sys.exit("ERROR: item %s not found in %s" % (args.id, cat))
        if callable(ctx.get("item_delete")):
            r = ctx["item_delete"](cat, args.id)
            if isinstance(r, dict) and r.get("code"):
                sys.exit("ERROR: %s" % (r.get("error") or r.get("code")))
            print("ITEM RM %s -> items=%s" % (args.id, r.get("items")))
            return 0
        arr.pop(idx)
        ctx["write"](cat, data)
        print("ITEM RM %s (file mode)" % args.id)
        return 0

    sys.exit("ERROR: unknown item command")


# ----------------------------- unarchive (P1) -------------------------------
# The way back out of data/archive/. On 2026-10-29 a manual archive moved 17
# items with no supported way back — they were recovered by hand from git (todo
# commit b780480). Archiving without a way back is a one-way door, so this is
# the CLI half of the fix, mirroring POST /api/lists/:id/unarchive.
#
# Restored entries are appended: top-level ones to the end of the list, subtasks
# to the end of their parent's subTasks. The archive records no position, so the
# round-trip preserves content and structure, not order.
ARCHIVE_MARKERS = ("archivedAt", "archivedFrom", "parentItemId", "parentTitle")


def content_rev(items):
    """Same token the server derives: sha256(JSON.stringify(items)).slice(0,16)."""
    raw = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def strip_markers(it):
    out = {k: v for k, v in it.items() if k not in ARCHIVE_MARKERS}
    if out.get("subTasks"):
        out["subTasks"] = [strip_markers(s) for s in out["subTasks"]]
    return out


def select_archived(items, wanted):
    """(chosen, unknown) — wanted=None or [] means everything."""
    if not wanted:
        return list(items), []
    known = set(i.get("itemId") for i in items)
    unknown = [w for w in wanted if w not in known]
    chosen = [i for i in items if i.get("itemId") in set(wanted)]
    return chosen, unknown


def reattach(items, chosen):
    """Put archived entries back into `items`; return (items, reattached, orphaned).

    A subtask whose parent is restored in the same call waits for it: it goes
    back on the queue instead of being orphaned. Every queued entry is either
    attached or appended, so the queue always drains.
    """
    by_id = {}

    def walk(arr):
        for it in arr or []:
            iid = it.get("itemId")
            if iid and iid not in by_id:
                by_id[iid] = it
                walk(it.get("subTasks"))

    walk(items)
    chosen_ids = set(i.get("itemId") for i in chosen)
    out = list(items)
    reattached = orphaned = 0
    queue = list(chosen)
    guard = len(chosen) * 4 + 20
    while queue and guard > 0:
        guard -= 1
        it = queue.pop(0)
        pid = it.get("parentItemId")
        parent = by_id.get(pid) if pid else None
        if parent:
            if not isinstance(parent.get("subTasks"), list):
                parent["subTasks"] = []
            restored = strip_markers(it)
            parent["subTasks"].append(restored)
            by_id[restored["itemId"]] = restored
            reattached += 1
            continue
        if pid and pid in chosen_ids and guard > 1:
            queue.append(it)          # its parent is still queued
            continue
        restored = strip_markers(it)
        out.append(restored)
        by_id[restored["itemId"]] = restored
        if pid:
            orphaned += 1             # parent is neither live nor in this batch
    for it in queue:                  # guard exhausted: never lose an entry
        out.append(strip_markers(it))
        if it.get("parentItemId"):
            orphaned += 1
    return out, reattached, orphaned


def op_unarchive(args, ctx):
    """Move archived work back into data/shared_lists/<category>.json."""
    cat = args.category
    wanted = args.item or None

    if callable(ctx.get("unarchive")):
        if args.dry_run:
            doc = ctx["read_archive"](cat)
            chosen, unknown = select_archived(doc.get("items", []), wanted)
            if unknown:
                sys.exit("ERROR: not in the archive: %s" % ", ".join(unknown))
            print("DRY-RUN: Restoring %d items, %d items remaining in archive:"
                  % (len(chosen), len(doc.get("items", [])) - len(chosen)))
            for m in chosen:
                print("   -", m.get("title"))
            return 0
        r = ctx["unarchive"](cat, wanted)
        if isinstance(r, dict) and r.get("code"):
            sys.exit("ERROR: %s %s" % (r.get("code"), r.get("error", "")))
        print("UNARCHIVE %s -> moved=%s reattached=%s orphaned=%s remaining=%s archiveCount=%s"
              % (cat, r.get("moved"), r.get("reattached"), r.get("orphaned"),
                 r.get("remaining"), r.get("archiveCount")))
        return 0

    # File mode (server down): do it locally, same rules as the endpoint.
    apath = os.path.join(args.root, "data", "archive", "%s.json" % cat)
    if not os.path.exists(apath):
        print("UNARCHIVE %s -> Archive is empty, nothing to restore" % cat)
        return 0
    with open(apath, "r", encoding="utf-8") as f:
        archive = json.load(f)
    archived = archive.get("items", [])
    chosen, unknown = select_archived(archived, wanted)
    if unknown:
        sys.exit("ERROR: not in the archive: %s" % ", ".join(unknown))
    if args.dry_run:
        print("DRY-RUN: Restoring %d items, %d items remaining in archive:"
              % (len(chosen), len(archived) - len(chosen)))
        for m in chosen:
            print("   -", m.get("title"))
        return 0
    if not chosen:
        print("UNARCHIVE %s -> No archived items selected" % cat)
        return 0
    data = ctx["read"](cat)
    items, reattached, orphaned = reattach(data.get("items", []), chosen)
    data["items"] = items
    data["rev"] = content_rev(items)
    ctx["write"](cat, data)
    returned = set(i.get("itemId") for i in chosen)
    kept = [i for i in archived if i.get("itemId") not in returned]
    if kept:
        archive["items"] = kept
        with open(apath, "w", encoding="utf-8") as f:
            json.dump(archive, f, ensure_ascii=False, indent=2)
    else:
        os.remove(apath)
    print("UNARCHIVE %s -> moved=%d reattached=%d orphaned=%d remaining=%d archiveCount=%d"
          % (cat, len(chosen), reattached, orphaned, len(items), len(kept)))
    return 0


# ----------------------------- restore (P0-2) -------------------------------
# A snapshot that has never been restored is only a rumour. The 2026-10-28
# cleanup deleted the M2 snapshot and, because it was unreproducible, three
# assertions had to be retired as a permanent loss — the tree had backups for
# months and no way to prove any of them could be read back.
BACKUP_STAMP_RE = re.compile(r"\.(\d{8}T\d{9}Z)\.json$")


def collect_stamps(root):
    """{stamp: [(path as it was under data/, absolute snapshot path)]}"""
    bd = os.path.join(root, "backup")
    out = {}
    if not os.path.isdir(bd):
        return out
    for dirpath, _, files in os.walk(bd):
        for fn in files:
            m = BACKUP_STAMP_RE.search(fn)
            if not m:
                continue
            full = os.path.join(dirpath, fn)
            # The stamp offset belongs to the file name, not to the path that
            # carries its directory — slicing the relative path with it produced
            # "shar.json" instead of "shared_lists/func.json" (found by
            # grade_restore_drill.py, 2026-10-29).
            stem = fn[:m.start()] + ".json"
            rel = os.path.relpath(os.path.join(dirpath, stem), bd).replace("\\", "/")
            out.setdefault(m.group(1), []).append((rel, full))
    return out


def op_restore(args, ctx=None):
    """Restore a startup snapshot: list them, restore into a directory, or write
    back into data/ behind an explicit --yes.

    Restore is a file-level operation, so it always works against --root and
    never routes through the server: the server has no snapshot API, and a
    recovery path must work when the server is the thing that is broken.
    """
    root = args.root
    bd = os.path.join(root, "backup")
    if not os.path.isdir(bd):
        sys.exit("ERROR: no backup/ under %s" % root)
    stamps = collect_stamps(root)
    if not stamps:
        sys.exit("ERROR: no stamped snapshots under %s" % bd)
    order = sorted(stamps, reverse=True)

    if not args.stamp:
        print("Available snapshots under %s (newest first): %d" % (bd, len(order)))
        for s in order[:20]:
            print("  %s   %d file(s)" % (s, len(stamps[s])))
        print()
        print("Restore somewhere safe:  restore --stamp <stamp> --to <dir>")
        print("Restore in place:        restore --stamp <stamp> --apply --yes")
        return 0

    if args.stamp not in stamps:
        sys.exit("ERROR: unknown stamp %r — available: %s"
                 % (args.stamp, ", ".join(order[:5])))

    if args.apply:
        if not args.yes:
            sys.exit("ERROR: --apply overwrites data/ under %s. Re-run with --yes "
                     "to confirm, or use --to <dir> to restore somewhere safe." % root)
        target = os.path.join(root, "data")
    elif args.to:
        target = args.to
    else:
        sys.exit("ERROR: pass --to <dir> (safe) or --apply --yes (overwrites data/)")

    written = 0
    for original, snapshot in sorted(stamps[args.stamp]):
        dst = os.path.join(target, *original.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(snapshot, dst)
        written += 1
    print("RESTORED stamp %s -> %s (%d file(s)); source %s"
          % (args.stamp, target, written, bd))
    return 0


# ----------------------- server lifecycle (Step 0 of the skill) -----------------------
def op_server(args, ctx=None):
    """Make sure the LiteTask server is reachable.

    action=ensure (default): if the port already answers, do nothing; otherwise
    launch `node server.js` in the project root (detached, so it survives the
    command that spawned it) and poll until the port answers or --timeout.
    action=status: just report running/down.

    It only ever starts a server when the port is currently free, so it will
    never clobber an already-running instance. This is the lightweight answer to
    the "no daemon" gap: the skill guarantees the board is up before any read or
    write, instead of relying on an OS-level supervisor.
    """
    import subprocess
    from urllib.parse import urlparse

    parsed = urlparse(args.url)
    explicit_port = getattr(args, "port", None)
    # Documented precedence: --url wins when it carries a non-default port;
    # otherwise --port drives BOTH the probe and the launch. Without this
    # reconciliation the probe always hit the default url's port, so
    # `server --action status --port <free>` wrongly reported the default
    # instance as RUNNING (found by grade_server_subcommand.py, 2026-10-29).
    if (explicit_port and explicit_port != parsed.port
            and parsed.port in (None, 3000)):
        port = explicit_port
        args.url = "%s://%s:%d%s" % (parsed.scheme or "http",
                                     parsed.hostname or "localhost",
                                     port, parsed.path or "/")
    else:
        port = parsed.port or explicit_port or 3000
    action = getattr(args, "action", "ensure")

    if server_reachable(args.url):
        print("[server] RUNNING at %s" % args.url)
        return 0

    if action == "status":
        print("[server] DOWN at %s" % args.url)
        return 1

    root = args.root
    log = os.path.join(root, "server.log")
    env = dict(os.environ)
    env["PORT"] = str(port)
    print("[server] not running; launching `node server.js` in %s (log -> %s) ..."
          % (root, log))
    try:
        if os.name == "nt":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(
                subprocess, "DETACHED_PROCESS", 0)
            with open(log, "ab") as lf:
                subprocess.Popen(
                    ["node", "server.js"], cwd=root, env=env,
                    stdout=lf, stderr=subprocess.STDOUT,
                    creationflags=flags, close_fds=True)
        else:
            with open(log, "ab") as lf:
                subprocess.Popen(
                    ["node", "server.js"], cwd=root, env=env,
                    stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
    except Exception as e:
        print("[server] FAILED to launch: %s" % e, file=sys.stderr)
        return 1

    deadline = time.time() + getattr(args, "timeout", 15)
    while time.time() < deadline:
        if server_reachable(args.url):
            print("[server] UP at %s" % args.url)
            return 0
        time.sleep(0.5)
    print("[server] did NOT come up within %ds; inspect %s"
          % (getattr(args, "timeout", 15), log), file=sys.stderr)
    return 1


def main():
    ap = argparse.ArgumentParser(description="LiteTask PM CLI")
    ap.add_argument("--root", default=DEFAULT_ROOT, help="project root (file mode)")
    ap.add_argument("--url", default=DEFAULT_URL, help="server base url (api mode)")
    ap.add_argument("--force", action="store_true",
                   help="B3: overwrite even if the list changed since this command "
                        "loaded it (use after reviewing the printed conflict diff)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("categories")
    p.set_defaults(func=op_categories)

    p = sub.add_parser("init",
                       help="standalone-mode bootstrap: create the five empty "
                            "category list files (idempotent, file mode only)")
    p.set_defaults(func=op_init)

    p = sub.add_parser("list")
    p.add_argument("--category", default=None)
    p.set_defaults(func=op_list)

    p = sub.add_parser("add")
    p.add_argument("--category", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--priority", default="Medium")
    p.add_argument("--local-directory", default="",
                   help="primary source path or URL (first --extra-dir wins if omitted)")
    p.add_argument("--extra-dir", action="append", default=[], dest="extra_dir",
                   help="additional source path/URL; repeat for multiple (F2)")
    p.add_argument("--comment", default="")
    p.add_argument("--parent", default=None)
    p.add_argument("--relates", action="append", default=[])
    p.add_argument("--agent", default=None,
                   help="AI Agent that owns this work (stored as createdByAgent; default %s)" % DEFAULT_AGENT)
    p.set_defaults(func=op_add)

    p = sub.add_parser("status")
    p.add_argument("--category", required=True)
    p.add_argument("--title-or-id", required=True)
    p.add_argument("--status", default=None, choices=VALID_STATUSES,
                   help="workflow state: %s" % "/".join(VALID_STATUSES))
    p.add_argument("--done", default=None,
                   help="legacy flag: true -> done, false -> in-progress")
    p.add_argument("--reason", default=None, help="blocked reason text (stored on the item)")
    p.set_defaults(func=op_status)

    p = sub.add_parser("statuses")
    p.set_defaults(func=op_statuses)

    p = sub.add_parser("path")
    p.add_argument("--category", required=True)
    p.add_argument("--title-or-id", required=True)
    p.add_argument("--add", action="append", default=[],
                   help="append a source path/URL; repeatable (F2)")
    p.add_argument("--remove", action="append", default=[],
                   help="remove by 1-based index or exact text; repeatable")
    p.add_argument("--primary", default=None,
                   help="promote this existing/new path to primary (first) position")
    p.set_defaults(func=op_path)

    p = sub.add_parser("priority")
    p.add_argument("--category", required=True)
    p.add_argument("--title-or-id", required=True)
    p.add_argument("--priority", required=True)
    p.set_defaults(func=op_priority)

    p = sub.add_parser("link")
    p.add_argument("--category", required=True)
    p.add_argument("--title-or-id", required=True)
    p.add_argument("--relates", action="append", default=[])
    p.set_defaults(func=op_link)

    p = sub.add_parser("unlink")
    p.add_argument("--category", required=True)
    p.add_argument("--title-or-id", required=True)
    p.add_argument("--target", action="append", default=[],
                   help="edge to remove: <list>:<itemId>[:relation] (repeatable)")
    p.add_argument("--relation", default=None,
                   help="without --target: drop every edge of this relation type")
    p.set_defaults(func=op_unlink)

    p = sub.add_parser("links")
    p.set_defaults(func=op_links)

    p = sub.add_parser("trace")
    p.add_argument("--category", required=True)
    p.add_argument("--title-or-id", required=True)
    p.add_argument("--direction", default="back", choices=["back", "forward", "both"])
    p.add_argument("--depth", type=int, default=3)
    p.set_defaults(func=op_trace)

    p = sub.add_parser("gaps")
    p.add_argument("--rule", default=None, help="configured rule value from categories.json")
    p.add_argument("--owner", default=None, help="ad-hoc: items in this category …")
    p.add_argument("--referrer", default=None, help="… not referenced from this category")
    p.add_argument("--relation", default=None, help="… via this relation (optional)")
    p.set_defaults(func=op_gaps)

    p = sub.add_parser("pending",
                       help="unclaimed tasks a human created through the UI")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="also print the note left on each task")
    p.set_defaults(func=op_pending)

    p = sub.add_parser("archive")
    p.add_argument("--category", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=op_archive)

    p = sub.add_parser("unarchive",
                       help="P1: bring archived work back into the active list")
    p.add_argument("--category", required=True)
    p.add_argument("--item", action="append", default=[],
                   help="itemId to bring back; repeatable (default: everything)")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=op_unarchive)

    p = sub.add_parser("restore",
                       help="P0-2: restore a startup snapshot (list / --to / --apply)")
    p.add_argument("--stamp", default=None,
                   help="snapshot stamp; omit to list the available ones")
    p.add_argument("--to", default=None,
                   help="restore into this directory (safe; never touches data/)")
    p.add_argument("--apply", action="store_true",
                   help="write the snapshot back into data/ (destructive)")
    p.add_argument("--yes", action="store_true",
                   help="confirmation required by --apply")
    p.set_defaults(func=op_restore)

    p = sub.add_parser("item",
                       help="P3-B: read/write ONE item (no whole-list upload)")
    isub = p.add_subparsers(dest="item_cmd", required=True)

    q = isub.add_parser("get", help="print one item as JSON")
    q.add_argument("--category", required=True)
    q.add_argument("--id", required=True)
    q.set_defaults(func=op_item)

    q = isub.add_parser("add", help="append one item (--json or --file)")
    q.add_argument("--category", required=True)
    q.add_argument("--json", default=None)
    q.add_argument("--file", default=None)
    q.set_defaults(func=op_item)

    q = isub.add_parser("status", help="change one item's workflow state")
    q.add_argument("--category", required=True)
    q.add_argument("--id", required=True)
    q.add_argument("--status", required=True, choices=VALID_STATUSES)
    q.set_defaults(func=op_item)

    q = isub.add_parser("rm", help="remove one item (destructive; confirmed by the command)")
    q.add_argument("--category", required=True)
    q.add_argument("--id", required=True)
    q.set_defaults(func=op_item)

    p = sub.add_parser("lint",
                       help="P3-D/E: report dangling relations and duplicate itemIds")
    p.add_argument("--strict", action="store_true",
                   help="exit 1 when anything is reported (for scripts/CI)")
    p.set_defaults(func=op_lint)

    p = sub.add_parser("server",
                       help="ensure the LiteTask server is up (Step 0 of the skill)")
    p.add_argument("--action", default="ensure", choices=["ensure", "status"],
                   help="ensure=start if down (default); status=report only")
    p.add_argument("--port", type=int, default=3000,
                   help="port to probe/launch on (default 3000; --url wins if it carries a port)")
    p.add_argument("--timeout", type=int, default=15,
                   help="seconds to wait for the server after launch")
    p.set_defaults(func=op_server)

    args = ap.parse_args()

    global FORCE_WRITE
    FORCE_WRITE = bool(getattr(args, "force", False))
    if FORCE_WRITE:
        print("[B3] --force: writes will overwrite a conflicting server version",
              file=sys.stderr)

    if server_reachable(args.url):
        try:
            ctx = api_ctx(args.url)
            mode = "API"
        except Exception as e:
            ctx = file_ctx(args.root)
            mode = "FILE(fallback:%s)" % e
    else:
        ctx = file_ctx(args.root)
        mode = "FILE"
    print("[mode=%s]" % mode, file=sys.stderr)
    try:
        rc = args.func(args, ctx)
    except urllib.error.HTTPError as e:
        # Shared mode requires a session cookie the CLI does not hold. Rather than
        # pretending the server is down, fall back to the file mode explicitly.
        if e.code in (401, 403) and str(mode).startswith("API"):
            ctx = file_ctx(args.root)
            mode = "FILE(fallback:auth)"
            print("[mode=%s]" % mode, file=sys.stderr)
            rc = args.func(args, ctx)
        else:
            raise
    # Propagate op_server's exit code (0 running / 1 down / 1 launch failure).
    # Without this the return value was dropped and even a failed `ensure`
    # silently exited 0 (found by grade_server_subcommand.py, 2026-10-29).
    if rc is not None:
        sys.exit(rc)


if __name__ == "__main__":
    main()
