# -*- coding: utf-8 -*-
"""
Exam case 01 — append the graded result to the exam entry's comment.

Appends only: the existing comment is left byte-for-byte intact and the new
text is added as its own paragraph at the end. Reads the current rev and sends
it back as baseRev (B3 optimistic concurrency), so a concurrent edit is
refused with 409 instead of being clobbered.
"""
import json
import sys
import urllib.request
import urllib.error

BASE = "http://localhost:3000"
LIST = "exam"
ITEM_ID = "task_17932045419986be2b6"
ADMIN_ID = "user_admin"

PARA = """[Empirical Archive 2026-10-28 17:36]

Grader tests/exam_case_01_grade.py (probe tests/exam_case_01_status_flow.py) -> RESULT: PASS. 25/25 cells match gold standard, 22 accepted / 3 rejected.

Server error messages for 3 rejections (400 INVALID_TRANSITION):
open -> verified: Invalid status transition 'open -> verified' (exam-probe). Allowed: in-progress / blocked / done
blocked -> verified: Invalid status transition 'blocked -> verified' (exam-probe). Allowed: open / in-progress / done
verified -> open: Invalid status transition 'verified -> open' (exam-probe). Allowed: in-progress / blocked / done

Divergence remains 5 self-transitions (open / in-progress / blocked / verified / done -> self); statusFlow still declares 17 legal transitions. The grader asserts divergence stability: any change requires recomputing rather than reusing stale text.

Exam list ID set identical before and after run (task_17932045419986be2b6), no leftover probe items.

Recompute: python tests/exam_case_01_grade.py (Exit code 0 = answer still holds)."""


def api(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "null")


def main():
    _, lists = api("GET", "/api/lists")
    lst = next(l for l in lists if l["listId"] == LIST)
    items = lst["items"]
    idx = next(i for i, it in enumerate(items) if it["itemId"] == ITEM_ID)
    item = items[idx]

    old_len = len(item["comment"])
    if PARA[:40] in item["comment"]:
        print("already appended, nothing to do")
        return 0

    new_item = dict(item)
    new_item["comment"] = item["comment"].rstrip("\n") + "\n\n" + PARA + "\n"
    new_items = list(items)
    new_items[idx] = new_item

    st, body = api("PUT", "/api/lists/" + LIST,
                   {"type": "UPDATE_ITEMS", "items": new_items,
                    "baseRev": lst["rev"], "userId": ADMIN_ID})
    print("PUT -> %s %s" % (st, body if st != 200 else ""))
    if st != 200:
        return 1

    # verbatim check straight off the server, not off what we just sent
    _, lists2 = api("GET", "/api/lists")
    got = next(it for it in next(l for l in lists2 if l["listId"] == LIST)["items"]
               if it["itemId"] == ITEM_ID)["comment"]
    print("comment length: %d -> %d" % (old_len, len(got)))
    print("original prefix intact:", got[:old_len].rstrip("\n") == item["comment"].rstrip("\n"))
    print("appended paragraph present:", PARA[:40] in got)
    print("--- last 200 chars ---")
    print(got[-200:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
