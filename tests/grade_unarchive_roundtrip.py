# -*- coding: utf-8 -*-
"""
Grader for the unarchive half of A1 (P1 backlog: archiving round-trip first step).

Why this file exists: on 2026-10-29 the archive button moved 17 closed items of
`arch` into data/archive/arch.json and there was **no way back**. `POST
/api/lists/:id/archive` is one-way: no endpoint, no CLI subcommand, no
round-trip guarantee. The 17 items were recovered by hand (git + per-item diff,
commit b780480) — a recovery path that only works because a human was watching.

The fix under test:

* POST /api/lists/:id/unarchive  — move archived items back into the active list
  (all of them, or exactly the ids named in `itemIds`), stripping
  archivedAt / archivedFrom / parentItemId / parentTitle, re-attaching archived
  subtasks to their parent, and recomputing rev.
* `litetask_cli.py unarchive` — the same operation from the CLI, in API mode and
  in file mode.
* The round-trip property: archive -> unarchive returns items field-for-field.

Everything runs against a throwaway `node server.js` on a private copy of data/
(grade_lib rule 2) with a private backup dir, so the working board is untouched;
the last section proves that by hashing the real data files before and after.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import (ADMIN_ID, ROOT, Checker, copy_data_dir,  # noqa: E402
                       http_at, read_items_file, run_instance,
                       stop_instance, temp_dir, temp_item)

c = Checker("unarchive-roundtrip")

CLI = os.path.join(ROOT, "scripts", "litetask_cli.py")
LID = "probe_unarch"
MARKERS = ("archivedAt", "archivedFrom", "parentItemId", "parentTitle")


# ----------------------------------------------------------------- local bits
def strip_markers(it):
    out = {k: v for k, v in it.items() if k not in MARKERS}
    if out.get("subTasks"):
        out["subTasks"] = [strip_markers(s) for s in out["subTasks"]]
    return out


def strip_deep(items):
    return [strip_markers(i) for i in items]


def canon_item(it):
    """Order-insensitive view of one item, markers dropped.

    The unarchive contract is content + structure, NOT order: restored entries
    are appended, because the archive records no position. Comparing raw lists
    would therefore assert a property the design deliberately does not promise
    (first RED run failed here on pu-parent alone).
    """
    out = {k: v for k, v in it.items() if k not in MARKERS and k != "subTasks"}
    out["subTasks"] = canon_items(it.get("subTasks") or [])
    return out


def canon_items(items):
    return sorted((canon_item(i) for i in items), key=lambda d: d["itemId"])


def has_markers(items):
    for it in items or []:
        if any(k in it for k in MARKERS):
            return True
        if has_markers(it.get("subTasks")):
            return True
    return False


def write_list(data_dir, list_id, items, list_name="GRADE probe unarchive"):
    doc = {"listId": list_id, "listName": list_name, "category": "test",
           "items": items, "rev": "", "updatedAt": "2026-10-28T00:00:00.000Z"}
    with open(os.path.join(data_dir, "shared_lists", "%s.json" % list_id),
              "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


def probe_items():
    sub_done = temp_item("pu-sub-done", title="probe subtask done",
                         status="done", isDone=True)
    sub_open = temp_item("pu-sub-open", title="probe subtask open", status="open")
    sub_nested = temp_item("pu-sub-nested", title="probe nested done",
                           status="done", isDone=True)
    return [
        temp_item("pu-done-top", title="probe done top", status="done", isDone=True),
        temp_item("pu-parent", title="probe parent open", status="open",
                  subTasks=[sub_done, sub_open]),
        temp_item("pu-subtree", title="probe closed subtree", status="done",
                  isDone=True, subTasks=[sub_nested]),
    ]


def ids_of(items):
    return sorted(i["itemId"] for i in items)


def as_dict(body):
    """A 404 from express (or a proxy) answers HTML, not JSON; never crash on it."""
    return body if isinstance(body, dict) else {}


def data_hashes():
    out = {}
    d = os.path.join(ROOT, "data")
    for rel in ("shared_lists/arch.json", "shared_lists/func.json",
                "shared_lists/test.json", "shared_lists/exam.json"):
        p = os.path.join(d, rel)
        if os.path.exists(p):
            with open(p, "rb") as f:
                out[rel] = hashlib.sha256(f.read()).hexdigest()
    ad = os.path.join(d, "archive")
    out["archive"] = sorted(os.listdir(ad)) if os.path.isdir(ad) else []
    return out


HASHES_BEFORE = data_hashes()

# ============================================ hermetic instance + round-trip
print("== a private instance: archive -> unarchive must round-trip ==")
tmp_root = temp_dir(prefix="lt_grade_unarch_")
run = None
try:
    data_dir = copy_data_dir(tmp_root)
    backup_dir = os.path.join(tmp_root, "backup")
    original = probe_items()
    write_list(data_dir, LID, original)
    lists_file = os.path.join(data_dir, "shared_lists", "%s.json" % LID)
    arc_file = os.path.join(data_dir, "archive", "%s.json" % LID)

    run = run_instance(data_dir, backup_dir, {"LITETASK_AUTO_ARCHIVE": "0"},
                       wait_after_ready=1.5, keep=True)
    base = "http://localhost:%d" % run["port"]
    c.check("the throwaway instance came up", run["ready"], run["output"][-300:])

    print()
    print("== the endpoint exists and is admin-guarded ==")
    st, body = http_at(base, "POST", "/api/lists/%s/unarchive" % LID,
                       {"userId": ADMIN_ID})
    c.check("POST /api/lists/:id/unarchive answers 200 on an empty archive",
            st == 200 and isinstance(body, dict), (st, body))
    c.check("it reports moved=0 when there is nothing to bring back",
            isinstance(body, dict) and as_dict(body).get("moved") == 0, body)
    st403, body403 = http_at(base, "POST", "/api/lists/%s/unarchive" % LID,
                             {"userId": "user_not_an_admin"})
    c.check("a non-admin is refused with 403", st403 == 403, (st403, body403))

    print()
    print("== archive, then bring everything back ==")
    st, ar = http_at(base, "POST", "/api/lists/%s/archive" % LID,
                   {"userId": ADMIN_ID, "confirm": True})
    # P1-2 whole-tree rule: only fully-closed top-level subtrees archive. The open
    # parent pu-parent keeps BOTH its subtasks (incl. the closed pu-sub-done), so
    # exactly 2 top-level subtrees move: pu-done-top and pu-subtree.
    c.check("the manual archive moved 2 fully-closed subtrees",
            st == 200 and as_dict(ar).get("moved") == 2, (st, ar))
    st, doc = http_at(base, "GET", "/api/archive/%s" % LID)
    archived = (doc or {}).get("items", [])
    c.check("the archive holds 2 entries", len(archived) == 2, len(archived))
    c.check("no subtask was split off its open parent (whole-tree rule)",
            sum(1 for i in archived if i.get("parentItemId")) == 0,
            [i.get("parentItemId") for i in archived])
    live_now = read_items_file(lists_file)
    c.check("the active list kept only the open parent", ids_of(live_now) == ["pu-parent"],
            ids_of(live_now))
    c.check("the parent kept BOTH its subtasks (open and closed, whole-tree rule)",
            set(ids_of(live_now[0].get("subTasks", []))) == {"pu-sub-done", "pu-sub-open"},
            ids_of(live_now[0].get("subTasks", [])))
    rev_archived = json.load(open(lists_file, encoding="utf-8")).get("rev")

    st400, b400 = http_at(base, "POST", "/api/lists/%s/unarchive" % LID,
                          {"userId": ADMIN_ID, "itemIds": ["pu-does-not-exist"]})
    c.check("an unknown id is refused with 400", st400 == 400, (st400, b400))
    c.check("nothing was restored by the refused call",
            len(read_items_file(lists_file)) == 1, len(read_items_file(lists_file)))

    print()
    print("== selective unarchive: only the ids that were named ==")
    st, b = http_at(base, "POST", "/api/lists/%s/unarchive" % LID,
                    {"userId": ADMIN_ID, "itemIds": ["pu-done-top"]})
    c.check("naming one id moves exactly one entry",
            st == 200 and as_dict(b).get("moved") == 1, (st, b))
    c.check("the rest stay in the archive", as_dict(b).get("archiveCount") == 1, b)
    ids = ids_of(read_items_file(lists_file))
    c.check("the named item is back in the active list", "pu-done-top" in ids, ids)

    print()
    print("== unarchive the remainder ==")
    st, b = http_at(base, "POST", "/api/lists/%s/unarchive" % LID, {"userId": ADMIN_ID})
    c.check("it moved the 1 remaining entry", st == 200 and as_dict(b).get("moved") == 1, (st, b))
    c.check("it re-attached 0 (pu-subtree came back whole with its child)",
            as_dict(b).get("reattached") == 0, b)
    c.check("nothing was orphaned", as_dict(b).get("orphaned") == 0, b)
    c.check("the archive is empty afterwards", as_dict(b).get("archiveCount") == 0, b)

    print()
    print("== the round-trip property ==")
    back = read_items_file(lists_file)
    c.check("every item is back, ids unchanged",
            ids_of(back) == ids_of(original), (ids_of(back), ids_of(original)))
    by_id = {i["itemId"]: i for i in back}
    parent = by_id.get("pu-parent", {})
    c.check("the archived subtask went back into its parent",
            ids_of(parent.get("subTasks", [])) == ["pu-sub-open", "pu-sub-done"]
            or ids_of(parent.get("subTasks", [])) == ["pu-sub-done", "pu-sub-open"],
            ids_of(parent.get("subTasks", [])))
    c.check("the parent still holds its own open subtask",
            "pu-sub-open" in ids_of(parent.get("subTasks", [])),
            ids_of(parent.get("subTasks", [])))
    subtree = by_id.get("pu-subtree", {})
    c.check("a closed subtree came back with its child intact",
            ids_of(subtree.get("subTasks", [])) == ["pu-sub-nested"],
            ids_of(subtree.get("subTasks", [])))
    c.check("no archive marker survived anywhere in the list",
            not has_markers(back), [i for i in back if any(k in i for k in MARKERS)])
    c.check("each restored item is field-for-field the original (order aside)",
            canon_items(back) == canon_items(original),
            [i["itemId"] for i in back if canon_item(i) not in canon_items(original)])
    c.check("restored top-level entries are appended after the untouched ones",
            [i["itemId"] for i in back][0] == "pu-parent"
            and ids_of(back[1:]) == ["pu-done-top", "pu-subtree"],
            [i["itemId"] for i in back])
    st, doc = http_at(base, "GET", "/api/archive/%s" % LID)
    c.check("GET /api/archive reports 0 items", len((doc or {}).get("items", [])) == 0,
            doc)

    print()
    print("== rev is recomputed, and the server agrees with its own rev ==")
    doc_live = json.load(open(lists_file, encoding="utf-8"))
    c.check("rev changed with the restore", doc_live.get("rev") != rev_archived,
            (rev_archived, doc_live.get("rev")))
    st, put = http_at(base, "PUT", "/api/lists/" + LID,
                      {"type": "UPDATE_ITEMS", "items": back, "userId": ADMIN_ID,
                       "baseRev": doc_live.get("rev")})
    c.check("a write carrying that rev is accepted (no REV_CONFLICT)",
            st == 200 and not (isinstance(put, dict) and put.get("code") == "REV_CONFLICT"),
            (st, put))
    st, b = http_at(base, "POST", "/api/lists/%s/unarchive" % LID, {"userId": ADMIN_ID})
    c.check("unarchive is idempotent when the archive is empty",
            st == 200 and as_dict(b).get("moved") == 0, (st, b))

    print()
    print("== the CLI does the same thing ==")
    st, ar = http_at(base, "POST", "/api/lists/%s/archive" % LID,
                   {"userId": ADMIN_ID, "confirm": True})
    c.check("re-archived for the CLI probe", st == 200 and as_dict(ar).get("moved") == 2, (st, ar))
    # --url is a top-level argparse option: it must precede the subcommand.
    p = subprocess.run([sys.executable, CLI, "--url", base, "unarchive",
                        "--category", LID, "--dry-run"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    c.check("cli unarchive --dry-run exits 0", p.returncode == 0,
            (p.returncode, p.stdout[-200:], p.stderr[-200:]))
    c.check("the dry run names the 2 entries it would bring back",
            "DRY-RUN" in p.stdout and "2" in p.stdout, p.stdout[-300:])
    c.check("a dry run restores nothing",
            len(read_items_file(lists_file)) == 1, len(read_items_file(lists_file)))
    p = subprocess.run([sys.executable, CLI, "--url", base, "unarchive",
                        "--category", LID],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    c.check("cli unarchive exits 0", p.returncode == 0,
            (p.returncode, p.stdout[-300:], p.stderr[-300:]))
    c.check("the cli brought everything back",
            ids_of(read_items_file(lists_file)) == ids_of(original),
            ids_of(read_items_file(lists_file)))
    c.check("the archive file is gone or empty after the cli restore",
            (not os.path.exists(arc_file))
            or len(read_items_file(arc_file)) == 0,
            os.path.exists(arc_file) and read_items_file(arc_file))
finally:
    if run and run.get("proc"):
        stop_instance(run["proc"])
    shutil.rmtree(tmp_root, ignore_errors=True)

print()
print("== file mode: recovery must work when the server is the thing that is down ==")
tmp_root2 = temp_dir(prefix="lt_grade_unarch_file_")
try:
    data_dir2 = copy_data_dir(tmp_root2)
    original2 = probe_items()
    write_list(data_dir2, LID, original2)
    lists_file2 = os.path.join(data_dir2, "shared_lists", "%s.json" % LID)
    arc_file2 = os.path.join(data_dir2, "archive", "%s.json" % LID)
    # Port 1 never answers, so the CLI takes its file-mode branch (grade_lib §28).
    down = ["--url", "http://127.0.0.1:1", "--root", tmp_root2]
    p = subprocess.run([sys.executable, CLI] + down + ["archive", "--category", LID],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    c.check("cli archive in file mode exits 0", p.returncode == 0,
            (p.returncode, p.stdout[-200:], p.stderr[-200:]))
    c.check("it really used file mode", "mode=FILE" in (p.stderr or ""), p.stderr[-200:])
    c.check("the archive file now holds 3 entries",
            os.path.exists(arc_file2) and len(read_items_file(arc_file2)) == 3,
            os.path.exists(arc_file2) and read_items_file(arc_file2))
    p = subprocess.run([sys.executable, CLI] + down + ["unarchive", "--category", LID],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    c.check("cli unarchive in file mode exits 0", p.returncode == 0,
            (p.returncode, p.stdout[-300:], p.stderr[-300:]))
    back2 = read_items_file(lists_file2)
    c.check("file mode round-trips content and structure too",
            canon_items(back2) == canon_items(original2),
            [i["itemId"] for i in back2 if canon_item(i) not in canon_items(original2)])
    c.check("file mode leaves no archive file behind", not os.path.exists(arc_file2),
            os.path.exists(arc_file2))
    rev2 = json.load(open(lists_file2, encoding="utf-8")).get("rev")
    c.check("file mode recomputes a 16-char rev", isinstance(rev2, str) and len(rev2) == 16,
            rev2)
    # The CLI and the server must derive the SAME rev token, otherwise a write
    # made while the server was down would look like a conflict after restart.
    node_src = ('const d=require(process.argv[1]);'
                'process.stdout.write(require("crypto").createHash("sha256")'
                '.update(JSON.stringify(d.items||[])).digest("hex").slice(0,16));')
    p = subprocess.run(["node", "-e", node_src, lists_file2],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    c.check("the CLI rev token is identical to node contentRev",
            p.returncode == 0 and p.stdout.strip() == rev2,
            (p.returncode, p.stdout.strip(), rev2, p.stderr[-200:]))
finally:
    shutil.rmtree(tmp_root2, ignore_errors=True)

print()
print("== the working board was not touched ==")
c.check("the real data files are byte-identical to before this grader ran",
        data_hashes() == HASHES_BEFORE, (HASHES_BEFORE, data_hashes()))

c.finish()
