# -*- coding: utf-8 -*-
"""
Grader for func item server ensure/status subcommand (Core Features)
(derives-from arch legacy P3: litetask service daemon/boot autostart,
 task_17932250668320f4fd5).

Recorded claim: `server --action status` is a pure probe — exit 0 and
"[server] RUNNING" when the port answers, exit 1 and "[server] DOWN" when it
does not — and it NEVER launches a server. `server --action ensure` against an
already-up port is a no-op: exit 0, RUNNING, and no "launching" line (it never
clobbers or duplicates a live instance).
"""
import os
import socket
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import ROOT, Checker  # noqa: E402

CLI = os.path.join(ROOT, "scripts", "litetask_cli.py")
c = Checker("server-subcommand")


def cli(*argv):
    p = subprocess.run([sys.executable, CLI, *argv],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


print("== status against the live server (default port 3000) ==")
rc, out = cli("server", "--action", "status")
c.check("status on a live port exits 0", rc == 0, (rc, out[-200:]))
c.check("it reports RUNNING", "[server] RUNNING" in out, out[-200:])

print()
print("== status against a dead port is a truthful DOWN, never a launch ==")
dead = free_port()
rc2, out2 = cli("server", "--action", "status", "--port", str(dead))
c.check("status on a dead port exits non-zero", rc2 != 0, (rc2, out2[-200:]))
c.check("it reports DOWN", "[server] DOWN" in out2, out2[-200:])
c.check("status never launches a server", "launching" not in out2, out2[-200:])

print()
print("== the probe follows reality, not a constant (live vs dead contrast) ==")
c.check("same command flips its verdict with the port state",
        (rc == 0) != (rc2 == 0), (rc, rc2))

print()
print("== ensure against the live port is a no-op ==")
rc3, out3 = cli("server", "--action", "ensure")
c.check("ensure on a live port exits 0", rc3 == 0, (rc3, out3[-200:]))
c.check("ensure reports RUNNING", "[server] RUNNING" in out3, out3[-200:])
c.check("ensure did not try to launch a second instance",
        "launching" not in out3, out3[-200:])

print()
print("== the live server is still the same one afterwards ==")
rc4, out4 = cli("server", "--action", "status")
c.check("still RUNNING after the ensure no-op", rc4 == 0 and "[server] RUNNING" in out4,
        out4[-200:])
c.finish()
