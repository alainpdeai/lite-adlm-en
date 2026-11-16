# -*- coding: utf-8 -*-
"""
Grader: the assertions must have teeth (mutation testing).

A grading suite can go green for the wrong reason. An assertion that is always
true proves nothing, and a suite full of them is a green light over a broken
build — the 2026-10-29 review found exactly two of that kind here (a hard-coded
item count, and a walk that never recursed into subTasks).

So this file breaks the implementation on purpose. For every (mutation, grader)
pair:

  * apply the mutation to whichever file now holds that code (route ① split
    server.js into lib/ modules, so most anchors no longer live in server.js);
  * run the grader and assert it FAILS — the grader caught the break;
  * restore the file and assert it is byte-identical again;
  * run the grader once more and assert it PASSES — proving the failure came
    from the mutation and not from a flaky environment.

A grader that still passes while the implementation is broken is not grading
anything; that tautology is what this file exists to catch.

Two guards keep the mechanism itself honest:

  * the mutation anchor must occur exactly once, so a refactor cannot leave the
    mutation silently doing nothing (which would fake a pass);
  * a grader must fail with its own `RESULT ...: FAIL` line. A crash or a
    transport error yields no such line and therefore fails here too — "the
    grader caught it" and "the grader exploded" are different claims.

Only hermetic graders are used: each starts its own `node server.js` against a
copy of the data, so the mutation takes effect without touching production.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import ROOT, Checker  # noqa: E402

c = Checker("assertion-quality")

def _target_of(mut):
    """Absolute path of the file a mutation applies to (server.js by default)."""
    return os.path.join(ROOT, *mut.get("file", "server.js").split("/"))


# Route ① split server.js (2845 lines) into lib/ modules, so most of the code
# these mutations probe now lives somewhere else. Each mutation names the file
# that holds it; `server.js` stays the default for the one anchor that is still
# there. The file is as much a part of the anchor as the text: a mutation
# applied to the wrong file would silently do nothing and fake a pass.
MUTATIONS = [
    {
        "name": "item schema validation disabled",
        "grader": "grade_item_schema.py",
        # The whole-list write now sits in lib/lists_routes.js, one nesting level
        # deeper than when it was in server.js. The item-level endpoints validate
        # too, but those moved to lib/items.js, so this anchor is unique here
        # without extra context.
        "file": "lib/lists_routes.js",
        "find": "                const vchk = validateItems(items);\n"
                "                if (!vchk.ok) {",
        "replace": "                const vchk = validateItems(items);\n"
                   "                if (false) {",
        "why": "illegal items would be accepted and written to disk",
    },
    {
        "name": "backup retention default 5 -> 2",
        "grader": "grade_backup_rotation.py",
        "file": "lib/backup.js",
        "find": "process.env.LITETASK_BACKUP_KEEP || 5",
        "replace": "process.env.LITETASK_BACKUP_KEEP || 2",
        "why": "rotation would keep 2 stamps where 5 are asserted",
    },
    {
        "name": "audit redaction disabled",
        "grader": "grade_security_audit.py",
        "file": "lib/audit.js",
        "find": "                ? '[redacted]'\n"
                "                : summarizeForAudit(value[k], depth + 1);",
        "replace": "                ? value[k]\n"
                   "                : summarizeForAudit(value[k], depth + 1);",
        "why": "a planted password would be written into the audit verbatim",
    },
    {
        "name": "archive confirmation gate disabled",
        "grader": "grade_destructive_confirm.py",
        "file": "lib/archive_routes.js",
        "find": "        const gate = requireConfirm(req, 'Archiving will move closed items out of the active list');\n"
                "        if (gate) return res.status(400).json(gate);",
        "replace": "        const gate = null;   /* mutated: no gate at all */",
        "why": "an unconfirmed archive would be performed anyway",
    },
    {
        "name": "hard gate softened back to 'omitted means yes'",
        "grader": "grade_destructive_confirm.py",
        "file": "lib/lists_core.js",
        "find": "    return b === true || q === 'true';",
        "replace": "    return b !== false;   /* mutated: omission counts as consent */",
        "why": "a caller that never saw a dialog would pass the gate by "
               "simply leaving the field out — the exact ambiguity the hard "
               "gate was introduced to remove",
    },
    {
        "name": "resync-on-connect disabled",
        "grader": "grade_resync_on_connect.py",
        "file": "server.js",
        "find": "    socket.emit('resync');",
        "replace": "    /* mutated: never tells a connecting client to refetch */",
        "why": "a browser that survived a restart would keep its stale snapshot",
    },
    {
        "name": "item-level write reads the previous status from the mutated list",
        "grader": "grade_item_endpoints.py",
        "file": "lib/items.js",
        "find": "                prevStatuses = collectStatuses(data.items, sc0);",
        "replace": "                prevStatuses = new Map();   /* mutated: reads nothing */",
        "why": "with an empty map every single-item write looks like a no-op, so "
               "the F1 status machine never runs and any transition is accepted",
    },
    {
        # Note: mutating the `if-none-match` branch itself does NOT make this
        # grader fail — Express answers the conditional GET on its own once an
        # ETag header is present. The part that is really ours is the *tag*, so
        # that is what gets broken here.
        "name": "the ETag stops following the content",
        "grader": "grade_incremental_sync.py",
        "file": "lib/lists_core.js",
        "find": ".update(JSON.stringify((lists || []).map(l => "
                "[String(l.listId), String(l.rev)])))",
        "replace": ".update('constant')   /* mutated: a tag that never moves */",
        "why": "a tag that does not follow the content is worse than no tag: "
               "clients would keep a stale board and believe it was confirmed "
               "fresh — every poll would answer 304 forever",
    },
]


def run_grader(name):
    """Return ("PASS"|"FAIL"|None, output). None means the grader never printed
    its verdict — a crash, not a caught mutation."""
    p = subprocess.run([sys.executable, os.path.join(HERE, name)],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    out = (p.stdout or "") + (p.stderr or "")
    m = re.search(r"RESULT .*?: (PASS|FAIL)", out)
    return (m.group(1) if m else None), out


def _check_one_mutation(c, mut, sources, originals):
    """Apply one (mutation, grader) pair: assert it fails, restore, assert it passes."""
    path = _target_of(mut)
    rel = os.path.relpath(path, ROOT).replace("\\", "/")
    src = sources[path]
    original = originals[path]

    print()
    print("== mutation: %s ==" % mut["name"])
    n = src.count(mut["find"])
    c.check("anchor %r occurs exactly once in %s (a missing or "
            "repeated anchor would make the mutation silent)"
            % (mut["find"], rel), n == 1, n)
    if n != 1:
        return

    mutated = src.replace(mut["find"], mut["replace"])
    c.check("the mutation really changes the source", mutated != src,
            mut["name"])
    with open(path, "wb") as f:
        f.write(mutated.encode("utf-8"))

    state, out = run_grader(mut["grader"])
    c.check("%s FAILS while the implementation is broken (%s)"
            % (mut["grader"], mut["why"]),
            state == "FAIL",
            (state, out.strip().splitlines()[-3:]))

    # restore, then prove the failure was the mutation's doing
    with open(path, "wb") as f:
        f.write(original)
    with open(path, "rb") as f:
        c.check("%s restored byte for byte right after the "
                "mutation" % rel, f.read() == original, mut["name"])

    state2, out2 = run_grader(mut["grader"])
    c.check("%s PASSES again once the implementation is restored "
            "(contrast: the failure came from the mutation, not the "
            "environment)" % mut["grader"],
            state2 == "PASS",
            (state2, out2.strip().splitlines()[-3:]))


def main():
    # Every file a mutation touches is snapshotted up front and restored in the
    # finally block: a mutation must never survive this grader, whichever module
    # it was applied to.
    originals = {}
    sources = {}
    for path in [_target_of(m) for m in MUTATIONS]:
        with open(path, "rb") as f:
            originals[path] = f.read()
        sources[path] = originals[path].decode("utf-8")

    try:
        for mut in MUTATIONS:
            _check_one_mutation(c, mut, sources, originals)
    finally:
        for path, original in originals.items():
            with open(path, "rb") as f:
                if f.read() != original:
                    with open(path, "wb") as g:
                        g.write(original)
                    print("  !! %s was left mutated; restored in finally"
                          % os.path.relpath(path, ROOT).replace("\\", "/"))

    for path, original in originals.items():
        with open(path, "rb") as f:
            c.check("%s is byte-identical to its original state when this "
                    "grader finishes (no mutation may survive)"
                    % os.path.relpath(path, ROOT).replace("\\", "/"),
                    f.read() == original, path)

    c.finish()


if __name__ == "__main__":
    main()
