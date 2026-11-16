# -*- coding: utf-8 -*-
"""
P1-1 grader: /api/config is the single, complete, credential-free contract.

P1-1 was already fixed during P0; this file is a regression guard, not a bug
driver. Three layers:

  * static  — exactly one `app.get('/api/config'` in server.js + lib/*.js;
  * runtime — seven keys, three values flipping between local and shared mode,
              config<->health deep equality, credential-free raw response;
  * UI      — passwordless / securityModel label+hint / requiresPassword branch,
              and no "missing field means passwordless" fallback.
"""
import copy
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (  # noqa: E402
    Checker, ROOT, copy_data_dir, http_at, http_at_headers,
    run_instance, stop_instance, temp_dir,
)

NAME = "p1-config-contract"
c = Checker(NAME)

json_out = None
if "--json" in sys.argv:
    i = sys.argv.index("--json")
    if i + 1 < len(sys.argv):
        json_out = sys.argv[i + 1]

KEYS = ["projectName", "subtitle", "loginSubtitle", "goal",
        "devAutoLogin", "passwordless", "securityModel"]


def start(tag, env_extra):
    tmp = temp_dir(prefix="lt_p1_cfg_%s_" % tag)
    data = copy_data_dir(os.path.join(tmp, "inst"))
    env = {"LITETASK_AUTO_ARCHIVE": "0", "LITETASK_BACKUP_MIRROR": "0",
           "LITETASK_LOG_DIR": os.path.join(tmp, "logs"),
           "LITETASK_AUDIT_FILE": os.path.join(tmp, "logs", "audit.log")}
    env.update(env_extra or {})
    inst = run_instance(data, os.path.join(tmp, "backup"), env,
                        wait_after_ready=2.0, timeout=60, keep=True)
    return {"inst": inst, "tmp": tmp,
            "base": "http://127.0.0.1:%d" % inst["port"]}


def deep_equal(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


local = shared = None
try:
    # ---------------------------------------------------------- static layer
    hits = []
    for f in [os.path.join(ROOT, "server.js")] + glob.glob(os.path.join(ROOT, "lib", "*.js")):
        with open(f, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        n = text.count("app.get('/api/config'") + text.count('app.get("/api/config"')
        if n:
            hits.append((os.path.relpath(f, ROOT), n))
    total = sum(n for _, n in hits)
    c.check("exactly one /api/config registration", total == 1, hits)
    c.check("the single registration is lib/logging.js",
            len(hits) == 1 and hits[0][0].replace("\\", "/") == "lib/logging.js", hits)

    # --------------------------------------------------------- runtime layer
    local = start("local", {})
    lb = local["base"]
    c.check("local instance started", local["inst"]["ready"], local["inst"]["output"][-300:])
    st, cfg, _ = http_at_headers(lb, "GET", "/api/config")
    c.check("local /api/config answers 200", st == 200, st)
    missing = [k for k in KEYS if not isinstance(cfg, dict) or k not in cfg]
    c.check("all seven keys are present", not missing, missing)
    c.check("local mode is passwordless + devAutoLogin",
            cfg.get("passwordless") is True and cfg.get("devAutoLogin") is True, cfg)
    c.check("local securityModel.mode is local-passwordless",
            (cfg.get("securityModel") or {}).get("mode") == "local-passwordless", cfg)

    st, health = http_at(lb, "GET", "/api/health")
    mode = (health or {}).get("mode") or {}
    c.check("config.securityModel deep-equals health.mode.securityModel",
            deep_equal(cfg.get("securityModel"), mode.get("securityModel")),
            (cfg.get("securityModel"), mode.get("securityModel")))
    c.check("config.passwordless equals health.mode.passwordless",
            cfg.get("passwordless") == mode.get("passwordless"),
            (cfg.get("passwordless"), mode.get("passwordless")))

    raw = json.dumps(cfg, ensure_ascii=False)
    c.check("config response carries no credential material",
            "scrypt$" not in raw and "lt_session" not in raw and '"password"' not in raw,
            "credential-like material found")

    # ----------------------------------------------------------- shared mode
    shared = start("shared", {"LITETASK_DEV_LOGIN": "0"})
    sb = shared["base"]
    c.check("shared instance started", shared["inst"]["ready"], shared["inst"]["output"][-300:])
    st, scfg = http_at(sb, "GET", "/api/config")
    c.check("shared mode flips passwordless/devAutoLogin to false",
            scfg.get("passwordless") is False and scfg.get("devAutoLogin") is False, scfg)
    c.check("shared securityModel.mode is shared-authenticated",
            (scfg.get("securityModel") or {}).get("mode") == "shared-authenticated", scfg)
    c.check("both modes still return all seven keys",
            all(k in scfg for k in KEYS), [k for k in KEYS if k not in scfg])

    # ------------------------------------------------------------- UI layer
    with open(os.path.join(ROOT, "public", "index.html"), encoding="utf-8") as fh:
        html = fh.read()
    c.check("UI reads cfg.passwordless", "passwordless" in html and "/api/config" in html)
    c.check("UI renders securityModel.label", re.search(r"securityModel[^\n]{0,80}\.label", html) is not None or "securityModel.label" in html)
    c.check("UI renders securityModel.hint", "securityModel.hint" in html or re.search(r"securityModel[^\n]{0,80}\.hint", html) is not None)
    c.check("UI branches on requiresPassword or mode",
            "securityModel.requiresPassword" in html or re.search(r"securityModel\.mode\s*===", html) is not None)
    c.check("password input is bound to passwordless", re.search(r"passwordless", html) is not None and re.search(r":required", html) is not None)
    dangerous = re.search(r"passwordless\s*(\?\?\s*true|===\s*undefined\s*\?\s*true|\|\|\s*true)", html)
    c.check("no 'missing passwordless means true' fallback", dangerous is None, dangerous.group(0) if dangerous else "")
finally:
    for ctx in (local, shared):
        if ctx and ctx["inst"].get("proc"):
            stop_instance(ctx["inst"]["proc"])
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump({"grader": NAME, "result": "FAIL" if c.failed else "PASS",
                       "checks": c.passed + len(c.failed), "failures": c.failed},
                      f, ensure_ascii=False, indent=2)
    import shutil
    for ctx in (local, shared):
        if ctx:
            shutil.rmtree(ctx["tmp"], ignore_errors=True)

c.finish()