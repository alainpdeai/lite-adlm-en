# -*- coding: utf-8 -*-
"""P2-4 grader: local-only assets, pinned hashes and a CSP with teeth."""
import base64
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import (  # noqa: E402
    Checker, ROOT, copy_data_dir, http_at, http_at_headers, run_instance,
    stop_instance, temp_dir,
)

NAME = "p2-asset-surface"
c = Checker(NAME)
json_out = None
if "--json" in sys.argv:
    i = sys.argv.index("--json")
    if i + 1 < len(sys.argv):
        json_out = sys.argv[i + 1]

HTML = os.path.join(ROOT, "public", "index.html")


def inline_hashes(text):
    out = []
    for m in re.finditer(r"<script\b([^>]*)>([\s\S]*?)</script>", text, re.I):
        if re.search(r"\bsrc\s*=", m.group(1), re.I):
            continue
        out.append("sha256-" + base64.b64encode(
            hashlib.sha256(m.group(2).encode("utf-8")).digest()).decode())
    return sorted(set(out))


ctx = None
try:
    html = open(HTML, encoding="utf-8").read()
    refs = re.findall(r'<(?:link|script)[^>]*?(?:href|src)="([^"]+)"', html)
    external = [u for u in refs if u.startswith(("http://", "https://"))]
    c.check("index.html has zero external resource references", not external, external)
    c.check("socket.io is served locally", any(u.startswith("/socket.io/") for u in refs), refs)

    vendor = [
        "public/vendor/vue/vue.global.prod.js",
        "public/vendor/quill/quill.js",
        "public/vendor/quill/quill.snow.css",
        "public/vendor/fontawesome/css/all.min.css",
        "public/vendor/dompurify/purify.min.js",
        "public/vendor/tailwind/tailwind.css",
        "public/vendor/VENDOR.json",
    ]
    missing = [p for p in vendor if not os.path.isfile(os.path.join(ROOT, p))]
    c.check("all vendored asset classes exist", not missing, missing)
    vue = open(os.path.join(ROOT, vendor[0]), encoding="utf-8", errors="replace").read()
    c.check("Vue is the production build", ".prod." in os.path.basename(vendor[0])
            and "vue-devtools" not in vue.lower() and "development build" not in vue[:400].lower())

    manifest = json.load(open(os.path.join(ROOT, "public/vendor/VENDOR.json"), encoding="utf-8"))
    bad = []
    for a in manifest.get("assets", []):
        p = os.path.join(ROOT, "public", a["path"])
        if not os.path.isfile(p):
            bad.append(a["path"]); continue
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        if h != a["sha256"]:
            bad.append(a["path"])
    c.check("VENDOR.json hashes match every asset", not bad, bad)
    c.check("versions are pinned to x.y.z",
            all(re.fullmatch(r"\d+\.\d+\.\d+", a.get("version", "")) for a in manifest["assets"]),
            [a.get("version") for a in manifest["assets"]])

    maps = [os.path.join(dp, f) for dp, _dn, fs in os.walk(os.path.join(ROOT, "public"))
            for f in fs if f.endswith(".map")]
    c.check("no source maps are shipped", not maps, maps)
    total = sum(os.path.getsize(os.path.join(dp, f))
                for dp, _dn, fs in os.walk(os.path.join(ROOT, "public")) for f in fs)
    c.check("public/ stays under 3 MiB", total <= 3 * 1024 * 1024, total)

    c.check("Python and Node agree on inline hashes",
            inline_hashes(html) == sorted(
                __import__("json").loads(
                    os.popen('node -e "const c=require(\'./lib/csp\');'
                             'const fs=require(\'fs\');'
                             'console.log(JSON.stringify(c.inlineScriptHashes(fs.readFileSync(\'public/index.html\',\'utf8\'))))"').read())),
            inline_hashes(html))
    tampered = html.replace("LiteTask", "LiteTaskX", 1)
    c.check("a single-character edit changes the hash set",
            inline_hashes(tampered) != inline_hashes(html))

    tmp = temp_dir(prefix="lt_p2_asset_")
    data = copy_data_dir(os.path.join(tmp, "inst"))
    inst = run_instance(data, os.path.join(tmp, "backup"), {
        "LITETASK_AUTO_ARCHIVE": "0", "LITETASK_BACKUP_MIRROR": "0",
    }, wait_after_ready=2.0, timeout=60, keep=True)
    ctx = {"inst": inst, "tmp": tmp}
    base = "http://127.0.0.1:%d" % inst["port"]
    st, _, hdrs = http_at_headers(base, "GET", "/")
    h = {k.lower(): v for k, v in hdrs.items()}
    csp = h.get("content-security-policy", "")
    c.check("GET / carries CSP", st == 200 and bool(csp), csp)
    c.check("script-src has no unsafe-inline / wildcard / external host",
            "script-src" in csp
            and "unsafe-inline" not in csp.split("script-src", 1)[1].split(";", 1)[0]
            and "*" not in csp.split("script-src", 1)[1].split(";", 1)[0]
            and "http" not in csp.split("script-src", 1)[1].split(";", 1)[0], csp)
    c.check("CSP carries exactly the inline hashes",
            all(("'%s'" % x) in csp for x in inline_hashes(html)), csp)
    st, _, hdrs2 = http_at_headers(base, "GET", "/api/config")
    c.check("/api/config also carries CSP", "content-security-policy" in
            {k.lower(): v for k, v in hdrs2.items()}, hdrs2)

    for rel, want in (("vendor/vue/vue.global.prod.js", "javascript"),
                      ("vendor/quill/quill.snow.css", "css"),
                      ("vendor/fontawesome/webfonts/fa-solid-900.woff2", "font")):
        st, _, hdrs3 = http_at_headers(base, "GET", "/" + rel)
        ct = {k.lower(): v for k, v in hdrs3.items()}.get("content-type", "")
        c.check("%s is served with %s" % (rel, want), st == 200 and want in ct, (st, ct))
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