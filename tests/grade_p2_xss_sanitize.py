# -*- coding: utf-8 -*-
"""P2-5 grader: comments are sanitized before storage."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (  # noqa: E402
    Checker, copy_data_dir, http_at, run_instance, stop_instance, temp_dir,
)

NAME = "p2-xss-sanitize"
c = Checker(NAME)
json_out = None
if "--json" in sys.argv:
    i = sys.argv.index("--json")
    if i + 1 < len(sys.argv):
        json_out = sys.argv[i + 1]

ADMIN = "user_admin"
LID = "probe_xss"
PAYLOADS = [
    '<img src=x onerror=alert(1)>',
    '<script>alert(1)</script>hello',
    '<svg onload=alert(1)>x</svg>',
    '<iframe srcdoc="x">y</iframe>',
    '<p onclick="alert(1)">ok</p>',
    '<a href="javascript:alert(1)">x</a>',
    '<a href="jav&#x09;ascript:alert(1)">x</a>',
    '<a href="data:text/html,<script>alert(1)</script>">x</a>',
    '<object data=x></object>',
    '<style>body{}</style>',
    '<math><mtext>x</mtext></math>',
    '<scr<script>ipt>alert(1)</scr<script>ipt>',
    '<div style="background:url(x)">x</div>',
    '<p><b>bold</b> <em>em</em></p>',
    '<ol><li>one</li></ol><ul><li>two</li></ul>',
    '<a href="https://ok.example" target="_blank">ok</a>',
    '<p>1 &lt; 2 &amp; 3</p>',
    'plain text',
    '<span class="ql-align-center">x</span>',
    '<br>',
]


def item(iid, comment=""):
    return {"itemId": iid, "title": iid, "isDone": False, "status": "open",
            "statusHistory": [], "blockedReason": "", "dueDate": "",
            "priority": "Medium", "assignedTo": "admin", "createdBy": "admin",
            "createdByAgent": "AI Agent", "createdById": ADMIN,
            "createdAt": "2026-11-01 00:00", "closedBy": None,
            "closedById": None, "closedAt": None, "localDirectory": "",
            "localDirectories": [], "comment": comment, "subTasks": []}


ctx = None
try:
    tmp = temp_dir(prefix="lt_p2_xss_")
    data = copy_data_dir(os.path.join(tmp, "inst"))
    os.makedirs(os.path.join(data, "shared_lists"), exist_ok=True)
    with open(os.path.join(data, "shared_lists", LID + ".json"), "w", encoding="utf-8") as f:
        json.dump({"listId": LID, "listName": "P2 XSS", "category": "test", "items": []}, f)
    logs = os.path.join(tmp, "logs")
    inst = run_instance(data, os.path.join(tmp, "backup"), {
        "LITETASK_AUTO_ARCHIVE": "0", "LITETASK_BACKUP_MIRROR": "0",
        "LITETASK_LOG_DIR": logs,
        "LITETASK_AUDIT_FILE": os.path.join(logs, "audit.log"),
    }, wait_after_ready=2.0, timeout=60, keep=True)
    ctx = {"inst": inst, "tmp": tmp}
    b = "http://127.0.0.1:%d" % inst["port"]
    c.check("instance started", inst["ready"], inst["output"][-120:])

    stored = []
    for i, payload in enumerate(PAYLOADS):
        lid = "x%d" % i
        doc = {"listId": LID, "listName": "P2 XSS", "category": "test",
               "items": [item(lid, payload)]}
        st, body = http_at(b, "PUT", "/api/lists/" + LID,
                           {"type": "UPDATE_ITEMS", "userId": ADMIN, "items": doc["items"]})
        st, got = http_at(b, "GET", "/api/lists/" + LID)
        comment = ((got.get("items") or [{}])[0].get("comment") or "")
        stored.append(comment)
        dangerous = ("<script" in comment.lower() or "onerror" in comment.lower()
                     or "javascript:" in comment.lower() or "<iframe" in comment.lower()
                     or "<svg" in comment.lower() or "<object" in comment.lower()
                     or "<style" in comment.lower() or "<math" in comment.lower())
        c.check("payload %d stored without executable markup" % i, st == 200 and not dangerous,
                comment[:80])

    joined = "\n".join(stored)
    c.check("legal bold/italic/list/br formatting survives",
            "<b>bold</b>" in joined and "<em>em</em>" in joined
            and "<li>one</li>" in joined and "<br>" in joined, joined[-120:])
    c.check("https links survive", 'href="https://ok.example"' in joined, joined[-120:])
    c.check("entities remain escaped", "&lt; 2" in joined, joined[-120:])
    c.check("javascript:/data: hrefs are stripped",
            "javascript:" not in joined.lower() and "data:text/html" not in joined.lower(),
            joined[-120:])

    # idempotent: same comment twice keeps the same rev
    payload = "<p onclick=x>same</p>"
    st, r1 = http_at(b, "PUT", "/api/lists/" + LID,
                     {"type": "UPDATE_ITEMS", "userId": ADMIN,
                      "items": [item("idem", payload)]})
    st, r2 = http_at(b, "PUT", "/api/lists/" + LID,
                     {"type": "UPDATE_ITEMS", "userId": ADMIN,
                      "items": [item("idem", payload)], "baseRev": r1.get("rev")})
    c.check("sanitisation is idempotent (rev does not churn)",
            r1.get("rev") == r2.get("rev"), (r1.get("rev"), r2.get("rev")))

    # too long rejected with no partial write
    long_comment = "x" * 20001
    st, body = http_at(b, "PUT", "/api/lists/" + LID,
                       {"type": "UPDATE_ITEMS", "userId": ADMIN,
                        "items": [item("long", long_comment)]})
    c.check("over-long comment is 400 COMMENT_TOO_LONG",
            st == 400 and body.get("code") == "COMMENT_TOO_LONG", (st, body))
    st, got = http_at(b, "GET", "/api/lists/" + LID)
    c.check("over-long comment was not partially stored",
            not any(i.get("itemId") == "long" for i in (got.get("items") or [])), got.get("items"))
finally:
    if ctx and ctx["inst"].get("proc"):
        stop_instance(ctx["inst"]["proc"])
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump({"grader": NAME, "result": "FAIL" if c.failed else "PASS",
                       "checks": c.passed + len(c.failed), "failures": c.failed},
                      f, ensure_ascii=False, indent=2)
    import shutil
    if ctx:
        shutil.rmtree(ctx["tmp"], ignore_errors=True)
c.finish()