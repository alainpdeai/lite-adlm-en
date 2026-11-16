# -*- coding: utf-8 -*-
"""
Grader: destructive operations ask twice (Security Boundary P2-C).

Archiving moves items out of the list file into the archive. Rolling back to a
snapshot rewrites a whole list. A forced overwrite drops whatever the payload
does not carry. All three are one-click-to-lose-work operations, and the UI is
not the only caller: the CLI and the graders reach the same endpoints directly.

So the confirmation exists in two places, and both are graded:

1. The server refuses a destructive operation unless the caller says so
   affirmatively: `confirm: true` in the body, or `confirm=true` in the query
   (DELETE carries no body). HARD GATE since 2026-10-31 — an omitted field used
   to be read as "the UI already asked", which is indistinguishable from a
   script that never asked and simply left it out. That ambiguity was exactly
   the shape of the 2026-10-29 `arch` loss, so the field is now mandatory and
   every caller in this repository (CLI, UI, graders) was updated with it.
2. The UI asks before each of them. Asserted statically on
   public/index.html: a `confirm(` must sit between the decision and the fetch.

Four contrast cases keep the gate from being a rubber stamp:

  * `confirm: true` performs the operation — the gate is not a blanket refusal;
  * omitting `confirm` is REFUSED — this is the whole point of the hard gate;
  * a truthy-but-not-boolean `confirm: "yes"` is refused — `if (confirm)` would
    have let it through, `confirm === true` does not;
  * a NON-destructive write carrying `confirm: false` still succeeds — the gate
    must not spread to ordinary edits, or it becomes noise people click past.

The four gated operations: forced overwrite that drops items, archive,
archive-restore, and DELETE /api/lists/:id (which had no gate at all before
this change — the largest hole in the set).
"""
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import ROOT, Checker, http_at, run_instance, stop_instance, temp_dir  # noqa: E402

c = Checker("destructive-confirm")

INDEX = os.path.join(ROOT, "public", "index.html")


def item(iid, done=True):
    return {
        "itemId": iid, "title": "confirm probe " + iid,
        "isDone": done, "status": "done" if done else "open",
        "statusHistory": [], "blockedReason": "", "dueDate": "",
        "priority": "Medium", "assignedTo": "admin", "createdBy": "admin",
        "createdByAgent": "AI Agent", "createdById": "user_admin",
        "createdAt": "2026-10-28 00:00", "closedBy": "admin",
        "closedById": "user_admin", "closedAt": "2026-10-28 01:00",
        "localDirectory": "", "localDirectories": [], "comment": "",
        "subTasks": [],
    }


def confirm_before(html, fetch_fragment, window=25, exclude=()):
    """True when a confirm() sits within `window` lines above the fetch.

    `exclude` skips look-alike URLs: `/archive-preview`, `/archive-snapshots`
    and plain `/api/archive/:id` reads are not the destructive call, and a
    grader that matched one of those would be grading the wrong line.
    """
    lines = html.splitlines()
    for n, line in enumerate(lines):
        if fetch_fragment in line and not any(x in line for x in exclude):
            lo = max(0, n - window)
            if any("confirm(" in l for l in lines[lo:n]):
                return True, n + 1
    return False, None




def _check_archive_confirm_gate(base, lid):
    # ---- 1) archive ----------------------------------------------------
    st, body = http_at(base, "POST", "/api/lists/%s/archive" % lid,
                       {"userId": "user_admin", "confirm": False})
    c.check("archive with confirm:false is refused", st == 400, (st, body))
    c.check("the refusal names CONFIRMATION_REQUIRED",
            (body or {}).get("error") == "CONFIRMATION_REQUIRED", body)
    c.check("the refusal carries the machine-readable code too",
            (body or {}).get("code") == "CONFIRMATION_REQUIRED", body)
    c.check("nothing was archived by the refused request",
            len((http_at(base, "GET", "/api/lists")[1] or []) and
                [l for l in http_at(base, "GET", "/api/lists")[1]
                 if l.get("listId") == lid][0]["items"]) == 4,
            "list changed despite refusal")

    # Hard gate: the field must be *omitted-refused*, not omitted-allowed.
    st_o, body_o = http_at(base, "POST", "/api/lists/%s/archive" % lid,
                           {"userId": "user_admin"})
    c.check("archive with NO confirm field is refused (hard gate)",
            st_o == 400, (st_o, body_o))
    c.check("the omission refusal names CONFIRMATION_REQUIRED",
            (body_o or {}).get("error") == "CONFIRMATION_REQUIRED", body_o)

    # a truthy non-boolean must not sneak through an `if (confirm)` check
    st_y, body_y = http_at(base, "POST", "/api/lists/%s/archive" % lid,
                           {"userId": "user_admin", "confirm": "yes"})
    c.check("archive with confirm:'yes' is refused (strict === true)",
            st_y == 400, (st_y, body_y))

    # contrast: explicit confirmation performs it
    st, body = http_at(base, "POST", "/api/lists/%s/archive" % lid,
                       {"userId": "user_admin", "confirm": True})
    c.check("contrast: archive with confirm:true is performed", st == 200,
            (st, body))
    c.check("it really moved the items", (body or {}).get("moved") == 4, body)


def _check_archive_restore_gate(base, lid):
    # ---- 2) archive-restore -------------------------------------------
    st, snaps = http_at(base, "GET",
                        "/api/lists/%s/archive-snapshots?userId=user_admin" % lid,
                        timeout=10)
    c.check("snapshots are listed", st == 200 and isinstance(snaps, dict), (st, snaps))
    stamps = [s.get("stamp") for s in (snaps or {}).get("snapshots", [])]
    c.check("at least one snapshot exists to roll back to", bool(stamps), stamps)
    if stamps:
        st, body = http_at(base, "POST", "/api/lists/%s/archive-restore" % lid,
                           {"userId": "user_admin", "stamp": stamps[-1],
                            "confirm": False})
        c.check("archive-restore with confirm:false is refused", st == 400,
                (st, body))
        c.check("the refusal names CONFIRMATION_REQUIRED",
                (body or {}).get("error") == "CONFIRMATION_REQUIRED", body)
        st_o, body_o = http_at(base, "POST", "/api/lists/%s/archive-restore" % lid,
                               {"userId": "user_admin", "stamp": stamps[-1]})
        c.check("archive-restore with NO confirm field is refused (hard gate)",
                st_o == 400, (st_o, body_o))
        st, body = http_at(base, "POST", "/api/lists/%s/archive-restore" % lid,
                           {"userId": "user_admin", "stamp": stamps[-1],
                            "confirm": True})
        c.check("contrast: archive-restore with confirm:true is performed",
                st == 200, (st, body))


def _check_forced_overwrite_gate(base, lid):
    # ---- 3) forced overwrite that drops items --------------------------
    now = [l for l in http_at(base, "GET", "/api/lists")[1]
           if l.get("listId") == lid][0]["items"]
    c.check("the list holds items again after the restore", len(now) > 0, len(now))
    fewer = [i for i in now[:-2]]          # drops 2 existing items
    st, body = http_at(base, "PUT", "/api/lists/" + lid,
                       {"type": "UPDATE_ITEMS", "items": fewer,
                        "userId": "user_admin", "force": True,
                        "confirm": False})
    c.check("a forced overwrite that drops items is refused when "
            "confirm:false", st == 400, (st, body))
    c.check("the refusal names CONFIRMATION_REQUIRED",
            (body or {}).get("error") == "CONFIRMATION_REQUIRED", body)
    c.check("the refusal reports how many items would be dropped",
            (body or {}).get("removed") == 2, body)

    st_o, body_o = http_at(base, "PUT", "/api/lists/" + lid,
                          {"type": "UPDATE_ITEMS", "items": fewer,
                           "userId": "user_admin", "force": True})
    c.check("the same overwrite with NO confirm field is refused (hard gate)",
            st_o == 400, (st_o, body_o))

    st, body = http_at(base, "PUT", "/api/lists/" + lid,
                       {"type": "UPDATE_ITEMS", "items": fewer,
                        "userId": "user_admin", "force": True,
                        "confirm": True})
    c.check("contrast: the same overwrite with confirm:true is performed",
            st == 200, (st, body))
    return fewer


def _check_nondestructive_not_gated(base, lid, fewer):
    # ---- 4) the gate must not spread to ordinary edits -----------------
    keep = list(fewer) + [item("cf-new", done=False)]
    st, body = http_at(base, "PUT", "/api/lists/" + lid,
                       {"type": "UPDATE_ITEMS", "items": keep,
                        "userId": "user_admin", "confirm": False})
    c.check("contrast: a NON-destructive write with confirm:false still "
            "succeeds (the gate is for destructive operations only)",
            st == 200, (st, body))


def _check_delete_confirm_gate(base):
    # ---- 5) DELETE /api/lists/:id ---------------------------------------
    # Removing a list file removes every item in it. It is the most
    # destructive call in the API and until 2026-10-31 it had no gate at
    # all — not even the old "confirm: false" one. It is gated now, and
    # the gate is reachable from the query string because a DELETE carries
    # no body in the UI.
    st, b = http_at(base, "POST", "/api/lists",
                    {"userId": "user_admin", "username": "admin",
                     "listName": "CONFIRM-DEL"})
    c.check("second temp list created", st == 200 and isinstance(b, dict), (st, b))
    dlid = b["listId"]
    st, _ = http_at(base, "PUT", "/api/lists/" + dlid,
                    {"type": "UPDATE_ITEMS",
                     "items": [item("tmp-1"), item("tmp-2")],
                     "userId": "user_admin", "force": True, "confirm": True})
    c.check("two items written into the doomed list", st == 200, st)

    st, body = http_at(base, "DELETE",
                       "/api/lists/%s?userId=user_admin" % dlid)
    c.check("DELETE with no confirm is refused (hard gate)", st == 400, (st, body))
    c.check("the refusal names CONFIRMATION_REQUIRED",
            (body or {}).get("error") == "CONFIRMATION_REQUIRED", body)
    c.check("the refusal reports how many items the list holds",
            (body or {}).get("items") == 2, body)
    still = [l for l in (http_at(base, "GET", "/api/lists")[1] or [])
             if l.get("listId") == dlid]
    c.check("the list still exists after the refusal", len(still) == 1, still)

    st, body = http_at(base, "DELETE",
                       "/api/lists/%s?userId=user_admin&confirm=true" % dlid)
    c.check("contrast: DELETE with confirm=true (query string) is performed",
            st == 200, (st, body))
    gone = [l for l in (http_at(base, "GET", "/api/lists")[1] or [])
            if l.get("listId") == dlid]
    c.check("the list is really gone", gone == [], gone)


def _check_ui_confirmations():
    # ---- 5) the UI asks too -------------------------------------------------
    with open(INDEX, encoding="utf-8") as f:
        html = f.read()

    # The archive fetch ends with a backtick (it is a template literal), and
    # /archive-preview, /archive-snapshots and /api/archive/:id are not it.
    ok, ln = confirm_before(html, "/archive`", window=30,
                            exclude=("preview", "snapshots", "restore", "/api/archive/"))
    c.check("the archive action confirms with the user before it fires "
            "(confirm() between the decision and the fetch)", ok, ln)

    ok, ln = confirm_before(html, "/archive-restore", window=30)
    c.check("the snapshot-restore action confirms with the user before it fires",
            ok, ln)

    ok, ln = confirm_before(html, "saveItems(payload, true)", window=30)
    c.check("the whole-list overwrite (conflict resolution, force=true) "
            "confirms before it fires", ok, ln)

    c.check("the UI declares the confirmation to the server (confirm: true on "
            "the destructive calls)",
            html.count("confirm: true") >= 2,
            html.count("confirm: true"))

    # DELETE carries no body, so the UI's confirmation for it rides in the URL.
    ok, ln = confirm_before(html, "&confirm=true", window=8)
    c.check("the delete-list call carries confirm=true in the query string, "
            "right under its confirm()", ok, ln)


def main():
    tmp = temp_dir(prefix="lt_confirm_")
    data_dir = os.path.join(tmp, "data")
    shutil.copytree(os.path.join(ROOT, "data"), data_dir)
    inst = run_instance(data_dir, os.path.join(tmp, "backup"), {},
                        wait_after_ready=3.0, timeout=60, keep=True)
    base = "http://127.0.0.1:%d" % inst["port"]
    try:
        c.check("throwaway instance came up", inst["ready"], inst["output"][-300:])

        st, body = http_at(base, "POST", "/api/lists",
                           {"userId": "user_admin", "username": "admin",
                            "listName": "CONFIRM-TEMP"})
        c.check("temp list created", st == 200 and isinstance(body, dict), (st, body))
        lid = body["listId"]

        items = [item("cf-%02d" % n) for n in range(4)]
        st, _ = http_at(base, "PUT", "/api/lists/" + lid,
                        {"type": "UPDATE_ITEMS", "items": items,
                         "userId": "user_admin", "force": True})
        c.check("probe items written", st == 200, st)
        _check_archive_confirm_gate(base, lid)
        _check_archive_restore_gate(base, lid)
        fewer = _check_forced_overwrite_gate(base, lid)
        _check_nondestructive_not_gated(base, lid, fewer)
        _check_delete_confirm_gate(base)
    finally:
        stop_instance(inst["proc"])
        shutil.rmtree(tmp, ignore_errors=True)

    _check_ui_confirmations()
    c.finish()


if __name__ == "__main__":
    main()
