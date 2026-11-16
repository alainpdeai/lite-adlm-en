# -*- coding: utf-8 -*-
"""P2-8 grader: dependency and documentation single source of truth."""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import Checker, ROOT  # noqa: E402

NAME = "p2-doc-consistency"
c = Checker(NAME)
json_out = None
if "--json" in sys.argv:
    i = sys.argv.index("--json")
    if i + 1 < len(sys.argv):
        json_out = sys.argv[i + 1]

pkg = json.load(open(os.path.join(ROOT, "package.json"), encoding="utf-8"))
c.check("package.json no longer depends on cors", "cors" not in pkg.get("dependencies", {}),
        pkg.get("dependencies"))
lock = json.load(open(os.path.join(ROOT, "package-lock.json"), encoding="utf-8"))
root_deps = (lock.get("packages", {}).get("", {}) or {}).get("dependencies", {})
c.check("package-lock root has no direct cors dependency", "cors" not in root_deps,
        root_deps.get("cors"))

blob = ""
for f in [os.path.join(ROOT, "server.js")] + [os.path.join(ROOT, "lib", x)
                                              for x in os.listdir(os.path.join(ROOT, "lib"))
                                              if x.endswith(".js")]:
    blob += open(f, encoding="utf-8", errors="replace").read()
c.check("no source requires cors", "require('cors')" not in blob and 'require("cors")' not in blob)

guide = open(os.path.join(ROOT, "references", "system-guide.md"), encoding="utf-8").read()
c.check("system-guide no longer claims five CDN libraries", "five libraries" not in guide)

c.check("guide records same-origin vendoring", "public/vendor" in guide and "CSP" in guide)

site = json.load(open(os.path.join(ROOT, "config", "site.json"), encoding="utf-8"))
c.check("site.json carries no securityModel key", "securityModel" not in site)

readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
sys.path.insert(0, os.path.join(ROOT, "tests"))
try:
    import run_grade_checks
    n = len(run_grade_checks.FAST_SET)
except Exception:
    n = -1
m = re.search(r"(?:（|\()(\d+)\s*(?:core\s*graders|graders)(?:）|\))", readme, re.I)
c.check("README fast-subset count matches FAST_SET", m and int(m.group(1)) == n, (m.group(1) if m else None, n))
matrix = open(os.path.join(ROOT, "docs", "test_case_matrix.md"), encoding="utf-8").read()
c.check("test matrix records the P2 units", "P2" in matrix or "p2" in matrix)
if json_out:
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump({"grader": NAME, "result": "FAIL" if c.failed else "PASS",
                   "checks": c.passed + len(c.failed), "failures": c.failed},
                  f, ensure_ascii=False, indent=2)
c.finish()