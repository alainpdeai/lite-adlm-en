# -*- coding: utf-8 -*-
"""
P1-4 grader: archive/restore cross-file writes are transactional.

Every failure injection runs against an isolated data tree. The grader asserts
that a failed action leaves both files byte-for-byte (semantically) at their
pre-action state, that snapshots are not consumed, and that a retry cannot
produce a duplicate archived item.
"""
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (  # noqa: E402
    Checker, ROOT, copy_data_dir, http_at, run_instance, stop_instance, temp_dir,
)

NAME = "p1-archive-txn"
c = Checker(NAME)

json_out = None
if "--json" in sys.argv:
    i = sys.argv.index("--json")
    if i + 1 < len(sys.argv):
        json_out = sys.argv[i + 1]

LIST_ID = "probe_txn"
ADMIN = "user_admin"


def item(iid, done=True):
    return {
        "itemId": iid, "title": "P1 TXN " + iid, "isDone": done,
        "status": "done" if done else "open", "statusHistory": [],
        "blockedReason": "", "dueDate": "", "priority": "Medium",
        "assignedTo": "admin", "createdBy": "admin", "createdByAgent": "AI Agent",
        "createdById": ADMIN, "createdAt": "2026-11-01 00:00",
        "closedBy": "admin" if done else None, "closedById": ADMIN if done else None,
        "closedAt": "2026-11-01 00:00" if done else None,
        "localDirectory": "", "localDirectories": [], "comment": "", "subTasks": [],
    }


def make_fixture(data_dir):
    shared = os.path.join(data_dir, "shared_lists")
    os.makedirs(shared, exist_ok=True)
    doc = {"listId": LIST_ID, "listName": "P1 TXN", "category": "test",
           "items": [item("a1"), item("a2"), item("a3"), item("open1", False)]}
    with open(os.path.join(shared, LIST_ID + ".json"), "w", encoding="utf-8") as f:
        json.dump(doc, f)


def start(tag, env_extra=None, fixture=True):
    tmp = temp_dir(prefix="lt_p1_txn_%s_" % tag)
    data = copy_data_dir(os.path.join(tmp, "inst"))
    if fixture:
        make_fixture(data)
    logs = os.path.join(tmp, "logs")
    env = {"LITETASK_AUTO_ARCHIVE": "0", "LITETASK_BACKUP_MIRROR": "0",
           "LITETASK_LOG_DIR": logs,
           "LITETASK_AUDIT_FILE": os.path.join(logs, "audit.log")}
    env.update(env_extra or {})
    inst = run_instance(data, os.path.join(tmp, "backup"), env,
                        wait_after_ready=2.0, timeout=60, keep=True)
    return {"inst": inst, "tmp": tmp, "data": data,
            "base": "http://127.0.0.1:%d" % inst["port"],
            "logs": logs, "output": inst["output"]}


def active(ctx):
    st, doc = http_at(ctx["base"], "GET", "/api/lists/" + LIST_ID)
    return st, doc


def archived(ctx):
    st, doc = http_at(ctx["base"], "GET", "/api/archive/" + LIST_ID)
    return st, doc


def archive(ctx):
    return http_at(ctx["base"], "POST", "/api/lists/%s/archive" % LIST_ID,
                   {"userId": ADMIN, "confirm": True})


def restore(ctx, stamp):
    return http_at(ctx["base"], "POST", "/api/lists/%s/archive-restore" % LIST_ID,
                   {"userId": ADMIN, "confirm": True, "stamp": stamp})


def norm(doc):
    return json.dumps(doc, ensure_ascii=False, sort_keys=True)


def snapshots(ctx):
    st, doc = http_at(ctx["base"], "GET",
                      "/api/lists/%s/archive-snapshots?userId=%s" % (LIST_ID, ADMIN))
    return st, doc


def snapshot_files(ctx):
    d = os.path.join(ctx["data"], "archive-snapshots")
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.endswith(".snapshot.json"))


def txn_files(ctx):
    d = os.path.join(ctx["data"], "archive-snapshots")
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.endswith(".txn.json"))


ctxs = []
try:
    # ----------------------------------------------------- 1/2. success paths
    ctx = start("success")
    ctxs.append(ctx)
    a0 = active(ctx)[1]
    before_active = norm(a0)
    st, r = archive(ctx)
    c.check("archive succeeds and moves the closed items",
            st == 200 and r.get("moved") == 3, (st, r))
    st, adoc = archived(ctx)
    c.check("archive file now holds the three items",
            st == 200 and len(adoc.get("items") or []) == 3, (st, adoc))
    st, sa = snapshots(ctx)
    stamp = (sa.get("snapshots") or [{}])[0].get("stamp") if st == 200 else None
    st, rr = restore(ctx, stamp)
    c.check("restore succeeds and returns both files to the snapshot state",
            st == 200 and rr.get("restoredActive") == 4 and rr.get("restoredArchive") == 0, (st, rr))
    c.check("restored active list matches the pre-archive items",
            (active(ctx)[1].get("items") or []) == (a0.get("items") or []))

    # ------------------------------- 3. archive first write fails (dir replacement)
    ctx2 = start("firstfail")
    ctxs.append(ctx2)
    ap = os.path.join(ctx2["data"], "archive", LIST_ID + ".json")
    os.makedirs(os.path.dirname(ap), exist_ok=True)
    os.makedirs(ap, exist_ok=True)          # a directory where the archive file goes
    st, r = archive(ctx2)
    c.check("archive first-write failure returns 500 ARCHIVE_TXN_FAILED",
            st == 500 and r.get("code") == "ARCHIVE_TXN_FAILED", (st, r))
    c.check("first-write failure leaves the active list unchanged",
            norm(active(ctx2)[1]) == before_active)

    # ------------------------------ 4/6. restore second write fails via drill fault
    ctx3 = start("restorefail", {"LITETASK_DRILL_FAULT": "restore-archive-write"})
    ctxs.append(ctx3)
    st, r = archive(ctx3)
    st, sa = snapshots(ctx3)
    stamp = (sa.get("snapshots") or [{}])[0].get("stamp") if st == 200 else None
    active_before_restore = norm(active(ctx3)[1])
    archive_before_restore = norm(archived(ctx3)[1])
    snaps_before = snapshot_files(ctx3)
    st, r = restore(ctx3, stamp)
    c.check("restore second-write failure returns 500 ARCHIVE_TXN_FAILED",
            st == 500 and r.get("code") == "ARCHIVE_TXN_FAILED" and r.get("compensated") is True,
            (st, r))
    c.check("restore failure leaves the active list at its pre-restore state",
            norm(active(ctx3)[1]) == active_before_restore,
            (norm(active(ctx3)[1]) == active_before_restore))
    c.check("restore failure leaves the archive content unchanged",
            norm(archived(ctx3)[1]) == archive_before_restore)
    c.check("snapshot set is unchanged by the failed action", snapshot_files(ctx3) == snaps_before)

    # ---------------------------------- 5. archive second write fails via drill
    ctx4 = start("secondfail", {"LITETASK_DRILL_FAULT": "archive-list-write"})
    ctxs.append(ctx4)
    a_before = norm(active(ctx4)[1])
    ar_before = norm(archived(ctx4)[1])
    snaps_before = snapshot_files(ctx4)
    st, r = archive(ctx4)
    fail = st == 500 and r.get("code") == "ARCHIVE_TXN_FAILED" and r.get("compensated") is True
    sames = norm(active(ctx4)[1]) == a_before and norm(archived(ctx4)[1]) == ar_before
    c.check("archive second-write failure returns compensated 500 ARCHIVE_TXN_FAILED", fail, (st, r))
    c.check("archive second-write failure restores both files semantically", sames,
            (norm(active(ctx4)[1]) == a_before, norm(archived(ctx4)[1]) == ar_before))
    c.check("failed archive does not consume the snapshot quota",
            snapshot_files(ctx4) == snaps_before, (snapshot_files(ctx4), snaps_before))

    # --------------------------------------------------- 7. idempotent + retry
    ctx5 = start("retry")
    ctxs.append(ctx5)
    st1, r1 = archive(ctx5)
    st2, r2 = archive(ctx5)
    st, adoc = archived(ctx5)
    ids = [x.get("itemId") for x in (adoc.get("items") or [])]
    c.check("a second archive is a no-op and does not duplicate items",
            st1 == 200 and r1.get("moved") == 3 and r2.get("moved") == 0
            and sorted(ids) == ["a1", "a2", "a3"], (st1, r1, r2, ids))

    # ----------------------------------------- 8/9. compensation itself fails
    ctx6 = start("compfail", {"LITETASK_DRILL_FAULT": "archive-list-write,compensate"})
    ctxs.append(ctx6)
    # A pre-existing archive file makes compensation call restoreFile(), which is
    # where the `compensate` fault fires. Without it, rollback is a plain remove.
    ap6 = os.path.join(ctx6["data"], "archive", LIST_ID + ".json")
    os.makedirs(os.path.dirname(ap6), exist_ok=True)
    with open(ap6, "w", encoding="utf-8") as f:
        json.dump({"listId": LIST_ID, "listName": "P1 TXN", "items": [item("old1")]}, f)
    st, r = archive(ctx6)
    c.check("compensation failure returns ARCHIVE_TXN_MANUAL_RECOVERY",
            st == 500 and r.get("code") == "ARCHIVE_TXN_MANUAL_RECOVERY"
            and r.get("compensated") is False, (st, r))
    c.check("compensation failure keeps the transaction record",
            bool(txn_files(ctx6)), txn_files(ctx6))
    st, r2 = archive(ctx6)
    c.check("a pending transaction blocks the next archive with ARCHIVE_TXN_PENDING",
            st == 500 and r2.get("code") == "ARCHIVE_TXN_PENDING", (st, r2))
    audit = ""
    p = os.path.join(ctx6["logs"], "audit.log")
    if os.path.exists(p):
        audit = open(p, encoding="utf-8", errors="replace").read()
    c.check("failed archive is audited without credentials",
            '"outcome":"failed"' in audit and "ARCHIVE_TXN" in audit
            and "scrypt$" not in audit and "lt_session" not in audit, audit[-200:])

    # ------------------------------------------------ 10. crash + resync
    ctx7 = start("crash", {"LITETASK_DRILL_FAULT": "crash-after-first-write"})
    ctxs.append(ctx7)
    pre_active = norm(active(ctx7)[1])
    pre_archive = norm(archived(ctx7)[1])
    try:
        http_at(ctx7["base"], "POST", "/api/lists/%s/archive" % LIST_ID,
                {"userId": ADMIN, "confirm": True}, timeout=5)
    except Exception:                                              # noqa: BLE001
        pass
    time.sleep(0.8)
    stop_instance(ctx7["inst"]["proc"])
    restarted = run_instance(ctx7["data"], os.path.join(ctx7["tmp"], "backup2"), {
        "LITETASK_AUTO_ARCHIVE": "0", "LITETASK_BACKUP_MIRROR": "0",
        "LITETASK_LOG_DIR": ctx7["logs"],
        "LITETASK_AUDIT_FILE": os.path.join(ctx7["logs"], "audit.log"),
    }, wait_after_ready=2.0, timeout=60, keep=True)
    ctx7["inst"] = restarted
    ctx7["base"] = "http://127.0.0.1:%d" % restarted["port"]
    c.check("after a crash the restart rolls both files back",
            norm(active(ctx7)[1]) == pre_active and norm(archived(ctx7)[1]) == pre_archive,
            "files not restored")
    c.check("no transaction record survives recovery", txn_files(ctx7) == [], txn_files(ctx7))
finally:
    for ctx in ctxs:
        if ctx and ctx["inst"].get("proc"):
            stop_instance(ctx["inst"]["proc"])
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump({"grader": NAME, "result": "FAIL" if c.failed else "PASS",
                       "checks": c.passed + len(c.failed), "failures": c.failed},
                      f, ensure_ascii=False, indent=2)
    for ctx in ctxs:
        if ctx:
            shutil.rmtree(ctx["tmp"], ignore_errors=True)

c.finish()