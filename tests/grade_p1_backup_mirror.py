# -*- coding: utf-8 -*-
"""
P1-6 grader: the backup mirror is off by default and never writes into the
developer's profile without an explicit absolute opt-in.

Safety rule (mandatory): HOME / USERPROFILE / LOCALAPPDATA are redirected to a
throwaway directory before any instance starts, because the pre-fix code falls
back to the real user profile when the variable is unset or empty. Without the
redirect this grader would itself create the leak it is testing for.
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (  # noqa: E402
    Checker, ROOT, copy_data_dir, http_at, run_instance, stop_instance, temp_dir,
)

NAME = "p1-backup-mirror"
c = Checker(NAME)

json_out = None
if "--json" in sys.argv:
    i = sys.argv.index("--json")
    if i + 1 < len(sys.argv):
        json_out = sys.argv[i + 1]

FAKE_HOME = temp_dir(prefix="lt_p1_fakehome_")
PROJECT_PROBE = os.path.join(ROOT, "tests", "_artifacts", "p1_mirror_probe")
REL_PROBE = os.path.join(ROOT, "tests", "_artifacts", "p1_mirror_rel")


def safe_env(extra=None):
    env = {
        "HOME": FAKE_HOME,
        "USERPROFILE": FAKE_HOME,
        "LOCALAPPDATA": os.path.join(FAKE_HOME, "AppData", "Local"),
        "LITETASK_AUTO_ARCHIVE": "0",
        "LITETASK_BACKUP_MIRROR": "",
        "LITETASK_BACKUP_DIR": "",
    }
    env.update(extra or {})
    return env


def default_mirror_dir():
    if os.name == "nt":
        return os.path.join(FAKE_HOME, "AppData", "Local", "LiteTask", "backup-mirror")
    return os.path.join(FAKE_HOME, ".local", "state", "litetask", "backup-mirror")


def files_under(root):
    out = []
    if not os.path.isdir(root):
        return out
    for dp, _dn, fs in os.walk(root):
        for f in fs:
            out.append(os.path.relpath(os.path.join(dp, f), root).replace("\\", "/"))
    return sorted(out)


def snapshot_profile():
    return files_under(FAKE_HOME)


def start(tag, env_extra):
    tmp = temp_dir(prefix="lt_p1_mirror_%s_" % tag)
    data = copy_data_dir(os.path.join(tmp, "inst"))
    logs = os.path.join(tmp, "logs")
    env = safe_env(env_extra)
    env["LITETASK_LOG_DIR"] = logs
    env["LITETASK_AUDIT_FILE"] = os.path.join(logs, "audit.log")
    # LITETASK_BACKUP_DIR from safe_env would point at CWD; always isolate it.
    env["LITETASK_BACKUP_DIR"] = os.path.join(tmp, "backup")
    inst = run_instance(data, env["LITETASK_BACKUP_DIR"], env,
                        wait_after_ready=2.0, timeout=60, keep=True)
    return {"inst": inst, "tmp": tmp, "base": "http://127.0.0.1:%d" % inst["port"],
            "backup": env["LITETASK_BACKUP_DIR"], "data": data,
            "output": inst["output"], "logs": logs}


ctxs = []
try:
    # ------------------------------------------------- 1. default: off, zero writes
    before = snapshot_profile()
    default = start("default", {})
    ctxs.append(default)
    after = snapshot_profile()
    dm = default_mirror_dir()
    c.check("default start creates no mirror under the profile",
            after == before, [p for p in after if p not in before][:5])
    c.check("default start does not create the legacy default mirror directory",
            not os.path.exists(dm), dm)
    st, health = http_at(default["base"], "GET", "/api/health")
    mirror = (health or {}).get("mirror") or {}
    c.check("health.mirror.enabled is false by default", mirror.get("enabled") is False, mirror)
    c.check("health.mirror.dir is null by default", mirror.get("dir") is None, mirror)
    c.check("health.mirror.reason is 'unset'", mirror.get("reason") == "unset", mirror)
    c.check("health.mirror.lastAttempt exists and is null",
            "lastAttempt" in mirror and mirror.get("lastAttempt") is None, mirror)
    c.check("startup says the mirror is off by default",
            "Mirror backup disabled by default" in default["output"], default["output"][-300:])
    c.check("primary backup still ran", "Startup backup" in default["output"],
            default["output"][-300:])

    # ---------------------------------------------------- 2. four off spellings
    off_ok = True
    for value in ("0", "off", "False", "none"):
        inst = start("off_%s" % value.lower(), {"LITETASK_BACKUP_MIRROR": value})
        ctxs.append(inst)
        st, h = http_at(inst["base"], "GET", "/api/health")
        m = (h or {}).get("mirror") or {}
        if m.get("enabled") is not False or files_under(dm) != [] or os.path.exists(dm):
            off_ok = False
    c.check("0/off/false/none all disable the mirror without falling back",
            off_ok, "one value fell back to the default path")

    # ------------------------------------------------------- 3. explicit mirror
    explicit = os.path.join(FAKE_HOME, "mirror-explicit")
    exp = start("explicit", {"LITETASK_BACKUP_MIRROR": explicit})
    ctxs.append(exp)
    mirrored = files_under(explicit)
    backed = files_under(exp["backup"])
    c.check("explicit absolute mirror receives the same relative path set as backup/",
            bool(mirrored) and mirrored == backed, (mirrored[:3], backed[:3]))
    c.check("explicit mirror includes the user store (mirror completeness kept)",
            any(os.path.basename(p).startswith("users.") for p in mirrored), mirrored[:4])
    st, h = http_at(exp["base"], "GET", "/api/health")
    m = (h or {}).get("mirror") or {}
    c.check("health reports the explicit mirror enabled with its dir",
            m.get("enabled") is True and m.get("dir") == explicit and m.get("reason") == "explicit", m)

    # ------------------------------------------------- 4. project-internal reject
    shutil.rmtree(PROJECT_PROBE, ignore_errors=True)
    proj = start("inside", {"LITETASK_BACKUP_MIRROR": PROJECT_PROBE})
    ctxs.append(proj)
    st, h = http_at(proj["base"], "GET", "/api/health")
    m = (h or {}).get("mirror") or {}
    c.check("a mirror inside the project tree is rejected",
            m.get("enabled") is False, m)
    c.check("project-internal mirror leaves no files in the project",
            not os.path.exists(PROJECT_PROBE) or files_under(PROJECT_PROBE) == [],
            files_under(PROJECT_PROBE)[:4])
    c.check("startup warns that the mirror config is invalid",
            "inside-project" in proj["output"] or "invalid" in proj["output"].lower(),
            proj["output"][-300:])

    # ------------------------------------------------------ 5. relative rejected
    shutil.rmtree(REL_PROBE, ignore_errors=True)
    rel_value = "tests/_artifacts/p1_mirror_rel"
    rel = start("relative", {"LITETASK_BACKUP_MIRROR": rel_value})
    ctxs.append(rel)
    st, h = http_at(rel["base"], "GET", "/api/health")
    m = (h or {}).get("mirror") or {}
    c.check("a relative mirror path is rejected", m.get("enabled") is False, m)
    c.check("relative mirror writes nothing", not os.path.exists(REL_PROBE), REL_PROBE)

    # -------------------------------------------------- 6. permissions / profile
    if os.name != "nt":
        mode = os.stat(explicit).st_mode & 0o777
        c.check("POSIX mirror root mode is 0700", mode == 0o700, oct(mode))
    else:
        c.check("Windows mirror root sits under the user profile",
                os.path.realpath(explicit).startswith(os.path.realpath(FAKE_HOME)), explicit)

    # ------------------------------------------------------- 7. layout unchanged
    c.check("backup/ keeps <dir>/<name>.<stamp>.json naming",
            all("." in os.path.basename(p) and p.endswith(".json") for p in backed), backed[:3])
    hist = os.path.join(FAKE_HOME, "history-mirror", "keep.me.20200101T000000000Z.json")
    os.makedirs(os.path.dirname(hist), exist_ok=True)
    with open(hist, "w", encoding="utf-8") as f:
        f.write('{"old":true}')
    hist_mtime = os.path.getmtime(hist)
    start("history", {"LITETASK_BACKUP_MIRROR": ""})
    c.check("a pre-existing mirror file is not deleted or updated",
            os.path.exists(hist) and os.path.getmtime(hist) == hist_mtime, hist)
finally:
    for ctx in ctxs:
        if ctx and ctx["inst"].get("proc"):
            stop_instance(ctx["inst"]["proc"])
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump({"grader": NAME, "result": "FAIL" if c.failed else "PASS",
                       "checks": c.passed + len(c.failed), "failures": c.failed},
                      f, ensure_ascii=False, indent=2)
    for ctx in ctxs:
        if ctx:
            shutil.rmtree(ctx["tmp"], ignore_errors=True)
    shutil.rmtree(FAKE_HOME, ignore_errors=True)
    shutil.rmtree(PROJECT_PROBE, ignore_errors=True)
    shutil.rmtree(REL_PROBE, ignore_errors=True)

c.finish()