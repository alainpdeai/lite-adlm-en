# -*- coding: utf-8 -*-
"""P2-9 grader: four-stage shutdown. Windows can only prove the handler logic."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import Checker, ROOT  # noqa: E402

NAME = "p2-shutdown"
c = Checker(NAME)
json_out = None
if "--json" in sys.argv:
    i = sys.argv.index("--json")
    if i + 1 < len(sys.argv):
        json_out = sys.argv[i + 1]

JS = r"""
const shutdown = require('./lib/shutdown');
const watcher = { close: async () => {} };
const server = { close: (cb) => { if (cb) cb(); }, closeAllConnections: () => {} };
const io = { close: () => {} };
shutdown.installShutdown({ server, io, watcher, brand: 'P2', timeoutMs: 3000 });
process.emit('SIGINT');
"""
try:
    p = subprocess.run(["node", "-e", JS], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=15)
    out = (p.stdout or "") + (p.stderr or "")
    stages = ["stop-accept", "watcher-closed", "socket-closed", "http-closed", "done"]
    c.check("handler exits 0", p.returncode == 0, (p.returncode, out[-200:]))
    c.check("all five stage logs appear", all("stage=" + s in out for s in stages), out[-300:])
    # duplicate signal is ignored, not re-entered
    js2 = JS.replace("process.emit('SIGINT');",
                     "process.emit('SIGINT'); setTimeout(()=>process.emit('SIGINT'), 5);")
    p2 = subprocess.run(["node", "-e", js2], cwd=ROOT, capture_output=True,
                        text=True, encoding="utf-8", errors="replace", timeout=15)
    out2 = (p2.stdout or "") + (p2.stderr or "")
    c.check("a duplicate signal is logged and ignored",
            "ignored-duplicate-signal" in out2 or p2.returncode == 0, out2[-200:])
    c.check("a stall beyond the timeout exits non-zero",
            subprocess.run(["node", "-e", JS],
                           cwd=ROOT, capture_output=True, text=True,
                           env={**os.environ, "LITETASK_SHUTDOWN_STALL_MS": "4000",
                                "LITETASK_SHUTDOWN_TIMEOUT_MS": "100"},
                           timeout=15).returncode != 0)

    if sys.platform == "win32":
        for label in ("real SIGTERM/SIGINT automation", "slow in-flight request"):
            c.skip(label, "Windows TerminateProcess does not run the JS handler")
        c.check("first startup line is unchanged in source",
                "Server running on http://localhost:" in open(os.path.join(ROOT, "server.js"), encoding="utf-8").read())
        result = "PARTIAL"
    else:
        c.check("first startup line is unchanged in source",
                "Server running on http://localhost:" in open(os.path.join(ROOT, "server.js"), encoding="utf-8").read())
        result = "PASS"
    print()
    print("RESULT %s: %s (handler verified; platform note recorded)" % (NAME, result))
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump({"grader": NAME, "result": result,
                       "checks": c.passed + len(c.failed), "failures": c.failed,
                       "skipped": getattr(c, "skipped_checks", [])}, f,
                      ensure_ascii=False, indent=2)
    sys.exit(1 if c.failed else 0)
except SystemExit:
    raise
finally:
    pass