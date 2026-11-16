# -*- coding: utf-8 -*-
"""
P1-2 grader: LITETASK_DEV_LOGIN is the only mode switch.

Recorded claims:
  * unset -> local-passwordless, '0' -> shared-authenticated;
  * config/site.json no longer carries securityModel, and init.js neither
    offers nor writes it (two consecutive --defaults runs stay clean);
  * a legacy field is ignored but warned about once, and any value type
    (number/object/null/empty) boots without aborting;
  * install.md says the mode is controlled only by LITETASK_DEV_LOGIN.
"""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (  # noqa: E402
    Checker, ROOT, copy_data_dir, http_at, run_instance, stop_instance, temp_dir,
)

NAME = "p1-mode-source"
c = Checker(NAME)

json_out = None
if "--json" in sys.argv:
    i = sys.argv.index("--json")
    if i + 1 < len(sys.argv):
        json_out = sys.argv[i + 1]


def start(tag, site_doc=None, env_extra=None):
    tmp = temp_dir(prefix="lt_p1_mode_%s_" % tag)
    data = copy_data_dir(os.path.join(tmp, "inst"))
    env = {"LITETASK_AUTO_ARCHIVE": "0", "LITETASK_BACKUP_MIRROR": "0",
           "LITETASK_LOG_DIR": os.path.join(tmp, "logs"),
           "LITETASK_AUDIT_FILE": os.path.join(tmp, "logs", "audit.log")}
    if site_doc is not None:
        site_path = os.path.join(tmp, "site.json")
        with open(site_path, "w", encoding="utf-8") as f:
            json.dump(site_doc, f)
        env["LITETASK_SITE_CONFIG"] = site_path
    env.update(env_extra or {})
    inst = run_instance(data, os.path.join(tmp, "backup"), env,
                        wait_after_ready=2.0, timeout=60, keep=True)
    return {"inst": inst, "tmp": tmp, "base": "http://127.0.0.1:%d" % inst["port"],
            "output": inst["output"]}


local = shared = None
others = []
try:
    # 1. mode flip by the single env switch
    local = start("local", {}, {})
    shared = start("shared", {}, {"LITETASK_DEV_LOGIN": "0"})
    st, cfg = http_at(local["base"], "GET", "/api/config")
    c.check("unset LITETASK_DEV_LOGIN -> passwordless true",
            st == 200 and cfg.get("passwordless") is True, (st, cfg))
    st, cfg = http_at(shared["base"], "GET", "/api/config")
    c.check("LITETASK_DEV_LOGIN=0 -> passwordless false",
            st == 200 and cfg.get("passwordless") is False, (st, cfg))

    # 2. shipped site.json has no dead key
    with open(os.path.join(ROOT, "config", "site.json"), encoding="utf-8") as f:
        shipped = json.load(f)
    c.check("config/site.json has no securityModel key",
            not isinstance(shipped, dict) or "securityModel" not in shipped,
            list(shipped.keys()) if isinstance(shipped, dict) else shipped)

    # 3. init.js no longer offers or writes it
    with open(os.path.join(ROOT, "scripts", "init.js"), encoding="utf-8") as f:
        init_src = f.read()
    defaults_block = re.search(r"const DEFAULTS\s*=\s*\{(.*?)\n\};", init_src, re.S)
    prompts_block = re.search(r"const PROMPTS\s*=\s*\[(.*?)\n\];", init_src, re.S)
    c.check("init.js DEFAULTS/PROMPTS do not contain securityModel",
            (defaults_block is None or "securityModel" not in defaults_block.group(1))
            and (prompts_block is None or "securityModel" not in prompts_block.group(1)),
            "securityModel still in defaults/prompts")

    # 4. two consecutive --defaults runs stay clean (isolated copy)
    t4 = temp_dir(prefix="lt_p1_init_")
    copy_root = os.path.join(t4, "repo")
    shutil.copytree(os.path.join(ROOT, "scripts"), os.path.join(copy_root, "scripts"))
    shutil.copytree(os.path.join(ROOT, "config"), os.path.join(copy_root, "config"))
    r1 = subprocess.run(["node", "scripts/init.js", "--defaults"], cwd=copy_root,
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    r2 = subprocess.run(["node", "scripts/init.js", "--defaults"], cwd=copy_root,
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        with open(os.path.join(copy_root, "config", "site.json"), encoding="utf-8") as f:
            generated = json.load(f)
        clean = "securityModel" not in generated
    except Exception:
        clean = False
    c.check("two init --defaults runs exit 0", r1.returncode == 0 and r2.returncode == 0,
            (r1.returncode, r2.returncode, (r1.stderr or "")[:120]))
    c.check("init --defaults does not resurrect securityModel", clean, "key present")
    shutil.rmtree(t4, ignore_errors=True)

    # 5/6. legacy field is ignored AND warned about
    legacy = start("legacy", {"securityModel": "password"}, {})
    others.append(legacy)
    st, lcfg = http_at(legacy["base"], "GET", "/api/config")
    c.check("legacy securityModel is ignored (still local passwordless)",
            st == 200 and lcfg.get("passwordless") is True, (st, lcfg))
    c.check("startup warns about the dead field once",
            "deprecated fields" in legacy["output"].lower() and "securityModel" in legacy["output"],
            legacy["output"][-300:])
    c.check("warning names the real switch LITETASK_DEV_LOGIN",
            "LITETASK_DEV_LOGIN" in legacy["output"], legacy["output"][-300:])

    # 7. invalid value types do not abort startup
    ok_types = True
    for value in (123, {"nested": True}, None, ""):
        inst = start("badtype", {"securityModel": value}, {})
        others.append(inst)
        st, _ = http_at(inst["base"], "GET", "/api/config")
        if st != 200 or not inst["inst"]["ready"] or "deprecated fields" not in inst["output"].lower():
            ok_types = False
    c.check("number/object/null/empty legacy values all boot with a warning", ok_types)

    # 8. env wins over a legacy site value
    conflict = start("conflict", {"securityModel": "passwordless-local"},
                     {"LITETASK_DEV_LOGIN": "0"})
    others.append(conflict)
    st, ccfg = http_at(conflict["base"], "GET", "/api/config")
    c.check("LITETASK_DEV_LOGIN=0 wins over site.json", st == 200 and ccfg.get("passwordless") is False,
            (st, ccfg))

    # 9. no second mode source
    with open(os.path.join(ROOT, "lib", "config.js"), encoding="utf-8") as f:
        cfg_src = f.read()
    line = re.search(r"const PASSWORDLESS_LOCAL\s*=\s*([^;]+);", cfg_src)
    c.check("PASSWORDLESS_LOCAL is derived only from LITETASK_DEV_LOGIN",
            line is not None and "LITETASK_DEV_LOGIN" in line.group(1)
            and "LITETASK_SITE_CONFIG" not in line.group(1)
            and "LITETASK_DRILL_FAULT" not in line.group(1),
            line.group(1) if line else "definition not found")

    # 10. install.md: no field, explicit single-switch statement
    with open(os.path.join(ROOT, "install.md"), encoding="utf-8") as f:
        install = f.read()
    c.check("install.md no longer documents securityModel as a configurable field",
            re.search(r'"securityModel"\s*:|`securityModel`\s*\|', install) is None,
            "field still documented as configurable")
    c.check("install.md states the mode is controlled only by LITETASK_DEV_LOGIN",
            "LITETASK_DEV_LOGIN" in install and re.search(r"controlled [^\n]{0,20}by [`]?LITETASK_DEV_LOGIN|sole switch", install) is not None,
            "single-switch wording missing")
finally:
    for ctx in [local, shared] + others:
        if ctx and ctx["inst"].get("proc"):
            stop_instance(ctx["inst"]["proc"])
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump({"grader": NAME, "result": "FAIL" if c.failed else "PASS",
                       "checks": c.passed + len(c.failed), "failures": c.failed},
                      f, ensure_ascii=False, indent=2)
    for ctx in [local, shared] + others:
        if ctx:
            shutil.rmtree(ctx["tmp"], ignore_errors=True)

c.finish()