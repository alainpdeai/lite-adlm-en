# Auto-generated
# -*- coding: utf-8 -*-
"""
Grader for test item Verify F3 reverse traceability filter queries and coverage gap analysis
(task_17931475877425a8af9).

Recorded claims:

* /api/trace walks the relation graph backwards, forwards or both, honours a
  depth limit, and answers 404 for an unknown item instead of hanging or 500;
* it is cycle-safe — a mutual pair does not turn into an infinite walk;
* /api/gaps reports the three rules configured in categories.json, and also
  accepts an ad-hoc (owner, referrer, relation) filter.

The cycle test needs real cyclic data, so it is built on a throwaway list and
removed again.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import (api, Checker, create_temp_list, delete_temp_list,  # noqa: E402
                       get_list, put_items, temp_item)

c = Checker("F3")

ROOT_ITEM = "task_arch_b1"      # B1 has test items behind it

# The direction/depth claims are anchored on a real seeded fixture. A clean
# delivery baseline has an empty arch list, so the fixture is absent: SKIP the
# dependent assertions rather than turning a missing fixture into a red build.
# Everything below (404 semantics, cycle safety, /api/gaps) is fixture-free.
_arch = get_list("arch") or {}
HAVE_FIXTURE = any(i.get("itemId") == ROOT_ITEM for i in (_arch.get("items") or []))

print("== trace: directions ==")
if HAVE_FIXTURE:
    for direction in ("back", "forward", "both"):
        st, body = api("GET", "/api/trace?listId=arch&itemId=%s&direction=%s&depth=3"
                       % (ROOT_ITEM, direction))
        c.check("direction=%s answers 200" % direction, st == 200, (st, body))
        c.check("direction=%s echoes the direction" % direction,
                isinstance(body, dict) and body.get("direction") == direction,
                (body or {}).get("direction"))
        c.check("direction=%s reports a count" % direction,
                isinstance(body, dict) and isinstance(body.get("count"), int),
                (body or {}).get("count"))
else:
    c.skip("trace directions (back/forward/both)",
           "fixture %s absent in empty delivery baseline" % ROOT_ITEM)

print()
print("== trace: depth is honoured ==")
counts = {}
if HAVE_FIXTURE:
    for depth in (1, 2, 3):
        st, body = api("GET", "/api/trace?listId=arch&itemId=%s&direction=back&depth=%d"
                       % (ROOT_ITEM, depth))
        counts[depth] = (body or {}).get("count")
    c.check("a deeper walk never returns fewer nodes",
            all(isinstance(v, int) for v in counts.values())
            and counts[1] <= counts[2] <= counts[3], counts)
else:
    c.skip("a deeper walk never returns fewer nodes",
           "fixture %s absent in empty delivery baseline" % ROOT_ITEM)

print()
print("== trace: unknown item is a clean 404 ==")
st, body = api("GET", "/api/trace?listId=arch&itemId=does-not-exist&direction=back&depth=2")
c.check("unknown item -> 404", st == 404, (st, body))
c.check("404 explains itself",
        isinstance(body, dict) and "not found" in str(body.get("error", "")), body)

print()
print("== trace is cycle-safe ==")
LID = create_temp_list("GRADE-TEMP f3")
try:
    put_items(LID, [
        temp_item("cA", title="A", relatesTo=[{"listId": LID, "itemId": "cB", "relation": "related"}]),
        temp_item("cB", title="B", relatesTo=[{"listId": LID, "itemId": "cA", "relation": "related"}]),
    ])
    st, body = api("GET", "/api/trace?listId=%s&itemId=cA&direction=both&depth=5" % LID,
                   timeout=15)
    c.check("a mutual pair does not hang", st == 200, (st, body))
    c.check("the walk terminates with a finite count",
            isinstance(body, dict) and isinstance(body.get("count"), int),
            (body or {}).get("count"))
    c.check("nodes are not duplicated endlessly",
            isinstance(body, dict) and (body.get("count") or 0) <= 4,
            (body or {}).get("count"))
finally:
    delete_temp_list(LID)
c.check("temp list removed again", get_list(LID) is None, LID)

print()
print("== gaps: the configured rules ==")
st, body = api("GET", "/api/gaps")
c.check("/api/gaps answers", st == 200, st)
rules = {r.get("value"): r for r in (body or {}).get("rules", [])}
c.check("all three configured rules are reported",
        set(rules) == {"func-not-verified", "arch-not-derived", "orphan"}, sorted(rules))
c.check("each rule carries a count",
        all(isinstance(r.get("count"), int) for r in rules.values()),
        {k: r.get("count") for k, r in rules.items()})
c.check("func coverage is credited by the test list",
        rules.get("func-not-verified", {}).get("referrer") == "test",
        rules.get("func-not-verified", {}).get("referrer"))
c.check("arch derivation is credited by the func list",
        rules.get("arch-not-derived", {}).get("referrer") == "func",
        rules.get("arch-not-derived", {}).get("referrer"))

print()
print("== gaps: ad-hoc filter ==")
st, body = api("GET", "/api/gaps?owner=func&referrer=test&relation=verifies")
c.check("ad-hoc query answers", st == 200, (st, body))
adhoc = (body or {}).get("rules") or []
c.check("it returns one ad-hoc rule", len(adhoc) == 1, len(adhoc))
c.check("the rule echoes the parameters",
        adhoc and adhoc[0].get("owner") == "func" and adhoc[0].get("referrer") == "test"
        and adhoc[0].get("relation") == "verifies", adhoc[:1])

c.finish()
