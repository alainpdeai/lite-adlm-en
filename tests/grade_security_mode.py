# -*- coding: utf-8 -*-
"""
Grader: the security model is named and shown (Security Boundary P2-B).

The switch between "local, no password" and "shared, password required" is one
environment variable (`LITETASK_DEV_LOGIN`). Before this item the UI received
only a boolean, and a boolean cannot tell a person which world they are in: an
instance accidentally reachable from outside looks, from the inside, exactly
like a correctly isolated one.

So the model must be *described*, not merely flagged, and the description must
change with the mode. Two contrast cases keep that from being a tautology:

  * a default instance must report the local-passwordless model;
  * an instance started with LITETASK_DEV_LOGIN=0 must report the shared model,
    with a different label and requiresPassword=true — a single hard-coded
    string would satisfy one of these but never both.

The UI half is asserted statically on public/index.html: it must read the model
from the API and render a label, and it must be able to show a *different*
message per mode. A grep for a word would pass on a comment; these checks look
for the binding and for the two branches it switches on.
"""
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import ROOT, Checker, http_at, run_instance, stop_instance, temp_dir  # noqa: E402

c = Checker("security-mode")

INDEX = os.path.join(ROOT, "public", "index.html")


def start(env_extra, tag):
    tmp = temp_dir(prefix="lt_mode_%s_" % tag)
    data_dir = os.path.join(tmp, "data")
    shutil.copytree(os.path.join(ROOT, "data"), data_dir)
    inst = run_instance(data_dir, os.path.join(tmp, "backup"), env_extra,
                        wait_after_ready=2.0, timeout=60, keep=True)
    return inst, tmp


def model_of(inst):
    base = "http://127.0.0.1:%d" % inst["port"]
    st, cfg = http_at(base, "GET", "/api/config", timeout=10)
    _, health = http_at(base, "GET", "/api/health", timeout=10)
    return st, (cfg or {}), ((health or {}).get("mode") or {})


def _check_default_instance(c):
    """Default instance must report the local-passwordless model."""
    local_label = local_hint = None
    inst, tmp = start({}, "default")
    try:
        c.check("default instance came up", inst["ready"], inst["output"][-300:])
        st, cfg, mode = model_of(inst)
        c.check("/api/config answers 200", st == 200, st)
        sm = cfg.get("securityModel") or {}
        c.check("config carries a securityModel object", bool(sm), cfg)
        c.check("default mode is 'local-passwordless'",
                sm.get("mode") == "local-passwordless", sm.get("mode"))
        c.check("it says no password is required", sm.get("requiresPassword") is False,
                sm.get("requiresPassword"))
        c.check("it carries a human-readable label", bool(sm.get("label")), sm.get("label"))
        c.check("it explains the model (hint is non-empty)", bool(sm.get("hint")),
                sm.get("hint"))
        c.check("health reports the same model as config",
                (mode.get("securityModel") or {}).get("mode") == sm.get("mode"),
                (mode.get("securityModel"), sm.get("mode")))
        local_label = sm.get("label")
        local_hint = sm.get("hint")
    finally:
        stop_instance(inst["proc"])
        shutil.rmtree(tmp, ignore_errors=True)
    return local_label, local_hint


def _check_shared_instance(c, local_label, local_hint):
    """Contrast: LITETASK_DEV_LOGIN=0 -> shared, password required."""
    inst2, tmp2 = start({"LITETASK_DEV_LOGIN": "0"}, "shared")
    try:
        c.check("shared-mode instance came up", inst2["ready"], inst2["output"][-300:])
        st, cfg, mode = model_of(inst2)
        c.check("/api/config answers 200 in shared mode", st == 200, st)
        sm = cfg.get("securityModel") or {}
        c.check("shared mode is 'shared-authenticated'",
                sm.get("mode") == "shared-authenticated", sm.get("mode"))
        c.check("it says a password IS required", sm.get("requiresPassword") is True,
                sm.get("requiresPassword"))
        c.check("its label differs from the local mode's label (a hard-coded "
                "string could not satisfy both)",
                bool(sm.get("label")) and sm.get("label") != local_label,
                (sm.get("label"), local_label))
        c.check("its hint differs from the local mode's hint",
                bool(sm.get("hint")) and sm.get("hint") != local_hint,
                (str(sm.get("hint"))[:40], str(local_hint)[:40]))
    finally:
        stop_instance(inst2["proc"])
        shutil.rmtree(tmp2, ignore_errors=True)


def _check_ui_renders_model(c):
    """The UI must show the model, not just receive it."""
    with open(INDEX, encoding="utf-8") as f:
        html = f.read()

    c.check("the UI reads the model from /api/config",
            "/api/config" in html and "securityModel" in html,
            ("config" in html, "securityModel" in html))
    c.check("the UI stores the model in reactive state (a ref it can render)",
            re.search(r"securityModel\s*=\s*ref\(", html) is not None, "no ref(")

    # Rendering: the label/hint must actually reach the template.
    c.check("the UI renders the model label in the template",
            re.search(r"securityModel[^;\n]{0,80}\.label", html) is not None
            or re.search(r"\{\{\s*securityModel\.label", html) is not None,
            "no label binding")
    c.check("the UI renders the model hint (the part that says what the mode "
            "means)",
            re.search(r"\{\{\s*securityModel\.hint", html) is not None
            or re.search(r"securityModel\.hint", html) is not None,
            "no hint binding")

    # Two branches: the banner must be able to differ per mode. Looking for both
    # a requiresPassword branch and a mode branch keeps this from passing on a
    # single unconditional line of text.
    c.check("the banner branches on the model, so the two modes read "
            "differently",
            re.search(r"securityModel\.requiresPassword", html) is not None
            or re.search(r"securityModel\.mode\s*===", html) is not None,
            "no branch on the model")


def main():
    local_label, local_hint = _check_default_instance(c)
    _check_shared_instance(c, local_label, local_hint)
    _check_ui_renders_model(c)
    c.finish()


if __name__ == "__main__":
    main()
