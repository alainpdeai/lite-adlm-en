"""CLI-side check for the B3 follow-up: --force + conflict-diff rendering.

Loads scripts/litetask_cli.py as a module and drives its real `write()` against
the running server. The list contents sent are the current ones, so nothing on
the board changes — only the revision token is faked to be stale.

Run:  python tests/test_cli_force.py
"""
import importlib.util
import os
import subprocess
import sys

BASE = os.environ.get("LITETASK_BASE_URL", "http://localhost:3000")
CLI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "scripts", "litetask_cli.py")

FAILURES = []


def check(label, ok, detail=""):
    print(("  PASS  " if cond_fmt(ok) else "  FAIL  ") + label + (("  -> " + str(detail)) if detail else ""))
    if not ok:
        FAILURES.append(label)


def cond_fmt(x):
    return bool(x)


def _load_cli():
    """Load scripts/litetask_cli.py as a module."""
    spec = importlib.util.spec_from_file_location("litetask_cli", CLI)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return cli


def _check_force_write(cli, ctx, arch):
    """A stale rev goes through with force, and is refused without it."""
    # 1. --force is a real global flag on the parser
    help_text = subprocess.run([sys.executable, CLI, "--help"],
                               capture_output=True, text=True).stdout
    check("--force is a documented global flag", "--force" in help_text)

    # 2. force write with a deliberately stale rev goes through
    stale = dict(arch)
    stale["rev"] = "deadbeefdeadbeef"          # a token the server has never issued
    cli.FORCE_WRITE = True
    try:
        res = ctx["write"]("arch", stale)
        ok = isinstance(res, dict) and res.get("listId") == "arch"
        check("forced write with stale rev accepted", ok, res.get("rev") if isinstance(res, dict) else res)
    except SystemExit as e:
        check("forced write with stale rev accepted", False, e.code)
    finally:
        cli.FORCE_WRITE = False

    # 3. without force the same stale rev is refused, and the diff is rendered
    try:
        ctx["write"]("arch", stale)
        check("stale rev refused without force", False, "no SystemExit raised")
    except SystemExit as e:
        msg = str(e.code)
        check("stale rev refused without force", "REV_CONFLICT" in msg, msg.splitlines()[0])
        check("message tells the user about --force", "--force" in msg)
        check("message contains the diff summary line", "summary:" in msg,
              [ln for ln in msg.splitlines() if "summary:" in ln])


def _check_diff_renderer(cli):
    """The diff renderer handles a realistic payload and an empty one."""
    # 4. the diff renderer handles a realistic payload
    sample = {
        "added": [{"itemId": "a1", "title": "My added task"}],
        "removed": [{"itemId": "s1", "title": "Server added task"}],
        "changed": [{"itemId": "c1", "title": "Both modified task", "fields": [
            {"field": "priority", "label": "Priority", "mine": "Low", "server": "High"},
            {"field": "comment", "label": "Comment", "mine": "My comment", "server": "Server comment"},
        ]}],
        "counts": {"added": 1, "removed": 1, "changed": 1, "fields": 2},
    }
    text = cli.format_conflict_diff(sample)
    print("\n--- rendered diff ---\n" + text + "\n---------------------")
    check("renderer lists mine-only item", "mine-only" in text and "My added task" in text)
    check("renderer lists server-only item", "server-only" in text and "Server added task" in text)
    check("renderer shows both sides of a field",
          "mine=Low" in text and "server=High" in text)
    check("renderer appends the summary", "summary: +1 / -1 / ~1 items, 2 fields" in text)
    check("renderer survives an empty diff",
          "summary:" in cli.format_conflict_diff({}) and "identical" in cli.format_conflict_diff({}))


def main():
    cli = _load_cli()
    ctx = cli.api_ctx(BASE)
    lists = cli._get(BASE + "/api/lists")
    arch = [l for l in lists if l.get("listId") == "arch"][0]

    _check_force_write(cli, ctx, arch)
    _check_diff_renderer(cli)

    print("\nRESULT: %d failure(s)" % len(FAILURES))
    for f in FAILURES:
        print("  - " + f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
