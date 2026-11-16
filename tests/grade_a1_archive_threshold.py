# -*- coding: utf-8 -*-
"""
Grader for the A1 auto-archive threshold risk (categories.json -> archive).

The risk this file exists for: the startup sweep archives *every* closed item of
a list once `closed >= minClosed`, and `buildLinkGraph()` only reads
data/shared_lists — so a list that crosses the threshold disappears from
/api/links, /api/trace and /api/gaps. With test.json holding 16 closed items
(and func.json 17), nine more closed items would have emptied the verification
record on the next restart.

The fix under test:

* categories.json -> archive.protected names the lists that are project records
  and are therefore never touched by the *startup sweep*.
* categories.json -> archive.minClosed / warnWithin make the policy declarative;
  LITETASK_AUTO_ARCHIVE_MIN_CLOSED and LITETASK_AUTO_ARCHIVE=0 still override.
* GET /api/archive-status exposes `wouldArchive`, the exact sweep predicate, so
  the decision can be checked without restarting the server.

Two halves:

A. Predicate, against the live server. Includes the real scenario: test.json is
   temporarily pushed over the threshold (snapshot -> inflate -> restore) and
   must still report wouldArchive=false.
B. A real sweep, against a throwaway `node server.js` started with
   LITETASK_DATA_DIR / LITETASK_BACKUP_DIR pointing at a *copy* of data/, so the
   startup sequence runs for real without touching the working data.

Nothing here edits server.js behaviour: it asserts the recorded answer.
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import (ADMIN_ID, ROOT, Checker, api, copy_data_dir,  # noqa: E402
                       count_files, create_temp_list, delete_temp_list,
                       fixture_preflight, get_list, http_at, put_items,
                       read_items_file, restore, run_instance, snapshot,
                       stop_instance, temp_dir, temp_item)

c = Checker("A1-threshold")

_fixture = fixture_preflight(os.path.join(ROOT, "data"), "test")
if _fixture in ("missing", "unparseable"):
    c.skip_all("delivery baseline lacks parseable test.json (%s)" % _fixture)
if _fixture == "unwritable":
    c.blocked("delivery data not writable: %s"
              % os.path.join(ROOT, "data", "shared_lists", "test.json"))

# Baseline, not an assumed-empty directory: a human archiving a list from the UI
# is a legitimate state, and this grader is about the threshold sweep, not about
# whether anyone has ever archived anything.
ARCHIVE_DIR = os.path.join(ROOT, "data", "archive")
ARCHIVE_BASELINE = sorted(os.listdir(ARCHIVE_DIR)) if os.path.isdir(ARCHIVE_DIR) else []


# ----------------------------------------------------------------- local bits
def status_row(doc, list_id):
    for l in (doc or {}).get("lists", []):
        if l.get("listId") == list_id:
            return l
    return None


# "Auto-archived 5 closed item(s) from probe_open (threshold 3)." -> probe_open
def swept_ids(output):
    import re
    return re.findall(r"Auto-archived \d+ closed item\(s\) from (\S+)", output)


def write_probe_list(data_dir, list_id, n_done, n_open=0):
    items = []
    for n in range(n_done):
        items.append(temp_item("%s-d%02d" % (list_id, n), title="probe closed",
                               status="done", isDone=True))
    for n in range(n_open):
        items.append(temp_item("%s-o%02d" % (list_id, n), title="probe open",
                               status="open"))
    doc = {
        "listId": list_id,
        "listName": "GRADE probe %s" % list_id,
        "items": items,
        "rev": "",
        "updatedAt": "2026-10-28T00:00:00.000Z",
    }
    with open(os.path.join(data_dir, "shared_lists", "%s.json" % list_id),
              "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


def ensure_closed_items(data_dir, list_id, n_closed):
    """Seed the private copy so a protected list has closed items to count.

    The delivery baseline ships an empty board; the assertions below are about
    sweep behaviour, not about how many items a real project happens to hold.
    """
    path = os.path.join(data_dir, "shared_lists", "%s.json" % list_id)
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    items = list(doc.get("items", []))
    closed = sum(1 for i in items
                 if i.get("isDone") is True or i.get("status") == "done")
    if closed < n_closed:
        for k in range(closed, n_closed):
            items.append(temp_item("%s-seed-%02d" % (list_id, k),
                                   title="baseline seed", status="done",
                                   isDone=True))
        doc["items"] = items
        doc["rev"] = ""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")


# =========================================================== A. live predicate
print("== policy comes from categories.json ==")
st, doc = api("GET", "/api/archive-status")
c.check("GET /api/archive-status answers 200", st == 200 and isinstance(doc, dict), (st, doc))
c.check("auto-archive is enabled", doc and doc.get("enabled") is True, doc and doc.get("enabled"))
c.check("threshold is 25, read from config",
        doc and doc.get("minClosed") == 25 and doc.get("thresholdSource") == "categories.json",
        doc and (doc.get("minClosed"), doc.get("thresholdSource")))
c.check("warnWithin is 5", doc and doc.get("warnWithin") == 5, doc and doc.get("warnWithin"))
c.check("the four project lists are protected",
        doc and set(["arch", "func", "test", "exam"]).issubset(set(doc.get("protected") or [])),
        doc and doc.get("protected"))

print()
print("== the four project lists would never be swept ==")
for lid in ["arch", "func", "test", "exam"]:
    row = status_row(doc, lid)
    c.check("%s is protected and wouldArchive=false" % lid,
            row and row.get("protected") is True and row.get("wouldArchive") is False, row)
    c.check("%s reports no distance to an archive it can never reach" % lid,
            row and row.get("untilArchive") is None, row and row.get("untilArchive"))

print()
print("== the risk scenario: a protected list pushed over the threshold ==")
# Testing architecture P1 (zero side effects): this probe runs against a PRIVATE COPY of
# data/, never against the working test.json. It used to inflate and restore the
# real list, which left test.json with a bumped updatedAt on every grading run —
# a metadata-only diff that buried real business changes, and exactly the
# "graders may only work on throwaway dirs and temp lists" rule this suite sets
# for itself. The predicate is unchanged; only the substrate moved.
rev_before = get_list("test")["rev"]
tmp_thr = temp_dir(prefix="lt_grade_threshold_")
inst_thr = None
try:
    d_thr = copy_data_dir(tmp_thr)
    b_thr = os.path.join(tmp_thr, "backup")
    tpath = os.path.join(d_thr, "shared_lists", "test.json")
    with open(tpath, encoding="utf-8") as f:
        tdoc = json.load(f)
    extra = [temp_item("thr-%02d" % n, title="threshold probe", status="done", isDone=True)
             for n in range(10)]
    tdoc["items"] = list(tdoc.get("items", [])) + extra
    with open(tpath, "w", encoding="utf-8") as f:
        json.dump(tdoc, f, ensure_ascii=False, indent=2)

    inst_thr = run_instance(d_thr, b_thr, {"LITETASK_AUTO_ARCHIVE_MIN_CLOSED": "3"},
                            wait_after_ready=1.5, keep=True)
    c.check("the threshold probe instance came up", inst_thr["ready"],
            inst_thr["output"][-300:])
    base_thr = "http://localhost:%d" % inst_thr["port"]
    st_thr, doc2 = http_at(base_thr, "GET", "/api/archive-status")
    c.check("the probe instance answers /api/archive-status",
            st_thr == 200 and isinstance(doc2, dict), (st_thr, doc2))
    row = status_row(doc2, "test")
    c.check("test.json really is over the threshold now (in the private copy)",
            row and row["closed"] >= row["threshold"], row and (row["closed"], row["threshold"]))
    c.check("a protected list over the threshold is still not auto-archived",
            row and row.get("protected") is True and row.get("wouldArchive") is False, row)
    c.check("protection is not reported as a distance", row and row.get("untilArchive") is None,
            row and row.get("untilArchive"))
finally:
    if inst_thr and inst_thr.get("proc"):
        stop_instance(inst_thr["proc"])
    shutil.rmtree(tmp_thr, ignore_errors=True)
c.check("the working test.json was never written to (rev unchanged)",
        get_list("test")["rev"] == rev_before,
        (get_list("test")["rev"], rev_before))

print()
print("== an unprotected list still follows the threshold ==")
LID = create_temp_list("GRADE-TEMP threshold")
try:
    put_items(LID, [temp_item("t1-%02d" % n, title="closed", status="done", isDone=True)
                    for n in range(25)])
    _, doc3 = api("GET", "/api/archive-status")
    row = status_row(doc3, LID)
    c.check("25 closed on an unprotected list -> wouldArchive", row and row.get("wouldArchive") is True, row)
    c.check("it is not protected", row and row.get("protected") is False, row)
    c.check("no warning once the threshold is reached", row and row.get("warning") is False, row)

    put_items(LID, [temp_item("t1-%02d" % n, title="closed", status="done", isDone=True)
                    for n in range(22)])
    _, doc4 = api("GET", "/api/archive-status")
    row = status_row(doc4, LID)
    c.check("22 closed -> not yet archived", row and row.get("wouldArchive") is False, row)
    c.check("22 closed -> 3 more until archive", row and row.get("untilArchive") == 3, row)
    c.check("22 closed -> inside the warning band", row and row.get("warning") is True, row)

    put_items(LID, [temp_item("t1-%02d" % n, title="closed", status="done", isDone=True)
                    for n in range(3)])
    _, doc5 = api("GET", "/api/archive-status")
    row = status_row(doc5, LID)
    c.check("3 closed -> no warning", row and row.get("warning") is False, row)
    c.check("3 closed -> 22 more until archive", row and row.get("untilArchive") == 22, row)
finally:
    delete_temp_list(LID)
c.check("temp list removed again", get_list(LID) is None, LID)


# ================================================== B. real sweep, hermetic dir
print()
print("== a real startup sweep, run against a private copy of data/ ==")
backup_before = count_files(os.path.join(ROOT, "backup"))
tmp_root = temp_dir(prefix="lt_grade_archive_")
try:
    data_dir = copy_data_dir(tmp_root)
    backup_dir = os.path.join(tmp_root, "backup")

    write_probe_list(data_dir, "probe_open", 5)
    write_probe_list(data_dir, "probe_near", 2)
    # A clean delivery baseline ships empty project lists. This half proves the
    # sweep *names* a protected list instead of archiving it, which needs closed
    # items in the private copy. Seed the copy only, never the working data.
    ensure_closed_items(data_dir, "test", 3)
    # The board's business counts evolve (new work lands on the test list over
    # time); assert properties, not last week's numbers (grade_lib rule 3).
    n_test_items = read_items_file(os.path.join(data_dir, "shared_lists", "test.json"))
    n_test = len(n_test_items)
    # The sweep counts CLOSED items; the file holds closed + open. Both numbers
    # are needed and neither is a constant of nature, so both are derived here.
    n_test_closed = sum(1 for i in n_test_items
                        if i.get("isDone") is True or i.get("status") == "done")

    run1 = run_instance(data_dir, backup_dir, {"LITETASK_AUTO_ARCHIVE_MIN_CLOSED": "3"})
    c.check("the throwaway instance came up", run1["ready"], run1["output"][-300:])
    c.check("it swept the unprotected 5-item list",
            "Auto-archived 5 closed item(s) from probe_open" in run1["output"],
            run1["output"][-400:])
    c.check("it left the 2-item list alone (warned, not swept)",
            "probe_near" not in swept_ids(run1["output"]), swept_ids(run1["output"]))
    c.check("it warned about the list inside the warning band",
            "probe_near: 2 closed item(s)" in run1["output"] and "more will trigger" in run1["output"],
            [l for l in run1["output"].splitlines() if "probe_near" in l])
    c.check("it named test.json as protected, not archived",
            ("test: %d closed item(s) at or over threshold 3" % n_test_closed) in run1["output"]
            and "protected in categories.json, not auto-archived" in run1["output"],
            [l for l in run1["output"].splitlines() if "test:" in l or "protected in" in l])
    swept = swept_ids(run1["output"])
    overlap = sorted(set(swept) & set(["arch", "func", "test", "exam"]))
    c.check("no project list was swept", not overlap, (swept, overlap))

    c.check("the swept list file is empty on disk",
            read_items_file(os.path.join(data_dir, "shared_lists", "probe_open.json")) == [],
            read_items_file(os.path.join(data_dir, "shared_lists", "probe_open.json")))
    archived = read_items_file(os.path.join(data_dir, "archive", "probe_open.json"))
    c.check("its 5 items landed in the archive", len(archived) == 5, len(archived))
    c.check("they are stamped with archivedFrom",
            all(i.get("archivedFrom") == "probe_open" for i in archived), archived[:1])
    c.check("test.json still holds all its items in the swept copy",
            len(read_items_file(os.path.join(data_dir, "shared_lists", "test.json"))) == n_test,
            len(read_items_file(os.path.join(data_dir, "shared_lists", "test.json"))))
    c.check("no archive file was created for test.json",
            not os.path.exists(os.path.join(data_dir, "archive", "test.json")), None)
    c.check("the startup backup went to the private backup dir",
            os.path.isdir(backup_dir) and count_files(backup_dir) > 0, backup_dir)
    c.check("the real backup/ was not touched by the throwaway instance",
            count_files(os.path.join(ROOT, "backup")) == backup_before,
            (count_files(os.path.join(ROOT, "backup")), backup_before))

    print()
    print("== env still wins: LITETASK_AUTO_ARCHIVE=0 disables the sweep ==")
    tmp_root2 = temp_dir(prefix="lt_grade_archive_off_")
    try:
        data_dir2 = copy_data_dir(tmp_root2)
        backup_dir2 = os.path.join(tmp_root2, "backup")
        write_probe_list(data_dir2, "probe_open", 5)
        run2 = run_instance(data_dir2, backup_dir2,
                            {"LITETASK_AUTO_ARCHIVE_MIN_CLOSED": "3", "LITETASK_AUTO_ARCHIVE": "0"})
        c.check("the instance reports the sweep as disabled",
                "Auto-archive disabled" in run2["output"], run2["output"][-300:])
        c.check("nothing was archived", "Auto-archived" not in run2["output"],
                [l for l in run2["output"].splitlines() if "Auto-archived" in l])
        c.check("the 5 items are still in the list file",
                len(read_items_file(os.path.join(data_dir2, "shared_lists", "probe_open.json"))) == 5,
                len(read_items_file(os.path.join(data_dir2, "shared_lists", "probe_open.json"))))
    finally:
        shutil.rmtree(tmp_root2, ignore_errors=True)

    print()
    print("== protection blocks the sweep, not the manual archive ==")
    tmp_root3 = temp_dir(prefix="lt_grade_manual_")
    run3 = None
    try:
        data_dir3 = copy_data_dir(tmp_root3)
        backup_dir3 = os.path.join(tmp_root3, "backup")
        # keep=True: the instance has to be alive to answer the manual request
        run3 = run_instance(data_dir3, backup_dir3, {"LITETASK_AUTO_ARCHIVE": "0"},
                            wait_after_ready=1.5, keep=True)
        base = "http://localhost:%d" % run3["port"]
        items3 = read_items_file(os.path.join(data_dir3, "shared_lists", "test.json"))
        # The property under test is "a protected list can still be archived by
        # hand", not "every item in test.json happens to be closed today". Two
        # open entries were added to that list later (DOM baseline / probe isolation, both
        # blocked), and counting *all* items here would re-assert yesterday's
        # data — precisely what grader rule 3 forbids. Count the closed ones.
        closed3 = sum(1 for i in items3
                      if i.get("isDone") is True or i.get("status") == "done")
        open3 = len(items3) - closed3
        st3, body3 = http_at(base, "POST", "/api/lists/test/archive",
                          {"userId": ADMIN_ID, "confirm": True})
        c.check("manual archive of a protected list is still allowed",
                st3 == 200 and isinstance(body3, dict) and body3.get("moved") == closed3,
                (st3, body3, closed3))
        c.check("the manual archive really moved the protected list's closed items",
                len(read_items_file(os.path.join(data_dir3, "shared_lists", "test.json"))) == open3,
                (len(read_items_file(os.path.join(data_dir3, "shared_lists", "test.json"))), open3))
    finally:
        if run3 and run3.get("proc"):
            stop_instance(run3["proc"])
        shutil.rmtree(tmp_root3, ignore_errors=True)
finally:
    shutil.rmtree(tmp_root, ignore_errors=True)

print()
print("== the working data is exactly as it was ==")
st, doc6 = api("GET", "/api/archive-status")
c.check("no project list is over the threshold in the working data",
        all(status_row(doc6, l) and status_row(doc6, l)["wouldArchive"] is False
            for l in ["arch", "func", "test", "exam"]),
        [(l, status_row(doc6, l)) for l in ["arch", "func", "test", "exam"]])
# A human may legitimately archive a list from the UI — that is what archiving
# is for — so "data/archive is empty" is a fact about today, not a property.
# Compare against a baseline captured before this grader ran anything.
_archive_dir = os.path.join(ROOT, "data", "archive")
_archive_now = sorted(os.listdir(_archive_dir)) if os.path.isdir(_archive_dir) else []
c.check("the working archive dir is unchanged by the experiment",
        _archive_now == ARCHIVE_BASELINE, (ARCHIVE_BASELINE, _archive_now))

c.finish()
