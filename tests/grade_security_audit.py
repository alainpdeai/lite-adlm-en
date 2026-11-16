# -*- coding: utf-8 -*-
"""
Grader: destructive/privileged operations are audited, and the audit never
leaks credentials (Security Boundary P2-A).

`server.js` already had an access log, but it records *requests* (method, url,
status, ms). What the 2026-10-29 review asked for is a record of *who changed
what*: archiving a list, rolling one back, overwriting a whole list, deleting a
list or a user. Without it, the 23 items that vanished from `arch` had no trail
at all — the recovery had to be reconstructed from git by hand.

Two constraints shape this grader, both from the acceptance text:

1. The audit must not live inside the project. Inside data/ it would be swept
   into the startup backup; inside the repo root it would show up in git. So the
   file must sit outside the work tree — asserted here as a property, not as a
   hard-coded path, because the location is configurable.
2. It must never record credentials. Bodies in this system carry `password` and
   `newPassword`, and an audit that serialises whatever it was handed would turn
   a safety feature into a secret dump. This is tested by *planting* a sentinel
   password in a request body and asserting it does not appear anywhere in the
   audit — an assertion with teeth, since a naive implementation fails it.

Contrast cases keep the assertions honest:

  * plain reads must NOT be audited (this is an action log, not an access log);
  * a planted credential must also not leak into the audit through a
    non-audited route, proving the redaction is not merely "field absent".
"""
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import ROOT, Checker, http_at, run_instance, stop_instance, temp_dir  # noqa: E402

c = Checker("security-audit")

SENTINEL = "SENTINEL-PW-7f3a91"   # planted credential that must never be logged


def audit_lines(path):
    # A missing path is a FAILed assertion earlier in this file, not a crash:
    # a grader that raises reports nothing about the property under test.
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="replace") as f:
        return [l for l in f.read().splitlines() if l.strip()]


def parsed(path):
    out = []
    for l in audit_lines(path):
        try:
            out.append(json.loads(l))
        except ValueError:
            pass
    return out


def _check_health_and_location(c, base, log_dir):
    """§1: the audit lives, and lives OUTSIDE the work tree."""
    st, health = http_at(base, "GET", "/api/health", timeout=10)
    c.check("/api/health answers 200", st == 200, (st, health))
    aud = (health or {}).get("audit") or {}
    audit_file = aud.get("file")
    c.check("health reports an audit file path", bool(audit_file), aud)
    if audit_file:
        norm = os.path.normcase(os.path.abspath(audit_file))
        root_norm = os.path.normcase(os.path.abspath(ROOT))
        c.check("the audit file is OUTSIDE the project work tree (it must "
                "not be swept into git or into the startup backup)",
                not norm.startswith(root_norm), (audit_file, ROOT))
        c.check("the audit file is the one under the configured log dir",
                norm.startswith(os.path.normcase(os.path.abspath(log_dir))),
                (audit_file, log_dir))
    return audit_file


def _check_archive_action(c, base, audit_file):
    """§2: archiving a list writes a named, attributable audit entry."""
    st, body = http_at(base, "POST", "/api/lists",
                       {"userId": "user_admin", "username": "admin",
                        "listName": "AUDIT-TEMP"})
    c.check("temp list created", st == 200 and isinstance(body, dict), (st, body))
    lid = body["listId"] if isinstance(body, dict) else None

    items = [{
        "itemId": "aud-%02d" % n, "title": "audit probe %d" % n,
        "isDone": True, "status": "done", "statusHistory": [],
        "blockedReason": "", "dueDate": "", "priority": "Medium",
        "assignedTo": "admin", "createdBy": "admin",
        "createdByAgent": "AI Agent", "createdById": "user_admin",
        "createdAt": "2026-10-28 00:00", "closedBy": "admin",
        "closedById": "user_admin", "closedAt": "2026-10-28 01:00",
        "localDirectory": "", "localDirectories": [], "comment": "",
        "subTasks": [],
    } for n in range(3)]
    st, _ = http_at(base, "PUT", "/api/lists/" + lid,
                    {"type": "UPDATE_ITEMS", "items": items,
                     "userId": "user_admin", "force": True})
    c.check("probe items written", st == 200, st)

    before = len(parsed(audit_file)) if audit_file else 0

    st, ar = http_at(base, "POST", "/api/lists/%s/archive" % lid,
                     {"userId": "user_admin", "confirm": True})
    c.check("archive succeeded", st == 200, (st, ar))

    entries = parsed(audit_file) if audit_file else []
    c.check("the archive wrote at least one audit entry",
            len(entries) > before, (before, len(entries)))

    arch = [e for e in entries if e.get("action") == "archive"]
    c.check("an audit entry names the action 'archive'", bool(arch),
            [e.get("action") for e in entries])
    if arch:
        e = arch[-1]
        c.check("it records which list was archived", e.get("listId") == lid,
                (e.get("listId"), lid))
        c.check("it records who did it (actor is non-empty)",
                bool(e.get("actor")), e.get("actor"))
        c.check("it records when (parseable timestamp)",
                bool(e.get("ts")), e.get("ts"))
    return lid


def _check_reads_not_audited(c, base, audit_file):
    """Contrast: a plain read is an access log event, not an audit action."""
    n_after_archive = len(parsed(audit_file))
    for _ in range(3):
        http_at(base, "GET", "/api/lists", timeout=10)
        http_at(base, "GET", "/api/health", timeout=10)
    c.check("plain reads add no audit entries (this is an action log, not "
            "an access log)",
            len(parsed(audit_file)) == n_after_archive,
            (n_after_archive, len(parsed(audit_file))))


def _check_credential_redaction(c, base, lid, audit_file, log_dir):
    """§3: a planted credential must not leak into audit or access logs."""
    http_at(base, "POST", "/api/lists/%s/archive" % lid,
            {"userId": "user_admin", "confirm": True,
             "password": SENTINEL, "newPassword": SENTINEL, "token": SENTINEL})
    http_at(base, "POST", "/api/login",
            {"username": "admin", "password": SENTINEL})
    time.sleep(0.5)   # audit writes are serialised through a chain

    raw = "\n".join(audit_lines(audit_file)) if audit_file else ""
    c.check("the planted credential does not appear in the audit file",
            SENTINEL not in raw, raw[-300:])

    access = os.path.join(log_dir, "access.log")
    araw = ""
    if os.path.exists(access):
        with open(access, encoding="utf-8", errors="replace") as f:
            araw = f.read()
    c.check("the planted credential does not appear in the access log "
            "either", SENTINEL not in araw, "access.log")


def _check_audit_endpoint(c, base):
    """§4: an admin can read the audit back, and the redaction holds client-side."""
    st, al = http_at(base, "GET", "/api/audit?userId=user_admin", timeout=10)
    if st == 200 and isinstance(al, dict):
        rows = al.get("entries") or []
        c.check("GET /api/audit returns the recorded actions",
                any(r.get("action") == "archive" for r in rows),
                [r.get("action") for r in rows][:5])
        c.check("no audit entry handed to the client contains a credential",
                SENTINEL not in json.dumps(rows, ensure_ascii=False), "leak")
    else:
        c.check("GET /api/audit is available to an admin", False, (st, al))
        c.check("no audit entry handed to the client contains a credential",
                False, "endpoint missing")


def main():
    tmp = temp_dir(prefix="lt_audit_")
    log_dir = os.path.join(tmp, "logs")
    os.makedirs(log_dir, exist_ok=True)
    data_dir = os.path.join(tmp, "data")
    shutil.copytree(os.path.join(ROOT, "data"), data_dir)
    backup_dir = os.path.join(tmp, "backup")

    inst = run_instance(data_dir, backup_dir,
                        {"LITETASK_LOG_DIR": log_dir},
                        wait_after_ready=3.0, timeout=60, keep=True)
    base = "http://127.0.0.1:%d" % inst["port"]
    try:
        c.check("throwaway instance came up", inst["ready"],
                inst["output"][-400:])
        audit_file = _check_health_and_location(c, base, log_dir)
        lid = _check_archive_action(c, base, audit_file)
        _check_reads_not_audited(c, base, audit_file)
        _check_credential_redaction(c, base, lid, audit_file, log_dir)
        _check_audit_endpoint(c, base)
    finally:
        stop_instance(inst["proc"])
        shutil.rmtree(tmp, ignore_errors=True)

    c.finish()


if __name__ == "__main__":
    main()
