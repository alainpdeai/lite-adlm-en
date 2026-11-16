"""Stale snapshot: When the instance is stopped, edits to JSON are never notified to the browser.

The iron rule is "Stop instance -> Edit JSON -> Restart instance". However, chokidar only
listens for file events while the process is alive, so modifications made during downtime
NEVER trigger io.emit('file-changed'). An open browser therefore holds onto the pre-shutdown
snapshot indefinitely: tasks closed on disk remain rendered as open on the client.

The fix under test: The server sends a `resync` event to that specific socket whenever a new
connection is established, so any client reconnecting after a restart pulls fresh state.

The grader uses engine.io polling transport (pure HTTP, no socket.io client library needed)
acting as a real client. One pitfall must be avoided: when a client aborts a long-poll via
timeout, the session terminates, and subsequent polls return HTTPError — while "session dead"
and "no events" both appear as no received data. Without distinguishing them, negative
assertions would falsely pass. Thus raw() separates timeout / error / data, and negative
assertions hold only on timeout (session is alive, simply idle).

Assertions test properties rather than counts:
1. Newly connected clients receive `resync`
2. Real file edits still broadcast `file-changed` to connected clients
   — Contrast: proves events actually deliver, making subsequent silence assertions meaningful
3. `resync` is one-shot, not continuous spam
4. Each new connection receives it independently (not only once globally)
5. Existing connected clients are not forced to refetch when others connect (no broadcast storm)
6. Frontend listens for `resync` and refetches — an unhandled event equals no change
"""

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import (ROOT, Checker, copy_data_dir,  # noqa: E402
                       run_instance, stop_instance, temp_dir)

# Same offline stance as grade_lib: never let a machine-wide proxy eat a
# loopback request.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

TIMEOUT = "timeout"      # session alive, nothing to say
ERROR = "error"          # session dead / transport failed -- NOT evidence of silence


def raw(path_base, sid=None, body=None, timeout=6.0):
    """One engine.io polling round-trip -> (kind, body)."""
    if sid:
        path = "/socket.io/?EIO=4&transport=polling&sid=" + sid
    else:
        path = "/socket.io/?EIO=4&transport=polling"
    data = body.encode("utf-8") if body is not None else None
    req = urllib.request.Request(path_base + path, data=data,
                                 method="POST" if data else "GET")
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return "data", r.read().decode("utf-8", "replace")
    except (socket.timeout, TimeoutError):
        return TIMEOUT, None
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            return TIMEOUT, None
        return ERROR, str(e)
    except Exception as e:                                      # noqa: BLE001
        return ERROR, str(e)


def join(base):
    """Open an engine.io session and connect to the default namespace."""
    kind, body = raw(base)
    if kind != "data" or not (body or "").startswith("0"):
        return None
    try:
        sid = json.loads(body[1:])["sid"]
    except (ValueError, KeyError):
        return None
    raw(base, sid, body="40")
    return sid


def events(body):
    """Event names inside an engine.io payload ('42["name",...]', RS-separated)."""
    names = []
    for part in (body or "").split("\x1e"):
        if part.startswith("42"):
            try:
                names.append(json.loads(part[2:])[0])
            except (ValueError, IndexError, TypeError):
                pass
    return names


def poll(base, sid, timeout=6.0):
    return raw(base, sid, timeout=timeout)


c = Checker("resync-on-connect")

root = temp_dir(prefix="lt_grade_resync_")
inst = None
try:
    data_dir = copy_data_dir(root)
    backup_dir = os.path.join(root, "backup")
    inst = run_instance(data_dir, backup_dir, {}, wait_after_ready=3.0, keep=True)
    base = "http://127.0.0.1:%d" % inst["port"]
    c.check("throwaway instance came up", inst["ready"], inst["output"][-200:])

    # --- 1. a client that has just connected is told to resync -------------
    a = join(base)
    c.check("a client can join the socket namespace", bool(a), a)
    if a:
        kind, body = poll(base, a)
        got = events(body)
        c.check("a freshly connected client receives a resync signal "
                "(this is what rescues a browser that survived a restart)",
                kind == "data" and "resync" in got, (kind, got or body))

        # --- 2. reverse control: real file changes still broadcast ---------
        probe = os.path.join(data_dir, "shared_lists", "resync_probe.json")
        with open(probe, "w", encoding="utf-8") as f:
            json.dump({"listId": "resync_probe", "items": [], "rev": "probe"}, f)
        time.sleep(1.2)
        kind, body = poll(base, a)
        c.check("a real file change still broadcasts file-changed to an "
                "already-connected client (events do reach this client, so the "
                "silence checked below means something)",
                kind == "data" and "file-changed" in events(body),
                (kind, events(body) or body))

        # --- 3. the resync is one-shot, not a repeating flood --------------
        kind, body = poll(base, a, timeout=3.0)
        c.check("the resync is sent once, not repeatedly "
                "(timeout = session still alive and silent; an errored session "
                "would prove nothing)",
                kind == TIMEOUT, (kind, events(body) or body))

    # --- 4/5. per-connection, and scoped to the connecting socket ----------
    d = join(base)
    c.check("a second client can join too", bool(d), d)
    if d:
        kind, body = poll(base, d)
        c.check("the second client gets its own resync (per-connection, "
                "not a one-off that only the first client ever saw)",
                kind == "data" and "resync" in events(body),
                (kind, events(body) or body))

        e = join(base)          # server pushes resync to E, and only to E
        c.check("a third client can join too", bool(e), e)
        if e:
            kind, body = poll(base, d, timeout=3.0)
            c.check("an already-connected client is NOT told to resync when "
                    "somebody else connects (no refetch storm every time a "
                    "browser tab opens)",
                    kind == TIMEOUT, (kind, events(body) or body))
            kind, body = poll(base, e)
            c.check("the newly connected client still gets its resync",
                    kind == "data" and "resync" in events(body),
                    (kind, events(body) or body))

    # --- 6. the frontend actually listens ----------------------------------
    html = open(os.path.join(ROOT, "public", "index.html"),
                encoding="utf-8").read()
    lines = html.splitlines()
    hit = None
    for n, line in enumerate(lines):
        if "socket.on('resync'" in line or 'socket.on("resync"' in line:
            hit = (n, line.strip(), "\n".join(lines[n:n + 3]))
            break
    c.check("the frontend listens for the resync event", bool(hit),
            [l.strip() for l in lines if "resync" in l][:2])
    c.check("and the handler refetches, so the event is not a no-op",
            bool(hit) and "fetchLists(" in hit[2], (hit[1][:90] if hit else None))
finally:
    if inst:
        try:
            stop_instance(inst["proc"])
        except Exception:                                       # noqa: BLE001
            pass

c.finish()
