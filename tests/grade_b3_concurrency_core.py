# -*- coding: utf-8 -*-
"""
Grader for test item Verify B3 concurrent write protection (task_17931411951464d0059).

Recorded claim: a write that was computed against a stale revision is refused
(409 REV_CONFLICT) instead of clobbering the newer content; concurrent writers
are serialised so the file is never torn; and the revision token is a function
of the content, not of time.

`test_conflict_diff.py` already grades the *shape* of the 409 diff payload. This
grader grades the protection semantics around it, and does the destructive part
(8 simultaneous writers) on a throwaway list so nothing real can be lost.
"""
import json
import os
import re
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import (api, Checker, create_temp_list, delete_temp_list,  # noqa: E402
                       get_list, put_items, server_shared_lists_dir, temp_item)

c = Checker("B3")

LID = create_temp_list("GRADE-TEMP b3")
try:
    print("== revision token ==")
    _, body = put_items(LID, [temp_item("b3a", title="v1")])
    lst = get_list(LID)
    rev1 = lst["rev"]
    c.check("rev is a 16-char hex digest", bool(re.match(r"^[0-9a-f]{16}$", rev1 or "")), rev1)

    put_items(LID, [temp_item("b3a", title="v1")], rev=rev1)     # identical content
    rev2 = get_list(LID)["rev"]
    c.check("rewriting identical content does not bump the rev", rev1 == rev2,
            (rev1, rev2))

    put_items(LID, [temp_item("b3a", title="v2")], rev=rev2)
    rev3 = get_list(LID)["rev"]
    c.check("changing content bumps the rev", rev3 != rev2, (rev2, rev3))

    print()
    print("== stale writer is refused, not clobbered ==")
    st, body = put_items(LID, [temp_item("b3b", title="stale attempt")], rev=rev2)
    c.check("stale baseRev -> 409", st == 409, (st, body))
    c.check("error code is REV_CONFLICT",
            isinstance(body, dict) and body.get("code") == "REV_CONFLICT", body)
    c.check("409 carries a diff payload",
            isinstance(body, dict) and isinstance(body.get("diff"), dict),
            (body or {}).get("diff"))
    titles = [i.get("title") for i in get_list(LID)["items"]]
    c.check("the stale write did not land", titles == ["v2"], titles)

    print()
    print("== eight simultaneous writers ==")
    base = get_list(LID)["rev"]
    results = []
    lock = threading.Lock()

    def writer(n):
        st, body = put_items(LID, [temp_item("b3c", title="writer-%d" % n)], rev=base)
        with lock:
            results.append((n, st))

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ok = [n for n, s in results if s == 200]
    conflicted = [n for n, s in results if s == 409]
    other = [(n, s) for n, s in results if s not in (200, 409)]
    c.check("exactly one writer wins", len(ok) == 1, {"200": ok, "409": conflicted})
    c.check("the losers are all refused with 409", len(conflicted) == 7,
            {"409": len(conflicted), "other": other})
    c.check("no writer saw an unexpected status", not other, other)

    final = get_list(LID)
    c.check("the surviving content is the winner's, whole",
            [i.get("title") for i in final["items"]] == ["writer-%d" % ok[0]],
            [i.get("title") for i in final["items"]])
    c.check("rev advanced past the base", final["rev"] != base, (base, final["rev"]))

    print()
    print("== no torn or half-written files ==")
    shared = server_shared_lists_dir()
    leftovers = [f for f in os.listdir(shared)
                 if f.endswith(".tmp") or ".tmp-" in f or f.startswith(".")]
    c.check("no temp files left behind by atomicWriteJson", not leftovers, leftovers)
    with open(os.path.join(shared, LID + ".json"), encoding="utf-8") as f:
        parsed = json.load(f)
    c.check("the list file still parses as JSON", isinstance(parsed, dict), type(parsed).__name__)
    c.check("and still carries its items", len(parsed.get("items", [])) == 1,
            len(parsed.get("items", [])))

    print()
    print("== force is the documented escape hatch ==")
    st, body = put_items(LID, [temp_item("b3d", title="forced")], rev=base, force=True)
    c.check("a stale write with force is accepted", st == 200, (st, body))
    c.check("rev advanced after the forced write",
            get_list(LID)["rev"] != final["rev"], None)
    c.check("forced content is what was sent",
            [i.get("title") for i in get_list(LID)["items"]] == ["forced"],
            [i.get("title") for i in get_list(LID)["items"]])
finally:
    delete_temp_list(LID)

c.check("temp list removed again", get_list(LID) is None, LID)
c.finish()
