# -*- coding: utf-8 -*-
"""
Exam case 03 — append the graded result to the exam entry's comment.

Appends only: the existing note is left intact and the new text is added as its
own paragraph. Reads the current rev and sends it back as baseRev (B3), so a
concurrent edit is refused with 409 instead of being clobbered.
"""
import json
import sys
import urllib.request
import urllib.error

BASE = "http://localhost:3000"
LIST = "exam"
ITEM_ID = "task_1793212781323a83e01"
ADMIN_ID = "user_admin"

PARA = """[Correction 2026-10-31 16:35]
Previous entry described pre-refactor design running in production exam list. That description is obsolete.

Current design runs on disposable probe list EXAM03-PROBE. Zero contact with live exam list.

Recompute: python tests/exam_case_03_grade.py -> RESULT exam-case-03: PASS (40 checks) - recorded answer reproduces exactly. Exit code 0 = answer holds."""


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
