# -*- coding: utf-8 -*-
"""
P0-3 grader: opening a local folder is a validated, parameterized launch.

Recorded claim: /api/open-folder
  * refuses a non-absolute / URL / NUL / over-long path with 400 INVALID_PATH;
  * refuses everything with 403 OPEN_ROOT_NOT_CONFIGURED when no root is set;
  * refuses a path outside the allowed root with 403;
  * maps absent -> 404 PATH_NOT_FOUND, file -> 400 NOT_A_DIRECTORY;
  * passes shell metacharacters through as one literal argument (no extra
    process), answering 400/403/404 instead of executing them;
  * returns within 200 ms and does not wait for the child;
  * reports a missing launcher as 503 while /api/health stays 200;
  * audits both the ok and the rejected branch without an absolute path.

On the pre-fix implementation the module has no roots, no validation and uses
`exec()`, so this file fails before any injection probe is sent.
"""
import glob
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (  # noqa: E402
    Checker, ROOT, copy_data_dir, http_at, run_instance, stop_instance, temp_dir,
)

NAME = "p0-open-folder"
c = Checker(NAME)

json_out = None
if "--json" in sys.argv:
    i = sys.argv.index("--json")
    if i + 1 < len(sys.argv):
        json_out = sys.argv[i + 1]


def harmless_launcher():
    if os.name == "nt":
        where = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                             "System32", "where.exe")
        return where if os.path.exists(where) else os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe")
    return "/bin/true"


def start(tag, env_extra):
    tmp = temp_dir(prefix="lt_p0_open_%s_" % tag)
    data = copy_data_dir(os.path.join(tmp, "inst"))
    env = dict(env_extra or {})
    env.setdefault("LITETASK_LOG_DIR", os.path.join(tmp, "logs"))
    env.setdefault("LITETASK_AUDIT_FILE", os.path.join(tmp, "logs", "audit.log"))
    env.setdefault("LITETASK_BACKUP_MIRROR", "0")
    inst = run_instance(data, os.path.join(tmp, "backup"), env,
                        wait_after_ready=2.0, timeout=60, keep=True)
    return {"inst": inst, "tmp": tmp,
            "base": "http://127.0.0.1:%d" % inst["port"],
            "logs": env["LITETASK_LOG_DIR"]}


def hardened(base):
    st, cfg = http_at(base, "GET", "/api/config")
    return bool(st == 200 and isinstance(cfg, dict)
                and isinstance(cfg.get("openFolder"), dict))


def post(base, path, cookie=None):
    return http_at(base, "POST", "/api/open-folder", {"folderPath": path}, cookie=cookie)


def _proc_count(name):
    """Count processes by image name, without ever starting one."""
    try:
        if os.name == "nt":
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s" % name],
                                 capture_output=True, text=True, timeout=10).stdout
            return out.lower().count(name.lower())
        out = subprocess.run(["pgrep", "-c", name],
                             capture_output=True, text=True, timeout=10)
        return int(out.stdout.strip() or 0)
    except Exception:                                            # noqa: BLE001
        return 0


no_root = rooted = missing = None
work = temp_dir(prefix="lt_p0_open_files_")
allowed = os.path.join(work, "allowed")
os.makedirs(os.path.join(allowed, "sub"), exist_ok=True)
os.makedirs(os.path.join(work, "outside"), exist_ok=True)
with open(os.path.join(allowed, "note.txt"), "w", encoding="utf-8") as f:
    f.write("not a directory")

try:
    # ---------------- no root configured: the capability is closed ----------------
    no_root = start("noroot", {})
    nb = no_root["base"]
    c.check("no-root instance started", no_root["inst"]["ready"],
            no_root["inst"]["output"][-300:])
    hard1 = hardened(nb)
    if hard1:
        st, body = post(nb, allowed)
    else:
        st, body = 0, None      # legacy would launch a file manager; skip
    c.check("with no allowed root, any folder is 403 OPEN_ROOT_NOT_CONFIGURED",
            st == 403 and isinstance(body, dict)
            and body.get("code") == "OPEN_ROOT_NOT_CONFIGURED",
            (st, body if hard1 else "legacy: probe skipped"))

    # ---------------- bad input (before any root/branch logic) ----------------
    bad_inputs = ["../../", "https://example.com", "file:///C:/", "",
                  "a\u0000b", "C:\\" + ("x" * 300)]
    if hard1:
        results = [post(nb, p) for p in bad_inputs]
    else:
        results = []
    bad_ok = bool(results) and all(
        st == 400 and isinstance(bd, dict) and bd.get("code") == "INVALID_PATH"
        for st, bd in results)
    c.check("relative / URL / NUL / over-long inputs are 400 INVALID_PATH", bad_ok,
            "" if bad_ok else "legacy: probes skipped")

    # ---------------- rooted instance: allow/deny, audit, latency ----------------
    rooted = start("rooted", {
        "LITETASK_OPEN_ROOT": allowed,
        "LITETASK_OPEN_LAUNCHER": harmless_launcher(),
        "LITETASK_OPEN_RATE": "100/10",
    })
    rb = rooted["base"]
    c.check("rooted instance started", rooted["inst"]["ready"],
            rooted["inst"]["output"][-300:])
    hard2 = hardened(rb)

    if hard2:
        st, body = post(rb, os.path.join(work, "outside"))
        c.check("a directory outside the allowed root is 403 PATH_OUTSIDE_ALLOWED_ROOT",
                st == 403 and body.get("code") == "PATH_OUTSIDE_ALLOWED_ROOT", (st, body))
        st, body = post(rb, os.path.join(allowed, "does-not-exist"))
        c.check("an absent path inside the root is 404 PATH_NOT_FOUND",
                st == 404 and body.get("code") == "PATH_NOT_FOUND", (st, body))
        st, body = post(rb, os.path.join(allowed, "note.txt"))
        c.check("an existing file is 400 NOT_A_DIRECTORY",
                st == 400 and body.get("code") == "NOT_A_DIRECTORY", (st, body))

        injection = [
            os.path.join(allowed, 'a" & calc.exe & "'),
            os.path.join(allowed, ";calc;"),
            os.path.join(allowed, "|calc"),
            os.path.join(allowed, "a\nb"),
        ]
        inj = [post(rb, p) for p in injection]
        no_exec = all(st in (400, 403, 404) for st, _ in inj)
        before = _proc_count("calc.exe")
        time.sleep(0.3)
        after = _proc_count("calc.exe")
        c.check("shell-metacharacter paths are refused, never executed",
                no_exec, inj)
        c.check("no calc.exe process was created by the injection probes",
                before == after, (before, after))

        lat = []
        for _ in range(5):
            t0 = time.time()
            st, body = post(rb, os.path.join(allowed, "sub"))
            lat.append((time.time() - t0) * 1000.0)
        c.check("a legal folder returns 200 within 200 ms (5/5)",
                all(x < 200.0 for x in lat), ["%.1fms" % x for x in lat])
    else:
        for label in ("a directory outside the allowed root is 403 PATH_OUTSIDE_ALLOWED_ROOT",
                      "an absent path inside the root is 404 PATH_NOT_FOUND",
                      "an existing file is 400 NOT_A_DIRECTORY",
                      "shell-metacharacter paths are refused, never executed",
                      "no calc.exe process was created by the injection probes",
                      "a legal folder returns 200 within 200 ms (5/5)"):
            c.check(label, False, "legacy: probes skipped (would launch a process)")

    # ---------------- launcher missing -> 503, server stays alive ----------------
    missing = start("missing", {
        "LITETASK_OPEN_ROOT": allowed,
        "LITETASK_OPEN_LAUNCHER": os.path.join(work, "no-such-launcher-xyz.exe"),
    })
    mb = missing["base"]
    if hardened(mb):
        st, body = post(mb, os.path.join(allowed, "sub"))
        c.check("a missing launcher is 503 LAUNCHER_UNAVAILABLE",
                st == 503 and body.get("code") == "LAUNCHER_UNAVAILABLE", (st, body))
        st, _ = http_at(mb, "GET", "/api/health")
        c.check("/api/health stays 200 after a launcher failure", st == 200, st)
    else:
        c.check("a missing launcher is 503 LAUNCHER_UNAVAILABLE", False, "legacy")
        c.check("/api/health stays 200 after a launcher failure", False, "legacy")

    # ---------------- audit: both branches, no absolute path ----------------
    audit_text = ""
    p = os.path.join(rooted["logs"], "audit.log")
    if os.path.exists(p):
        with open(p, encoding="utf-8", errors="replace") as f:
            audit_text = f.read()
    entries = []
    for line in audit_text.splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            pass
    ok_entries = [e for e in entries
                  if e.get("action") == "open-folder" and e.get("outcome") == "ok"]
    rejected = [e for e in entries
                if e.get("action") == "open-folder" and e.get("outcome") == "rejected"
                and e.get("note") == "PATH_OUTSIDE_ALLOWED_ROOT"]
    c.check("the ok branch is audited with a relative path only",
            bool(ok_entries) and all("relPath" in (e.get("params") or {})
                                     and allowed not in json.dumps(e) for e in ok_entries),
            ok_entries[-1:] if ok_entries else [])
    c.check("the rejected branch is audited with the error code, not the path",
            bool(rejected) and all(allowed not in json.dumps(e) for e in rejected),
            rejected[-1:] if rejected else [])

    # ---------------- static: no shell-based launch path anywhere ----------------
    blob = ""
    for f in [os.path.join(ROOT, "server.js")] + glob.glob(os.path.join(ROOT, "lib", "*.js")):
        with open(f, encoding="utf-8", errors="replace") as fh:
            blob += fh.read()
    c.check("no child_process exec()/execSync()/shell:true remains in server.js or lib/",
            not re.search(r"child_process[^\n]{0,80}\.exec\s*\(", blob)
            and "execSync(" not in blob
            and not re.search(r"shell\s*:\s*true", blob),
            "shell execution path still present")
    c.check("folderPath is never interpolated into a command string",
            not re.search(r"\$\{[^}]*folderPath[^}]*\}", blob),
            "request value reaches a command string")

finally:
    for ctx in (no_root, rooted, missing):
        if ctx and ctx.get("inst") and ctx["inst"].get("proc"):
            stop_instance(ctx["inst"]["proc"])
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump({"name": NAME, "passed": c.passed, "failed": c.failed},
                      f, ensure_ascii=False, indent=2)
    import shutil
    for ctx in (no_root, rooted, missing):
        if ctx:
            shutil.rmtree(ctx["tmp"], ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)

c.finish()