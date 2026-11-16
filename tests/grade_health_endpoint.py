# -*- coding: utf-8 -*-
"""
Grader: /api/health plus request logging with rotation.

Two P0 observability gaps, closed together because the second one only exists
to serve the first:

* There was no way to ask the running server what it thinks its own state is.
  Two "is the server down?" alarms (2026-10-29) were answered by hand, with
  `curl --noproxy '*'` and guesswork; one was a proxy artefact and one was a
  mistyped URL, and each cost ~15 minutes because nothing could be *read*.
* There was no request log at all, so even afterwards there was no record of
  what the server had actually served.

The contract under test:

    GET /api/health -> 200 {
        ok, startedAt, uptimeSec, pid, nodeVersion,
        dataDir: { path, readable },
        lists: [ { listId, items, rev } ],
        categories: { path, readable, parsable },
        backup: { dir, latestStamp, latestAt, ageSec },
        mode: { passwordless, devAutoLogin },
        log: { dir, file }
    }
    ... and a non-200 (503) with ok:false and a reason when the data tree is
    not usable, because a health endpoint that always answers 200 is not a
    health endpoint.

Everything destructive happens on a throwaway instance with a throwaway data
dir, backup dir and log dir. Three contrast cases prove the checks are not
tautologies: a corrupted categories.json must flip the answer to non-200, a
restored categories.json must flip it back, and adding an item must move the
reported count.
"""
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import (ROOT, Checker, copy_data_dir, http_at,  # noqa: E402
                       run_instance, stop_instance, temp_dir, temp_item)

c = Checker("health-endpoint")

STAMP_RE = re.compile(r"\.(\d{8}T\d{9}Z)\.json$")


def iso_parse(v):
    if not isinstance(v, str):
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


def newest_stamp(backup_dir):
    """Newest backup stamp, derived independently of the server's own answer."""
    best = None
    for dirpath, _, files in os.walk(backup_dir):
        for f in files:
            m = STAMP_RE.search(f)
            if m:
                if best is None or m.group(1) > best:
                    best = m.group(1)
    return best


tmp = temp_dir(prefix="lt_grade_health_")
inst = None
try:
    data_dir = copy_data_dir(tmp)
    backup_dir = os.path.join(tmp, "backup")
    log_dir = os.path.join(tmp, "logs")
    inst = run_instance(
        data_dir, backup_dir,
        {"LITETASK_AUTO_ARCHIVE": "0",
         "LITETASK_LOG_DIR": log_dir,
         "LITETASK_LOG_MAX_BYTES": "400",   # tiny, so rotation is reachable
         "LITETASK_LOG_KEEP": "2"},
        wait_after_ready=2.0, keep=True)
    c.check("the throwaway instance came up", inst["ready"], inst["output"][-300:])
    base = "http://localhost:%d" % inst["port"]

    # ---------------------------------------------------------------- basics
    st, h = http_at(base, "GET", "/api/health")
    c.check("GET /api/health answers 200", st == 200 and isinstance(h, dict),
            (st, str(h)[:200]))
    # Keep grading instead of crashing if the endpoint is missing or returns
    # HTML: every check below should report a failure, not raise AttributeError.
    if not isinstance(h, dict):
        h = {}
    c.check("it reports ok", h.get("ok") is True, h.get("ok"))
    c.check("health needs no credentials", st == 200, st)

    started = iso_parse(h.get("startedAt"))
    c.check("startedAt parses as a timestamp", started is not None, h.get("startedAt"))
    c.check("startedAt is not in the future",
            started and started <= datetime.now(timezone.utc), h.get("startedAt"))
    c.check("uptimeSec is a sane non-negative number",
            isinstance(h.get("uptimeSec"), (int, float)) and 0 <= h["uptimeSec"] < 3600,
            h.get("uptimeSec"))
    # The bug this catches (2026-10-29): uptimeSec divided the elapsed ms by
    # 10000 instead of 1000, so it read 10x too small and still passed the
    # "sane" range above. Cross-check it against startedAt + the local clock.
    if isinstance(h.get("uptimeSec"), (int, float)) and started:
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        c.check("uptimeSec agrees with startedAt to within a few seconds",
                abs(h["uptimeSec"] - elapsed) < 5, (h.get("uptimeSec"), elapsed))

    # A fresh instance cannot expose a scaling bug: at 4s of uptime a 10x error
    # is 3.6s and hides inside any sane tolerance. So wait until this instance
    # is at least 10s old, where a 10x error is 9s and cannot hide. Seen live on
    # the production server: 36 minutes of uptime reported as uptimeSec 218.
    import time as _time
    h2, started2 = h, started
    for _ in range(30):
        if started2 and (datetime.now(timezone.utc) - started2).total_seconds() >= 10:
            break
        _time.sleep(1)
        st2, h2 = http_at(base, "GET", "/api/health")
        started2 = iso_parse(h2.get("startedAt")) if isinstance(h2, dict) else None
    if isinstance(h2, dict) and isinstance(h2.get("uptimeSec"), (int, float)) and started2:
        elapsed2 = (datetime.now(timezone.utc) - started2).total_seconds()
        c.check("uptimeSec really is seconds (10s+ instance: a 10x error cannot hide)",
                elapsed2 >= 10 and abs(h2["uptimeSec"] - elapsed2) < 2,
                (h2.get("uptimeSec"), elapsed2))
    c.check("pid is a positive integer",
            isinstance(h.get("pid"), int) and h["pid"] > 0, h.get("pid"))
    c.check("nodeVersion looks like a node version",
            isinstance(h.get("nodeVersion"), str)
            and re.match(r"^v\d+\.\d+", h["nodeVersion"] or ""), h.get("nodeVersion"))

    # ------------------------------------------------------------- data tree
    dd = h.get("dataDir") or {}
    c.check("dataDir.path points at the instance's data dir",
            os.path.normcase(os.path.realpath(dd.get("path") or ""))
            == os.path.normcase(os.path.realpath(data_dir)), dd)
    c.check("dataDir.readable is true", dd.get("readable") is True, dd)

    ct = h.get("categories") or {}
    c.check("categories is readable and parsable",
            ct.get("readable") is True and ct.get("parsable") is True, ct)

    # ------------------------------------------------- lists: cross-checked
    lists = h.get("lists") or []
    c.check("lists is a non-empty array", isinstance(lists, list) and lists, lists[:2])
    c.check("every list entry carries listId, items and rev",
            all({"listId", "items", "rev"} <= set(x) for x in lists), lists[:2])

    _, live = http_at(base, "GET", "/api/lists")
    live_counts = {l["listId"]: len(l.get("items", [])) for l in live}
    health_counts = {x["listId"]: x["items"] for x in lists}
    c.check("item counts match /api/lists (not a hardcoded answer)",
            health_counts == live_counts, (health_counts, live_counts))

    # -------------------------------------------------------------- backups
    bk = h.get("backup") or {}
    c.check("backup.dir points at the instance's backup dir",
            os.path.normcase(os.path.realpath(bk.get("dir") or ""))
            == os.path.normcase(os.path.realpath(backup_dir)), bk)
    expected_stamp = newest_stamp(backup_dir)
    c.check("backup.latestStamp matches the newest file on disk",
            bk.get("latestStamp") == expected_stamp,
            (bk.get("latestStamp"), expected_stamp))
    c.check("backup.latestAt parses as a timestamp",
            iso_parse(bk.get("latestAt")) is not None, bk.get("latestAt"))
    c.check("backup.ageSec is a non-negative number",
            isinstance(bk.get("ageSec"), (int, float)) and bk["ageSec"] >= 0,
            bk.get("ageSec"))

    # ------------------------------------------------------------------ mode
    md = h.get("mode") or {}
    c.check("mode reports the login model in force",
            md.get("passwordless") is True and md.get("devAutoLogin") is True, md)

    # ------------------------------------------------------- request logging
    lg = h.get("log") or {}
    c.check("log.file lives under the configured log dir",
            (lg.get("file") or "").startswith(log_dir), lg)

    for _ in range(12):                       # enough to pass the 400-byte cap
        http_at(base, "GET", "/api/health")
    log_file = lg.get("file")
    c.check("the request log exists after traffic",
            log_file and os.path.exists(log_file) and os.path.getsize(log_file) > 0,
            log_file)
    body = ""
    if log_file and os.path.exists(log_file):
        body = open(log_file, encoding="utf-8", errors="replace").read()
    c.check("the log records the requests that were made",
            "GET /api/health" in body, body[:200])

    rotated = sorted(glob.glob(log_file + ".*")) if log_file else []
    c.check("rotation produced a numbered previous log", bool(rotated), rotated)
    c.check("rotation kept at most LITETASK_LOG_KEEP old files",
            len(rotated) <= 2, rotated)

    # ------------------------ contrast 1: corrupt categories.json -> non-200
    cat_path = os.path.join(data_dir, "categories.json")
    with open(cat_path, "rb") as fh:
        original = fh.read()
    with open(cat_path, "wb") as fh:
        fh.write(b"this is not json")
    st2, h2 = http_at(base, "GET", "/api/health")
    c.check("a corrupted categories.json makes health answer non-200",
            st2 != 200, (st2, str(h2)[:160]))
    c.check("and it says ok:false with a reason",
            h2.get("ok") is False and h2.get("reason"), h2)

    # --------------------- contrast 2: restore it -> healthy again (not sticky)
    with open(cat_path, "wb") as fh:
        fh.write(original)
    st3, h3 = http_at(base, "GET", "/api/health")
    c.check("restoring categories.json returns health to 200/ok",
            st3 == 200 and h3.get("ok") is True, (st3, str(h3)[:160]))

    # ---------------- contrast 3: adding an item moves the reported count
    _, live2 = http_at(base, "GET", "/api/lists")
    target = [l for l in live2 if l.get("listId") == "arch"][0]
    before = len(target["items"])
    new_items = list(target["items"]) + [temp_item("ghealth-1", title="health grader probe")]
    http_at(base, "PUT", "/api/lists/arch",
            {"type": "UPDATE_ITEMS", "items": new_items, "userId": "user_admin", "force": True})
    _, h4 = http_at(base, "GET", "/api/health")
    after = {x["listId"]: x["items"] for x in (h4.get("lists") or [])}.get("arch")
    c.check("adding an item raises the count health reports",
            after == before + 1, (before, after))
finally:
    if inst and inst.get("proc"):
        stop_instance(inst["proc"])

# ------------------- default log location must not be inside the project ----
tmp2 = temp_dir(prefix="lt_grade_health2_")
inst2 = None
try:
    d2 = copy_data_dir(tmp2)
    b2 = os.path.join(tmp2, "backup")
    inst2 = run_instance(d2, b2, {"LITETASK_AUTO_ARCHIVE": "0"},
                         wait_after_ready=2.0, keep=True)
    c.check("the second throwaway instance came up", inst2["ready"], inst2["output"][-200:])
    if inst2["ready"]:
        base2 = "http://localhost:%d" % inst2["port"]
        http_at(base2, "GET", "/api/health")
        _, h5 = http_at(base2, "GET", "/api/health")
        default_log_dir = (h5.get("log") or {}).get("dir")
        project_root = os.path.realpath(ROOT)
        c.check("the default log dir is outside the project tree",
                 bool(default_log_dir)
                 and not os.path.realpath(default_log_dir).startswith(project_root),
                 default_log_dir)
        c.check("the default log file was actually written",
                 os.path.exists((h5.get("log") or {}).get("file") or ""),
                 (h5.get("log") or {}).get("file"))
finally:
    if inst2 and inst2.get("proc"):
        stop_instance(inst2["proc"])
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(tmp2, ignore_errors=True)

c.finish()
