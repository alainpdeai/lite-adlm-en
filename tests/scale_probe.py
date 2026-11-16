# -*- coding: utf-8 -*-
"""
Scale baseline probe (Capacity and Performance P2) — measures, never asserts.

Everything is read-modify-write over a whole JSON file, behind one lock per
list, with no pagination. The live lists hold tens of items, so nobody knows
where the knee is. This probe builds 1k and 5k item lists in a throwaway data
directory and times:

  * a full read (`GET /api/lists`) — what every client pays on load;
  * a one-item write (`PUT`) — what every edit pays, since the whole file is
    rewritten no matter how small the change;
  * the payload size, because that is what crosses the wire;
  * a client-side `JSON.parse` of that payload, run under node — the nearest
    available stand-in for the browser's own parse cost.

It prints a table and a JSON block; it never fails. `grade_scale_baseline.py`
is the file that asserts, and it reads this one's numbers rather than
hard-coding them, so the probe can grow without the grader drifting.

Honest limitation, stated here so it travels with the numbers: this measures
the server and the wire, NOT the browser's DOM render. Vue rendering N rows is
a cost this probe cannot see without a headless browser, and pretending
otherwise would be a fabricated baseline.
"""
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import ROOT, http_at, run_instance, stop_instance, temp_dir  # noqa: E402

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
SCALES = [1000, 5000]
READ_SAMPLES = 5
WRITE_SAMPLES = 3


def raw_get(base, path, timeout=120):
    """Return (elapsed_seconds, payload_bytes)."""
    req = urllib.request.Request(base + path)
    t0 = time.perf_counter()
    with _OPENER.open(req, timeout=timeout) as r:
        body = r.read()
    return time.perf_counter() - t0, len(body), body


def pct(xs, q):
    if not xs:
        return None
    s = sorted(xs)
    i = min(len(s) - 1, int(round((len(s) - 1) * q)))
    return s[i]


def summarize(xs):
    return {
        "p50_ms": round(pct(xs, 0.5) * 1000, 1),
        "p95_ms": round(pct(xs, 0.95) * 1000, 1),
        "max_ms": round(max(xs) * 1000, 1),
        "samples": len(xs),
    }


def make_items(n, start=0):
    return [{
        "itemId": "sc-%06d" % (start + i),
        "title": "scale probe item %d" % (start + i),
        "isDone": False, "status": "open", "statusHistory": [],
        "blockedReason": "", "dueDate": "", "priority": "Medium",
        "assignedTo": "admin", "createdBy": "admin",
        "createdByAgent": "AI Agent", "createdById": "user_admin",
        "createdAt": "2026-10-28 00:00", "closedBy": None,
        "closedById": None, "closedAt": None,
        "localDirectory": "", "localDirectories": [],
        "comment": "x" * 40, "subTasks": [],
    } for i in range(n)]


def client_parse_ms(payload_bytes, runs=3):
    """JSON.parse cost under node — the closest stand-in for the browser."""
    tmp = temp_dir(prefix="lt_parse_")
    f = os.path.join(tmp, "payload.json")
    try:
        with open(f, "wb") as fh:
            fh.write(payload_bytes)
        script = (
            "const fs=require('fs');const t=Date.now();"
            "const s=fs.readFileSync(%s,'utf8');JSON.parse(s);"
            "console.log(Date.now()-t);" % json.dumps(f)
        )
        xs = []
        for _ in range(runs):
            p = subprocess.run(["node", "-e", script], capture_output=True,
                               text=True, timeout=120)
            try:
                xs.append(float((p.stdout or "0").strip().splitlines()[-1]))
            except (ValueError, IndexError):
                pass
        return summarize_ms(xs)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def summarize_ms(xs):
    if not xs:
        return {"p50_ms": None, "p95_ms": None, "max_ms": None, "samples": 0}
    return {
        "p50_ms": round(pct(xs, 0.5), 1),
        "p95_ms": round(pct(xs, 0.95), 1),
        "max_ms": round(max(xs), 1),
        "samples": len(xs),
    }


def _bulk_write(base, lid, n):
    """Build n items and write them in one bulk PUT; return (items, bulk_s)."""
    items = make_items(n)
    t0 = time.perf_counter()
    st, _ = http_at(base, "PUT", "/api/lists/" + lid,
                    {"type": "UPDATE_ITEMS", "items": items,
                     "userId": "user_admin", "force": True},
                    timeout=180)
    bulk_s = time.perf_counter() - t0
    if st != 200:
        return None, st
    return items, bulk_s


def _sample_io(base, lid, items):
    """Sample full-list reads and a one-item write; return read/write stats."""
    reads = []
    payload_len = None
    payload = None
    for _ in range(READ_SAMPLES):
        el, ln, pl = raw_get(base, "/api/lists")
        reads.append(el)
        payload_len = ln
        payload = pl

    # a one-item edit: the whole file is rewritten regardless
    writes = []
    for k in range(WRITE_SAMPLES):
        edited = list(items)
        edited[0] = dict(edited[0], title="edited %d" % k)
        t0 = time.perf_counter()
        st, _ = http_at(base, "PUT", "/api/lists/" + lid,
                        {"type": "UPDATE_ITEMS", "items": edited,
                         "userId": "user_admin", "force": True},
                        timeout=180)
        writes.append(time.perf_counter() - t0)
        if st == 200:
            items = edited
    return reads, writes, payload, payload_len


def _probe_scale(base, n):
    """Build and measure one scale; return (rec, error_message_or_None)."""
    st, body = http_at(base, "POST", "/api/lists",
                       {"userId": "user_admin", "username": "admin",
                        "listName": "SCALE-%d" % n}, timeout=60)
    if st != 200 or not isinstance(body, dict):
        return None, "could not create probe list: %s %s" % (st, body)
    lid = body["listId"]

    items, bulk_s = _bulk_write(base, lid, n)
    if items is None:
        return None, "bulk write failed: %s" % bulk_s

    reads, writes, payload, payload_len = _sample_io(base, lid, items)
    rec = {
        "items": n,
        "bulk_write_s": round(bulk_s, 2),
        "read": summarize(reads),
        "write_one_item": summarize(writes),
        "payload_bytes": payload_len,
        "payload_kib": round((payload_len or 0) / 1024.0, 1),
        "client_parse": client_parse_ms(payload),
    }
    http_at(base, "DELETE", "/api/lists/%s?userId=user_admin" % lid,
            {"confirm": True}, timeout=60)
    return rec, None


def main():
    tmp = temp_dir(prefix="lt_scale_")
    data_dir = os.path.join(tmp, "data")
    shutil.copytree(os.path.join(ROOT, "data"), data_dir)
    inst = run_instance(data_dir, os.path.join(tmp, "backup"), {},
                        wait_after_ready=3.0, timeout=60, keep=True)
    base = "http://127.0.0.1:%d" % inst["port"]
    out = {"scales": [], "note": "server + wire + client parse; DOM render NOT measured"}
    try:
        if not inst["ready"]:
            print("instance did not come up:\n" + inst["output"][-800:])
            return 1

        for n in SCALES:
            rec, err = _probe_scale(base, n)
            if err:
                print(err)
                return 1
            out["scales"].append(rec)
    finally:
        stop_instance(inst["proc"])
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("%-8s %-10s %-10s %-12s %-12s %-10s" %
          ("items", "read p50", "read p95", "write1 p50", "payload", "parse p50"))
    for r in out["scales"]:
        print("%-8d %-10s %-10s %-12s %-12s %-10s" % (
            r["items"],
            "%sms" % r["read"]["p50_ms"],
            "%sms" % r["read"]["p95_ms"],
            "%sms" % r["write_one_item"]["p50_ms"],
            "%s KiB" % r["payload_kib"],
            "%sms" % (r["client_parse"]["p50_ms"] if r["client_parse"]["p50_ms"] is not None else "-"),
        ))
    print()
    print("JSON " + json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
