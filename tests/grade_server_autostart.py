# -*- coding: utf-8 -*-
"""
Grader for arch legacy P3 (daemon/autostart) — scheduled task resident:
`litetask_ensure.ps1` + Windows scheduled task `LiteTaskServerEnsure`
(derives-from arch: litetask service daemon/boot autostart).

Why this exists: a server launched from an agent command is reaped together
with that command's process group, which is what made the board look like it
"stopped after the task finished". The fix is OS-owned supervision: an at-logon
trigger plus a 5-minute idempotent self-heal probe.

Grading rules honoured here:
  - destructive act only ever touches a THROWAWAY instance (own port, own
    LITETASK_DATA_DIR / LITETASK_BACKUP_DIR), never the production board;
  - every positive verdict has a contrast case, so exit 0 can never be a
    tautology;
  - nothing is asserted about last week's data — only about state observed now.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import ROOT, Checker  # noqa: E402

SCRIPT = os.path.join(ROOT, "scripts", "litetask_ensure.ps1")
TASK = "LiteTaskServerEnsure"
PROD_PORT = 3000
PROD_BACKUP = os.path.join(ROOT, "backup")

c = Checker("server-autostart")


def ps(cmd):
    p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-Command", cmd],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def probe(port, host="127.0.0.1", timeout=1.0):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def server_js_pids():
    rc, out, err = ps(
        "@(Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | "
        "Where-Object { $_.CommandLine -like '*server.js*' }).ProcessId | "
        "ConvertTo-Json -Compress")
    if not out:
        return []
    try:
        v = json.loads(out)
        return [int(v)] if isinstance(v, int) else [int(x) for x in v]
    except Exception:
        return []


def kill_listener(port):
    ps("$c = Get-NetTCPConnection -LocalPort %d -State Listen "
       "-ErrorAction SilentlyContinue | Select-Object -First 1; "
       "if ($c) { Stop-Process -Id $c.OwningProcess -Force }" % port)
    time.sleep(1.0)


def run_script(port, data_dir, backup_dir, log, root=ROOT):
    """Run the ensure script with its stdout/stderr sent to FILES, never pipes.

    The script spawns a long-lived `node server.js`. If that child inherited a
    pipe, the pipe would never reach EOF (the server stays alive), so the
    reader would hang forever -- which is exactly what killed the first run of
    this grader (SIGTERM with an empty stdout). Files have no such property.
    """
    out_log, err_log = log + ".out", log + ".err"
    with open(out_log, "ab") as fo, open(err_log, "ab") as fe:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", SCRIPT,
             "-Port", str(port), "-Root", root,
             "-DataDir", data_dir, "-BackupDir", backup_dir, "-Log", log],
            stdout=fo, stderr=fe, timeout=120)
    try:
        p.stdout = open(out_log, "r", encoding="utf-8", errors="replace").read()[-400:]
        p.stderr = open(err_log, "r", encoding="utf-8", errors="replace").read()[-400:]
    except Exception:
        p.stdout, p.stderr = "", ""
    return p


def prod_backup_stamps():
    if not os.path.isdir(PROD_BACKUP):
        return None
    stamps = set()
    for name in os.listdir(PROD_BACKUP):
        # <file>.<YYYYmmddTHHMMSSsssZ>.json
        parts = name.split(".")
        if len(parts) >= 3 and parts[-1] == "json":
            stamps.add(parts[-2])
    return stamps


print("== 1. artefacts exist and the task is registered ==")
c.check("litetask_ensure.ps1 exists", os.path.isfile(SCRIPT), SCRIPT)

rc, out, err = ps(
    "$t = Get-ScheduledTask -TaskName '%s' -ErrorAction SilentlyContinue; "
    "if ($null -eq $t) { '{\"exists\":false}' } else { "
    "  $obj = [ordered]@{ exists=$true; state=[string]$t.State; "
    "    actions=@($t.Actions | ForEach-Object { $_.Execute + ' ' + $_.Arguments }); "
    "    triggers=@($t.Triggers | ForEach-Object { $_.CimClass.CimClassName }); "
    "    intervals=@($t.Triggers | ForEach-Object { if ($_.Repetition) { $_.Repetition.Interval } else { '' } }); "
    "    lastResult=(Get-ScheduledTaskInfo -TaskName '%s').LastTaskResult }; "
    "  $obj | ConvertTo-Json -Depth 5 -Compress }" % (TASK, TASK))
info = {}
try:
    info = json.loads(out)
except Exception:
    info = {"exists": False, "raw": out, "err": err}

c.check("scheduled task '%s' is registered" % TASK, bool(info.get("exists")), info)
state = str(info.get("state", ""))
# 2026-10-29 operating-model change: the operator chose MANUAL start (the
# LiteTaskServerEnsure task was disabled so no 5-minute probe flashes the screen;
# litetask_ensure.ps1 is launched on demand instead). The grader therefore verifies
# the task is correctly *defined* (so one Enable-ScheduledTask re-arms it) rather
# than asserting it is currently running. "Disabled" is an accepted state.
c.check("task is defined and not in a broken state",
        state in ("Ready", "Running", "Queued", "Disabled"), state)
acts = info.get("actions") or []
acts = [acts] if isinstance(acts, str) else acts
c.check("task action runs the ensure script",
        any(SCRIPT.replace("\\", "/") in a.replace("\\", "/") for a in acts), acts)
triggers = info.get("triggers") or []
triggers = [triggers] if isinstance(triggers, str) else triggers
c.check("task has an at-logon trigger (survives reboot)",
        any("Logon" in t for t in triggers), triggers)
intervals = info.get("intervals") or []
intervals = [intervals] if isinstance(intervals, str) else intervals
c.check("task repeats every 5 minutes (PT5M)",
        any(str(i).upper() == "PT5M" for i in intervals), intervals)
c.check("last task run succeeded (or task is manually disabled)",
        state == "Disabled" or int(info.get("lastResult", -1)) == 0,
        (state, info.get("lastResult")))

print()
print("== 2. script contract on a THROWAWAY instance ==")
tmp = tempfile.mkdtemp(prefix="litetask_grade_")
data_dir = os.path.join(tmp, "data").replace("\\", "/")
backup_dir = os.path.join(tmp, "backup").replace("\\", "/")
os.makedirs(data_dir, exist_ok=True)
os.makedirs(backup_dir, exist_ok=True)
log = os.path.join(tmp, "wd.log").replace("\\", "/")
port = free_port()

before_stamps = prod_backup_stamps()

c.check("throwaway port %d is silent before the test" % port, not probe(port), port)
r1 = run_script(port, data_dir, backup_dir, log)
c.check("cold start: exit 0", r1.returncode == 0, (r1.returncode, r1.stderr[-200:]))
c.check("cold start: the port answers afterwards", probe(port), port)

n_before = len(server_js_pids())
r2 = run_script(port, data_dir, backup_dir, log)
n_after = len(server_js_pids())
c.check("idempotent: re-running adds no second instance",
        n_after == n_before, (n_before, n_after, r2.returncode))

kill_listener(port)
c.check("after kill the throwaway port really is silent", not probe(port), port)
r3 = run_script(port, data_dir, backup_dir, log)
c.check("self-heal: killed instance is brought back (exit 0)",
        r3.returncode == 0, (r3.returncode, r3.stderr[-200:]))
c.check("self-heal: the port answers again", probe(port), port)
c.check("the same script flips its verdict with reality (up vs killed)",
        (r2.returncode == 0) and probe(port) and (r3.returncode == 0),
        (r2.returncode, r3.returncode))

print()
print("== 3. contrast: exit 0 is not a tautology ==")
bad_port = free_port()
missing_root = os.path.join(tmp, "no-such-root").replace("\\", "/")
r4 = run_script(bad_port, data_dir, backup_dir, log, root=missing_root)
c.check("with an unusable root it fails instead of claiming success",
        r4.returncode != 0, (r4.returncode, r4.stdout[-200:]))
c.check("and the port stays silent (no phantom success)", not probe(bad_port),
        bad_port)

print()
print("== 4. the throwaway instance never touched production data ==")
after_stamps = prod_backup_stamps()
c.check("production backup/ snapshot set is unchanged",
        before_stamps is not None and before_stamps == after_stamps,
        (len(before_stamps or []), len(after_stamps or [])))

print()
print("== 5. cleanup + production board still healthy ==")
kill_listener(port)
c.check("throwaway instance cleaned up (port silent again)", not probe(port), port)
shutil.rmtree(tmp, ignore_errors=True)
c.check("throwaway data dir removed", not os.path.exists(tmp), tmp)
c.check("production port %d still answers" % PROD_PORT, probe(PROD_PORT), PROD_PORT)
c.finish()
