# Auto-generated
# -*- coding: utf-8 -*-
"""
Shared plumbing for the grader scripts.

A grader is not a unit test: it hard-codes the answer this project has recorded
for a verification item and exits non-zero the moment reality no longer matches.
`tests/exam_case_01_grade.py` established the pattern; every `grade_*.py` file
here follows it, and `tests/run_grade_checks.py` runs them all.

Three rules every grader in this directory obeys:

1. Snapshot, never assume empty. A restore that writes `[]` is a delete, and its
   own assertion will confirm the delete succeeded. Use snapshot()/restore() and
   assert on id sets.
2. Work on a throwaway list when the probe is destructive. create_temp_list()
   hands out a numbered list that delete_temp_list() removes again.
3. Assert the property under test, not yesterday's data state. Counts that were
   true last week belong in a comment, never in an assertion (see §24/§25 of
   references/system-guide.md).
"""
import copy
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import urllib.error

BASE = os.environ.get("LITETASK_BASE_URL", "http://localhost:3000")
ADMIN_ID = "user_admin"
# Repository root derived from this file, never welded to one machine.
# LITETASK_REPO (also honoured by scripts/precommit_grades.py) overrides it.
ROOT = os.environ.get("LITETASK_REPO") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------- http plumbing
def api(method, path, body=None, timeout=15, headers=None, cookie=None):
    """Return (status, parsed body). HTTP errors are returned, not raised.

    `headers` / `cookie` are optional and default to the historical behaviour
    (Content-Type only), so every existing caller keeps its exact signature.
    """
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    hdrs = dict(headers or {})
    if data:
        hdrs["Content-Type"] = "application/json"
    if cookie:
        hdrs["Cookie"] = cookie
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw) if raw else None
            except ValueError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw) if raw else None
        except ValueError:
            return e.code, raw
    except Exception as e:                                  # noqa: BLE001
        return 0, "transport error: %s" % e


def server_data_dir():
    """Data dir the live :3000 instance is actually serving.

    Graders used to hard-code an absolute repository path for disk assertions,
    which only matched when the live instance served that exact checkout. The
    live instance may serve a different copy (e.g. the user's real-app checkout),
    so disk assertions must target the directory the running server reports.
    """
    if server_data_dir._cache is None:
        st, body = api("GET", "/api/health")
        if st == 200 and isinstance(body, dict):
            dd = (body.get("dataDir") or {}).get("path")
            if dd:
                server_data_dir._cache = dd
        if server_data_dir._cache is None:
            server_data_dir._cache = os.path.join(ROOT, "data")
    return server_data_dir._cache
server_data_dir._cache = None


def server_shared_lists_dir():
    return os.path.join(server_data_dir(), "shared_lists")


def server_archive_dir():
    return os.path.join(server_data_dir(), "archive")


def get_list(lid):
    _, lists = api("GET", "/api/lists")
    for l in lists or []:
        if l.get("listId") == lid:
            return l
    return None


def get_items(lid):
    l = get_list(lid)
    return list(l["items"]) if l else []


def put_items(lid, items, rev=None, force=False, user=ADMIN_ID):
    payload = {"type": "UPDATE_ITEMS", "items": items, "userId": user}
    if rev:
        payload["baseRev"] = rev
    if force:
        payload["force"] = True
        # Security Boundary P2-C Hard Gate: a forced write that drops items needs an
        # affirmative confirm. Graders restore snapshots on purpose, so they
        # state it; the gate itself is graded in grade_destructive_confirm.py.
        payload["confirm"] = True
    return api("PUT", "/api/lists/" + lid, payload)


def snapshot(lid):
    """Deep copy of the current items — the only thing restore() should write."""
    return copy.deepcopy(get_items(lid))


def restore(lid, items):
    st, body = put_items(lid, items, force=True)
    after = [i["itemId"] for i in get_items(lid)]
    return st == 200 and after == [i["itemId"] for i in items], after, (st, body)


# ------------------------------------------------------------ throwaway lists
def create_temp_list(name="GRADE-TEMP"):
    st, body = api("POST", "/api/lists",
                   {"userId": ADMIN_ID, "username": "admin", "listName": name})
    if st != 200 or not isinstance(body, dict):
        raise RuntimeError("could not create temp list: %s %s" % (st, body))
    return body["listId"]


def delete_temp_list(lid):
    # Hard gate: deleting a list needs an affirmative confirm as well.
    api("DELETE", "/api/lists/%s?userId=%s" % (lid, ADMIN_ID), {"confirm": True})
    # the archive file a temp list may have produced is not removed by the API
    import os
    ap = "%s/data/archive/%s.json" % (ROOT, lid)
    if os.path.exists(ap):
        os.remove(ap)


def temp_item(item_id, status="open", **kw):
    """A minimal but complete item, so a temp entry never trips validation."""
    it = {
        "itemId": item_id, "title": kw.pop("title", "GRADE-TEMP item"),
        "isDone": kw.pop("isDone", False), "status": status,
        "statusHistory": [], "blockedReason": "", "dueDate": "",
        "priority": kw.pop("priority", "Medium"), "assignedTo": "admin",
        "createdBy": "admin", "createdByAgent": "AI Agent",
        "createdById": ADMIN_ID, "createdAt": "2026-10-28 00:00",
        "closedBy": None, "closedById": None, "closedAt": None,
        "localDirectory": kw.pop("localDirectory", ""),
        "localDirectories": kw.pop("localDirectories", []),
        "comment": kw.pop("comment", ""), "subTasks": [],
    }
    it.update(kw)
    return it


# ------------------------------------------------- throwaway server instances
# Startup behaviour (backup, auto-archive sweep, anything inside server.listen)
# can only be graded by actually starting a server — which would act on the real
# data. LITETASK_DATA_DIR / LITETASK_BACKUP_DIR relocate both trees, so an
# instance can run against a private copy. See §28 of references/system-guide.md.
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_at(base, method, path, body=None, timeout=10, headers=None, cookie=None):
    """Same contract as api(), but against an arbitrary base URL."""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    hdrs = dict(headers or {})
    if data:
        hdrs["Content-Type"] = "application/json"
    if cookie:
        hdrs["Cookie"] = cookie
    req = urllib.request.Request(base + path, data=data, method=method, headers=hdrs)
    try:
        with _NO_PROXY.open(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw) if raw else None
        except ValueError:
            return e.code, raw
    except Exception as e:                                      # noqa: BLE001
        return 0, "transport error: %s" % e


def http_at_headers(base, method, path, body=None, timeout=10, headers=None, cookie=None):
    """http_at(), plus the response headers, for Set-Cookie assertions."""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    hdrs = dict(headers or {})
    if data:
        hdrs["Content-Type"] = "application/json"
    if cookie:
        hdrs["Cookie"] = cookie
    req = urllib.request.Request(base + path, data=data, method=method, headers=hdrs)
    try:
        with _NO_PROXY.open(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw) if raw else None
            except ValueError:
                parsed = raw
            return r.status, parsed, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            body_out = json.loads(raw) if raw else None
        except ValueError:
            body_out = raw
        return e.code, body_out, dict(e.headers)
    except Exception as e:                                      # noqa: BLE001
        return 0, "transport error: %s" % e, {}


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def copy_data_dir(dst_root):
    """A private copy of data/ that a throwaway instance may write freely."""
    data_dir = os.path.join(dst_root, "data")
    shutil.copytree(os.path.join(ROOT, "data"), data_dir)
    return data_dir


def fixture_preflight(data_dir, list_id):
    """Read-only precondition probe for graders that need fixture data.

    Returns "missing" / "unparseable" / "unwritable" / None. It never creates
    or writes anything, so a grader can SKIP on an absent delivery baseline
    instead of reporting a false failure. A writable but still unsuitable
    fixture is NOT covered here: that stays a real FAIL.
    """
    path = os.path.join(data_dir, "shared_lists", list_id + ".json")
    if not os.path.isfile(path):
        return "missing"
    try:
        with open(path, encoding="utf-8") as fh:
            json.load(fh)
    except (OSError, ValueError):
        return "unparseable"
    if not os.access(path, os.W_OK):
        return "unwritable"
    return None


def run_instance(data_dir, backup_dir, env_extra, wait_after_ready=3.0,
                 timeout=40, keep=False):
    """Start `node server.js` against a copy of data/ and capture its stdout.

    With keep=True the process stays alive and is handed back in `proc`; the
    caller must stop_instance() it.
    """
    port = free_port()
    env = dict(os.environ)
    env.update({"PORT": str(port),
                "LITETASK_DATA_DIR": data_dir,
                "LITETASK_BACKUP_DIR": backup_dir})
    env.update(env_extra)

    proc = subprocess.Popen(
        ["node", "server.js"], cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1)
    lines = []

    def drain():
        try:
            for line in proc.stdout:
                lines.append(line.rstrip("\r\n"))
        except Exception:                                       # noqa: BLE001
            pass

    t = threading.Thread(target=drain, daemon=True)
    t.start()

    deadline = time.time() + timeout
    ready = False
    while time.time() < deadline:
        if any("Server running" in l for l in lines):
            ready = True
            break
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    time.sleep(wait_after_ready)      # backup + sweep run after listen()

    if keep:
        return {"port": port, "ready": ready, "output": "\n".join(lines),
                "proc": proc, "lines": lines, "thread": t}
    stop_instance(proc)
    t.join(timeout=5)
    return {"port": port, "ready": ready, "output": "\n".join(lines)}


def stop_instance(proc):
    try:
        proc.kill()
    except Exception:                                           # noqa: BLE001
        pass
    try:
        proc.wait(timeout=10)
    except Exception:                                           # noqa: BLE001
        pass


def read_items_file(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("items", [])


def count_files(root):
    n = 0
    for _dir, _sub, files in os.walk(root):
        n += len(files)
    return n


def temp_dir(prefix="lt_grade_"):
    return tempfile.mkdtemp(prefix=prefix)


# ------------------------------------------------------------------- assertions
class Checker:
    def __init__(self, name):
        self.name = name
        self.passed = 0
        self.failed = []
        self.retired_checks = []
        self.skipped_checks = []

    def skip(self, label, reason):
        self.skipped_checks.append((label, reason))
        print("  SKIP  %s   %s" % (label, reason))

    def blocked(self, reason):
        print()
        print("RESULT %s: BLOCKED (%s)" % (self.name, reason))
        sys.exit(3)

    def skip_all(self, reason):
        """SKIP the whole grader because a precondition is absent, not broken.

        Used for graders whose recorded claim depends on project history or a
        fixture layout that a clean delivery baseline deliberately does not
        carry (empty board, legacy junction). A SKIP is not a pass and not a
        failure: it must never turn the build red, and it must stay visible.
        """
        print()
        print("RESULT %s: SKIP (%s)" % (self.name, reason))
        sys.exit(0)

    def retired(self, label, reason):
        """Record an assertion that can no longer be re-derived, loudly.

        For the two cases where deleting the check would be a lie and keeping it
        would be a permanent false alarm: the evidence it depended on is gone for
        good, or an approved behaviour change moved the invariant somewhere else.
        A retired check prints, is listed again at the end, and counts as
        neither pass nor fail — it can never masquerade as a green one.
        """
        self.retired_checks.append((label, reason))
        print("  RETIRED  %s" % label)
        print("           reason: %s" % reason)

    def check(self, label, cond, detail=""):
        if cond:
            self.passed += 1
            print("  ok   %s" % label)
        else:
            self.failed.append(label)
            print("  FAIL %s   %s" % (label, detail))
        return bool(cond)

    def finish(self):
        print()
        if self.failed:
            print("RESULT %s: FAIL (%d of %d)" % (self.name, len(self.failed),
                                                  self.passed + len(self.failed)))
            for f in self.failed:
                print("   - " + f)
            sys.exit(1)
        print("RESULT %s: PASS (%d checks)" % (self.name, self.passed))
        if self.retired_checks:
            print("  (%d retired check(s), NOT counted as passing:)" % len(self.retired_checks))
            for label, _ in self.retired_checks:
                print("     - " + label)
        sys.exit(0)
