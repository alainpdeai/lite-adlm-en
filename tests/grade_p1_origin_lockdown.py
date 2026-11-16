# -*- coding: utf-8 -*-
"""
P1-5 grader: no wildcard CORS, and Socket.IO is gated by origin and session.

The two P0 red lines are asserted first-class:
  * a polling client with no Origin must still connect in local mode;
  * a same-origin browser connection must still receive `resync`.
"""
import glob
import json
import os
import socket
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (  # noqa: E402
    Checker, ROOT, copy_data_dir, http_at, http_at_headers,
    run_instance, stop_instance, temp_dir,
)

NAME = "p1-origin-lockdown"
c = Checker(NAME)

json_out = None
if "--json" in sys.argv:
    i = sys.argv.index("--json")
    if i + 1 < len(sys.argv):
        json_out = sys.argv[i + 1]

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def start(tag, env_extra):
    tmp = temp_dir(prefix="lt_p1_origin_%s_" % tag)
    data = copy_data_dir(os.path.join(tmp, "inst"))
    env = {"LITETASK_AUTO_ARCHIVE": "0", "LITETASK_BACKUP_MIRROR": "0",
           "LITETASK_LOG_DIR": os.path.join(tmp, "logs"),
           "LITETASK_AUDIT_FILE": os.path.join(tmp, "logs", "audit.log")}
    env.update(env_extra or {})
    inst = run_instance(data, os.path.join(tmp, "backup"), env,
                        wait_after_ready=2.0, timeout=60, keep=True)
    return {"inst": inst, "tmp": tmp, "base": "http://127.0.0.1:%d" % inst["port"],
            "output": inst["output"], "logs": env["LITETASK_LOG_DIR"]}


def raw(base, sid=None, body=None, origin=None, cookie=None, timeout=4.0):
    path = "/socket.io/?EIO=4&transport=polling" + (("&sid=" + sid) if sid else "")
    data = body.encode("utf-8") if body is not None else None
    headers = {}
    if origin:
        headers["Origin"] = origin
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(base + path, data=data, method="POST" if data else "GET",
                                 headers=headers)
    try:
        with OPENER.open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                                          # noqa: BLE001
        return 0, "transport error: %s" % e


def handshake(base, origin=None, cookie=None):
    """Return (accepted, sid_or_reason, body). Rejected = 403 or 44 connect_error."""
    st, body = raw(base, origin=origin, cookie=cookie)
    if st == 403:
        return False, "403", body
    if not (body or "").startswith("0"):
        return False, "no-open-packet:%s" % (st,), body
    try:
        sid = json.loads(body[1:])["sid"]
    except Exception:                                              # noqa: BLE001
        return False, "bad-open-packet", body
    st2, body2 = raw(base, sid=sid, body="40", origin=origin, cookie=cookie)
    if st2 == 403:
        return False, "403-after-open", body2
    if (body2 or "").startswith("44"):
        return False, "connect_error", body2
    # The namespace reply is delivered on the next poll; a rejected io.use shows
    # up as a 44/AUTH_REQUIRED packet there, not in the POST ack.
    st3, body3 = raw(base, sid=sid, origin=origin, cookie=cookie)
    if (body3 or "").startswith("44") or "AUTH_REQUIRED" in (body3 or ""):
        return False, "connect_error", body3
    if st3 == 403:
        return False, "403-after-open", body3
    return True, sid, (body2 or "") + "|" + (body3 or "")


def poll(base, sid, origin=None, cookie=None):
    st, body = raw(base, sid=sid, origin=origin, cookie=cookie)
    return st, body


local = shared = wild = exact = None
try:
    local = start("local", {})
    lb = local["base"]

    # -------------------------------------------- 1. no wildcard ACAO on HTTP
    for path in ("/api/lists", "/api/config", "/api/health"):
        st, _, hdrs = http_at_headers(lb, "GET", path,
                                      headers={"Origin": "https://evil.example"})
        h = {k.lower(): v for k, v in hdrs.items()}
        c.check("no Access-Control-Allow-Origin on %s" % path,
                "access-control-allow-origin" not in h, h.get("access-control-allow-origin"))

    # ------------------------------------------------ 2. no CORS in the source
    blob = ""
    for f in [os.path.join(ROOT, "server.js")] + glob.glob(os.path.join(ROOT, "lib", "*.js")):
        with open(f, encoding="utf-8", errors="replace") as fh:
            blob += fh.read()
    c.check("source has no cors() middleware or ACAO header",
            "Access-Control-Allow-Origin" not in blob
            and "require('cors')" not in blob
            and not any("cors(" in line and "origin" in line for line in blob.splitlines()),
            "CORS still present")

    # ------------------------------------------- 3. cross-origin socket denied
    ok, sid, body = handshake(lb, origin="https://evil.example")
    c.check("cross-origin socket handshake is rejected", not ok, (ok, sid))
    if not ok:
        c.check("rejection body does not echo the origin or an internal address",
                "evil.example" not in str(body) and "127.0.0.1" not in str(body)
                and "Error:" not in str(body), body[:200])
    else:
        c.check("rejection body does not echo the origin or an internal address", False, "not rejected")

    # ----------------------------------------------- 4. same-origin still works
    ok, sid, transcript = handshake(lb, origin=lb)
    c.check("same-origin socket handshake succeeds", ok, (ok, sid))
    got_resync = "resync" in (transcript or "")
    if ok and not got_resync:
        st, payload = poll(lb, sid, origin=lb)
        got_resync = "resync" in (payload or "")
    c.check("same-origin connection receives resync", got_resync, "no resync packet")

    # ------------------------------------------ 5. absent Origin (P0 red line)
    ok_absent, sid_absent, body_absent = handshake(lb)
    c.check("a no-Origin local client is still allowed", ok_absent, (ok_absent, sid_absent))

    # ------------------------------------------------ 6. shared mode no session
    shared = start("shared", {"LITETASK_DEV_LOGIN": "0"})
    sb = shared["base"]
    ok_s, reason_s, body_s = handshake(sb, origin=sb)
    c.check("shared mode rejects a socket without a session", not ok_s, (ok_s, reason_s))
    c.check("shared-mode rejection names AUTH_REQUIRED",
            "AUTH_REQUIRED" in str(body_s) or "AUTH_REQUIRED" in str(reason_s), (reason_s, body_s))

    # ------------------------------------------ 7. shared mode with a session
    st, login, hdrs = http_at_headers(sb, "POST", "/api/login",
                                      {"username": "admin", "password": "admin"})
    setc = (hdrs.get("Set-Cookie") or hdrs.get("set-cookie") or "")
    cookie = setc.split(";", 1)[0] if "=" in setc else ""
    ok_cookie, sid_cookie, body_cookie = handshake(sb, origin=sb, cookie=cookie)
    c.check("shared mode accepts a valid session", ok_cookie, (st, ok_cookie, sid_cookie))

    # ------------------------------------------------- 8. empty allowlist warning
    c.check("startup says the origin allowlist is empty",
            "Origin whitelist empty" in local["output"], local["output"][-300:])

    # ------------------------------------------------- 9. wildcard invalidated
    wild = start("wild", {"LITETASK_SOCKET_ALLOW_ORIGINS": "https://a.example, *"})
    c.check("a wildcard allowlist is cleared with a warning",
            ("invalid" in wild["output"].lower() and "origin" in wild["output"].lower()), wild["output"][-300:])
    ok_w, _, _ = handshake(wild["base"], origin="https://a.example")
    c.check("a wildcard allowlist does not authorize any origin", not ok_w, ok_w)

    # ----------------------------------------------- 10. exact allowlist works
    exact = start("exact", {"LITETASK_SOCKET_ALLOW_ORIGINS": "https://allowed.example"})
    ok_a, _, _ = handshake(exact["base"], origin="https://allowed.example")
    ok_b, _, _ = handshake(exact["base"], origin="https://other.example")
    c.check("an exact allowlist entry is accepted", ok_a, ok_a)
    c.check("a non-listed origin is still rejected", not ok_b, ok_b)
finally:
    for ctx in (local, shared, wild, exact):
        if ctx and ctx["inst"].get("proc"):
            stop_instance(ctx["inst"]["proc"])
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump({"grader": NAME, "result": "FAIL" if c.failed else "PASS",
                       "checks": c.passed + len(c.failed), "failures": c.failed},
                      f, ensure_ascii=False, indent=2)
    import shutil
    for ctx in (local, shared, wild, exact):
        if ctx:
            shutil.rmtree(ctx["tmp"], ignore_errors=True)

c.finish()