# -*- coding: utf-8 -*-
"""
Grader: archived work must stay visible to links / trace / gaps.

`buildLinkGraph()` used to read `data/shared_lists` only. Archiving moves an item
out of the shared list and into `data/archive/<listId>.json`, so from the graph's
point of view the item stopped existing — and so did every relation it carried.
The visible damage is a **false gap**: a func item that *is* verified by a test
item starts being reported as `func-not-verified` the moment that test item is
archived. Coverage evidence disappearing is not the same as coverage
disappearing.

The fix under test:

* `buildLinkGraph()` reads the archive too; every node/edge carries
  `archived: true|false`.
* gaps use archived relations as **evidence** (an archived referrer still covers
  an owner) but never **report** archived items as gaps — otherwise archiving
  would manufacture new gaps out of closed work.

Two halves:

A. Ad-hoc rules on the live server, on throwaway lists: owner/referrer lists with
   a `verifies` edge, then the referrer is archived.
B. The real `func-not-verified` rule, on a throwaway `node server.js` started
   against a copy of data/ (LITETASK_DATA_DIR), where archiving `test` is safe.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import (ADMIN_ID, ROOT, Checker, api, copy_data_dir,  # noqa: E402
                       create_temp_list, delete_temp_list, get_list,
                       http_at, put_items, read_items_file, run_instance,
                       snapshot, stop_instance, temp_dir, temp_item)

import shutil  # noqa: E402

c = Checker("F3-archive-traceability")

# Coverage of the live board is a business fact that moves on its own: brand-new
# open work is legitimately unverified, and an architecture decision that has
# not been broken down yet is legitimately underived. It is therefore recorded
# here as a BASELINE to compare against, never asserted to be zero.
_, _gap_base = api("GET", "/api/gaps")
BASE_COUNTS = {r.get("value"): r.get("count")
               for r in (_gap_base or {}).get("rules", [])}

# Same reason, for the archive directory: a human may legitimately archive a
# list from the UI (that is what archiving is for), so "data/archive is empty"
# is a fact about today, not a property. Recorded as a baseline instead.
ARCHIVE_DIR = os.path.join(ROOT, "data", "archive")
ARCHIVE_BASELINE = sorted(os.listdir(ARCHIVE_DIR)) if os.path.isdir(ARCHIVE_DIR) else []


def rule_items(doc, value):
    for r in (doc or {}).get("rules", []):
        if r.get("value") == value:
            return r
    return None


def ids_of(rule):
    return [i.get("itemId") for i in (rule or {}).get("items", [])]


def node_of(nodes, item_id):
    for n in nodes or []:
        if n.get("itemId") == item_id:
            return n
    return None


# A temporary list plus a PUT helper bound to a given base URL.
def put_at(base, lid, items, force=True):
    payload = {"type": "UPDATE_ITEMS", "items": items, "userId": ADMIN_ID}
    if force:
        payload["force"] = True
    return http_at(base, "PUT", "/api/lists/" + lid, payload)


# ============================================ A. ad-hoc rule, live server
print("== setup: an owner item verified by a referrer item ==")
LA = create_temp_list("GRADE-TEMP f3 owner")     # plays the role of func
LB = create_temp_list("GRADE-TEMP f3 referrer")  # plays the role of test

put_items(LA, [temp_item("a1", title="owner under test", status="open")])
put_items(LB, [
    temp_item("b1", title="referrer, verifies a1", status="done", isDone=True,
              relatesTo=[{"listId": LA, "itemId": "a1", "relation": "verifies"}]),
    temp_item("b2", title="referrer with no relations", status="done", isDone=True),
])

adhoc = "/api/gaps?owner=%s&referrer=%s&relation=verifies" % (LA, LB)
_, g0 = api("GET", adhoc)
c.check("before archiving, the owner item is covered",
        rule_items(g0, "adhoc") and rule_items(g0, "adhoc").get("count") == 0,
        rule_items(g0, "adhoc"))

_, orphan0 = api("GET", "/api/gaps?rule=orphan")
c.check("before archiving, b1 is not an orphan",
        "b1" not in ids_of(rule_items(orphan0, "orphan")),
        ids_of(rule_items(orphan0, "orphan")))

_, links0 = api("GET", "/api/links")
n_a1_0 = node_of(links0["nodes"], "a1")
c.check("before archiving, a1 is an active node",
        n_a1_0 and n_a1_0.get("archived") is False, n_a1_0)

print()
print("== archive the referrer list ==")
st, body = api("POST", "/api/lists/%s/archive" % LB,
              {"userId": ADMIN_ID, "confirm": True})
c.check("archive answered 200", st == 200 and isinstance(body, dict), (st, body))
c.check("both closed items moved", isinstance(body, dict) and body.get("moved") == 2, body)
c.check("the referrer list is now empty on the board",
        len(get_list(LB)["items"]) == 0, get_list(LB)["items"])
st, adoc = api("GET", "/api/archive/" + LB)
c.check("the archived items are readable",
        st == 200 and sorted(i["itemId"] for i in (adoc or {}).get("items", [])) == ["b1", "b2"],
        st)

print()
print("== coverage survives archiving ==")
_, g1 = api("GET", adhoc)
r1 = rule_items(g1, "adhoc")
c.check("the owner item is STILL covered by the archived referrer",
        r1 and r1.get("count") == 0, r1)
c.check("the owner item is not listed as a gap", "a1" not in ids_of(r1), ids_of(r1))

print()
print("== archived work is in the graph, flagged ==")
_, links1 = api("GET", "/api/links")
n_b1 = node_of(links1["nodes"], "b1")
c.check("the archived item is still a node", n_b1 is not None,
        [n.get("itemId") for n in links1.get("nodes", [])][:12])
c.check("it is flagged as archived", n_b1 and n_b1.get("archived") is True, n_b1)
c.check("it keeps the list it came from", n_b1 and n_b1.get("listId") == LB, n_b1)
c.check("the active item is flagged as not archived",
        node_of(links1["nodes"], "a1") and node_of(links1["nodes"], "a1").get("archived") is False,
        node_of(links1["nodes"], "a1"))
edge = [e for e in links1.get("edges", [])
        if e["from"]["itemId"] == "b1" and e["to"]["itemId"] == "a1"]
c.check("its verifies edge survived", len(edge) == 1 and edge[0]["relation"] == "verifies",
        edge)

print()
print("== trace walks into archived work ==")
_, tr = api("GET", "/api/trace?listId=%s&itemId=a1&direction=back&depth=3" % LA)
c.check("trace answers 200", isinstance(tr, dict) and "count" in tr, tr)
c.check("the archived referrer shows up in the backward trace",
        "b1" in [i.get("itemId") for i in (tr or {}).get("items", [])],
        [i.get("itemId") for i in (tr or {}).get("items", [])])

print()
print("== archiving does not manufacture gaps ==")
_, orphan1 = api("GET", "/api/gaps?rule=orphan")
c.check("the archived item with no relations is not an orphan gap",
        "b2" not in ids_of(rule_items(orphan1, "orphan")),
        ids_of(rule_items(orphan1, "orphan")))
c.check("the archived verifier is not an orphan gap either",
        "b1" not in ids_of(rule_items(orphan1, "orphan")),
        ids_of(rule_items(orphan1, "orphan")))
c.check("b2 really was an orphan gap while it was active",
        "b2" in ids_of(rule_items(orphan0, "orphan")),
        ids_of(rule_items(orphan0, "orphan")))
c.check("archiving never increases the orphan count",
        (rule_items(orphan1, "orphan") or {}).get("count")
        <= (rule_items(orphan0, "orphan") or {}).get("count"),
        ((rule_items(orphan0, "orphan") or {}).get("count"),
         (rule_items(orphan1, "orphan") or {}).get("count")))

for lid in (LA, LB):
    delete_temp_list(lid)
c.check("temp lists removed again",
        get_list(LA) is None and get_list(LB) is None, (LA, LB))
c.check("their archive files were cleaned up too",
        not os.path.exists("%s/data/archive/%s.json" % (ROOT, LB)), LB)


# ============================ B. the real func/test rule, hermetic instance
print()
print("== the real func-not-verified rule, on a private copy of data/ ==")
tmp = temp_dir(prefix="lt_grade_f3_")
inst = None
try:
    data_dir = copy_data_dir(tmp)
    backup_dir = os.path.join(tmp, "backup")
    inst = run_instance(data_dir, backup_dir, {"LITETASK_AUTO_ARCHIVE": "0"},
                        wait_after_ready=1.5, keep=True)
    c.check("the throwaway instance came up", inst["ready"], inst["output"][-300:])
    base = "http://localhost:%d" % inst["port"]

    _, funcs = http_at(base, "GET", "/api/lists")
    func_items = [l for l in funcs if l.get("listId") == "func"][0]["items"]
    test_items = [l for l in funcs if l.get("listId") == "test"][0]["items"]
    arch_items = [l for l in funcs if l.get("listId") == "arch"][0]["items"]

    # The board's business state evolves — brand-new open work is legitimately
    # not covered by a test yet. This grader tests the ARCHIVING machinery, not
    # the board's current coverage, so neutralize whatever the copy inherited
    # with copy-only fixture items before asserting machinery behaviour.
    _, g0 = http_at(base, "GET", "/api/gaps")

    def deep_ids(items):
        out = set()
        for x in items or []:
            out.add(x.get("itemId"))
            out |= deep_ids(x.get("subTasks"))
        return out

    # The orphan rule is `owner: '*'`: any node with no edge at either end,
    # whatever list it sits in. Orphans are therefore NOT confined to func/arch —
    # a newly added list (a bug tracker, say) legitimately starts with entries
    # that relate to nothing, and every one of them is reported. This grader
    # tests the ARCHIVING machinery, not the board's coverage, so neutralise
    # those here too, before the baseline below is measured: each gets a
    # throwaway edge in this copy. The copy is discarded when the grader ends;
    # the working data/ is never touched.
    def tag_orphans(items, oids, edge):
        """Give every item (or subtask) whose id is in `oids` a fixture edge."""
        hit = [False]

        def walk(arr):
            for x in arr or []:
                if x.get("itemId") in oids:
                    x["relatesTo"] = list(x.get("relatesTo") or []) + [edge]
                    hit[0] = True
                walk(x.get("subTasks"))
        walk(items)
        return hit[0]

    stray_by_list = {}
    for n in (rule_items(g0, "orphan") or {}).get("items", []):
        lid = n.get("listId")
        if lid in ("func", "arch"):
            continue                       # the fixtures further down cover these
        stray_by_list.setdefault(lid, set()).add(n.get("itemId"))
    if stray_by_list and deep_ids(arch_items):
        edge = {"listId": "arch", "itemId": sorted(deep_ids(arch_items))[0],
                "relation": "related"}
        for lid, oids in sorted(stray_by_list.items()):
            _, doc = http_at(base, "GET", "/api/lists/%s" % lid)
            items = (doc or {}).get("items", [])
            if items and tag_orphans(items, oids, edge):
                put_at(base, lid, items)
        _, g0 = http_at(base, "GET", "/api/gaps")   # re-read: the board is clean now

    # buildLinkGraph enumerates subtasks as their own nodes, so the id sets
    # must include them (a fresh subtask under a func item is a func node too).
    func_ids = deep_ids(func_items)
    arch_ids = deep_ids(arch_items)
    uncovered_func = set(ids_of(rule_items(g0, "func-not-verified")))
    uncovered_arch = set(ids_of(rule_items(g0, "arch-not-derived")))
    orphan_ids = set(ids_of(rule_items(g0, "orphan")))
    uncovered_func |= orphan_ids & func_ids
    uncovered_arch |= orphan_ids & arch_ids
    stray_orphans = orphan_ids - func_ids - arch_ids
    # A fixture derivation is itself a func node. If it is not covered by a
    # verifier, neutralising arch-not-derived manufactures fresh
    # func-not-verified gaps and the baseline below can never reach zero.
    # (Happened 2026-10-29: three new arch items made this grader fail with
    # three gfix-f* items listed as func-not-verified.)
    fx_funcs = [temp_item("gfix-f%d" % n, title="grader fixture derivation",
                          status="done", isDone=True,
                          relatesTo=[{"listId": "arch", "itemId": aid,
                                      "relation": "derives-from"}])
                for n, aid in enumerate(sorted(uncovered_arch))]
    uncovered_func |= {x["itemId"] for x in fx_funcs}
    fx_tests = [temp_item("gfix-t%d" % n, title="grader fixture verifier",
                          status="done", isDone=True,
                          relatesTo=[{"listId": "func", "itemId": fid,
                                      "relation": "verifies"}])
                for n, fid in enumerate(sorted(uncovered_func))]
    if fx_funcs:
        func_items = func_items + fx_funcs
        put_at(base, "func", func_items)
    if fx_tests:
        test_items = test_items + fx_tests
        put_at(base, "test", test_items)
    _, g0b = http_at(base, "GET", "/api/gaps")
    leftovers = [(r.get("value"), r.get("count"))
                 for r in (g0b or {}).get("rules", []) if r.get("count")]
    c.check("the copy starts from a zero-gap baseline (open board work neutralized)",
            not leftovers and not stray_orphans,
            leftovers + sorted(stray_orphans))

    # one brand new func item, verified only by one brand new test item
    fx = temp_item("fx-new", title="func covered only by a soon-archived test",
                   status="open")
    tx = temp_item("tx-new", title="verifier that will be archived", status="done",
                   isDone=True,
                   relatesTo=[{"listId": "func", "itemId": "fx-new", "relation": "verifies"}])
    put_at(base, "func", func_items + [fx])
    put_at(base, "test", test_items + [tx])

    _, gA = http_at(base, "GET", "/api/gaps?rule=func-not-verified")
    c.check("before archiving, the new func item is covered",
            "fx-new" not in ids_of(rule_items(gA, "func-not-verified")),
            ids_of(rule_items(gA, "func-not-verified")))

    st, ar = http_at(base, "POST", "/api/lists/test/archive",
                 {"userId": ADMIN_ID, "confirm": True})
    # Archiving moves the CLOSED items; the board's test list carries two
    # open/blocked entries (DOM rendering baseline measurement, exam_case_01 probe isolation), so the
    # count that belongs in this assertion is the closed one — derived here
    # rather than baked in (grade_lib rule 3).
    all_test = test_items + [tx]
    closed_test = sum(1 for i in all_test
                      if i.get("isDone") is True or i.get("status") == "done")
    c.check("the copy's test list was archived",
            st == 200 and ar.get("moved") == closed_test,
            (st, ar, closed_test, len(all_test)))
    c.check("the archived verifier is on disk in the copy",
            any(i.get("itemId") == "tx-new"
                for i in read_items_file(os.path.join(data_dir, "archive", "test.json"))), None)

    _, gB = http_at(base, "GET", "/api/gaps?rule=func-not-verified")
    rb = rule_items(gB, "func-not-verified")
    c.check("after archiving, the func item is STILL not a gap",
            rb and "fx-new" not in ids_of(rb), ids_of(rb))
    c.check("func-not-verified stays at zero", rb and rb.get("count") == 0, rb)

    _, gC = http_at(base, "GET", "/api/gaps")
    c.check("arch-not-derived stays at zero too",
            (rule_items(gC, "arch-not-derived") or {}).get("count") == 0,
            rule_items(gC, "arch-not-derived"))
    c.check("the orphan rule reports no archived item",
            not (set(ids_of(rule_items(gC, "orphan")))
                 & set(["tx-new", "fx-new"])),
            ids_of(rule_items(gC, "orphan")))

    _, lk = http_at(base, "GET", "/api/links")
    n_tx = node_of(lk.get("nodes", []), "tx-new")
    c.check("the archived verifier is a node, flagged archived",
            n_tx and n_tx.get("archived") is True, n_tx)
    c.check("it still belongs to the test list", n_tx and n_tx.get("listId") == "test", n_tx)
finally:
    if inst and inst.get("proc"):
        stop_instance(inst["proc"])
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("== the working data is untouched by the copy's experiment ==")
_, gfinal = api("GET", "/api/gaps")
for rv in ["func-not-verified", "arch-not-derived", "orphan"]:
    c.check("%s is unchanged by the experiment (baseline %s)" % (rv, BASE_COUNTS.get(rv)),
            (rule_items(gfinal, rv) or {}).get("count") == BASE_COUNTS.get(rv),
            (BASE_COUNTS.get(rv), rule_items(gfinal, rv)))
now_archive = sorted(os.listdir(ARCHIVE_DIR)) if os.path.isdir(ARCHIVE_DIR) else []
c.check("the working archive dir is unchanged by the experiment",
        now_archive == ARCHIVE_BASELINE, (ARCHIVE_BASELINE, now_archive))

c.finish()
