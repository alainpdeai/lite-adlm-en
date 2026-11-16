# -*- coding: utf-8 -*-
"""
Size budget grader: pin the "no file over 500 lines" rule inside the repository.

Why this is a grader and not a habit
------------------------------------
The 500-line limit follows a generic checker default (`max_file_lines`, 500).
It was not a decision recorded anywhere in this repository: no config file
pinned a budget, the pre-commit gate runs the grading subset only, and there
was no CI. The rule was real in practice and invisible in the repository — it
lived in a throwaway script outside the tree, so it died with the session that
created it.

This grader makes the budget a first-class, reviewed artefact:

  * the thresholds are written here, not inherited from a tool's default;
  * the scope is explicit, including which files are deliberately exempt and
    why (`public/index.html` is a single-file frontend with no build step, so a
    per-file line budget does not mean for it what it means for `lib/`);
  * the exemption list is asserted to still match reality, so it cannot quietly
    rot into a way of hiding new oversized files.

Two thresholds, not one
-----------------------
A single hard limit gives no warning: a file is fine at 400 and a failure at
501, and the only moment the project finds out is when it is already over. The
band in between is where the decision belongs — it is the room to judge whether
a file is growing for a reason or by accident.

  * 400 lines -> printed as a warning. Nothing fails. It means "start looking".
  * 500 lines -> a hard failure. The commit is blocked.

Raising the limit would have been a no-op when this was written: the largest
enforced file was 392 lines, so no file sat anywhere near either threshold.

The informational section at the end measures JavaScript function bodies. That
metric is deliberately NOT enforced here. Route (1) builds each domain module
as a factory closure (`createXRoutes = (app, io, deps) => { ... }`), so the
enclosing function spans the whole module even though it holds a dozen
independent helpers — enforcing it as written would fail on the pattern rather
than on a problem. Containers and leaf bodies are therefore reported
separately, so the number can be read instead of obeyed.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from grade_lib import Checker                                    # noqa: E402

# ------------------------------------------------------------------ the budget
WARN_LINES = 400     # printed, never fails: "this file is getting there"
HARD_LINES = 500     # fails the build: the file is over budget
FUNC_WATCH = 80      # informational only: JS bodies worth a second look

# Directories that hold no first-party source at all.
SKIP_DIRS = {".git", "node_modules", "data", "backup", "logs", "archive"}

# Files exempt from the budget, each with the reason it is exempt. An exemption
# without a reason is just an exclusion; the reason is what makes it reviewable.
DECLARED_EXCEPTIONS = {
    "public/index.html": (
        "single-file frontend with no build step; third-party assets are "
        "vendored and declared separately"
    ),
}

DECLARED_THIRD_PARTY = {
    "public/vendor/vue/vue.global.prod.js": "Vue 3 production build",
    "public/vendor/quill/quill.js": "Quill 1.3.6",
    "public/vendor/quill/quill.snow.css": "Quill snow theme",
    "public/vendor/fontawesome/css/all.min.css": "Font Awesome 6.7.2",
    "public/vendor/fontawesome/webfonts/fa-solid-900.woff2": "FA webfont",
    "public/vendor/fontawesome/webfonts/fa-regular-400.woff2": "FA webfont",
    "public/vendor/fontawesome/webfonts/fa-brands-400.woff2": "FA webfont",
    "public/vendor/dompurify/purify.min.js": "DOMPurify 3.2.4",
    "public/vendor/tailwind/tailwind.css": "precompiled Tailwind 3.4.17",
    "public/vendor/VENDOR.json": "asset manifest",
}


def _rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def _lines(p):
    with open(p, encoding="utf-8") as f:
        return len(f.read().splitlines())


# ------------------------------------------------------------------ scope
def _glob(rel_dir, pattern):
    d = os.path.join(ROOT, rel_dir)
    if not os.path.isdir(d):
        return []
    import glob as _g
    return sorted(_g.glob(os.path.join(d, pattern)))


def collected_files():
    out = []
    out += _glob("", "*.js")
    out += _glob("lib", "*.js")
    out += _glob("tests", "*.py")
    out += _glob("tests", "*.js")
    return sorted(set(p for p in out if os.path.isfile(p)))


def first_party_files():
    """Every first-party source file, enforced or not. Feeds the scope guard."""
    out = []
    for sub, pattern in (("", "*.js"), ("lib", "*.js"), ("tests", "*.py"),
                         ("tests", "*.js"), ("public", "*.html"),
                         ("public", "*.js"), ("public", "*.css")):
        out += _glob(sub, pattern)
    return sorted(set(p for p in out if os.path.isfile(p)))


# ------------------------------------------------------------------ js bodies
def _closing_brace(lines, i):
    depth, started = 0, False
    for j in range(i, min(i + 3000, len(lines))):
        for ch in lines[j]:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
                if started and depth == 0:
                    return j
    return None


def _is_container(lines, i, e):
    """True when the body defines further functions or registers route
    handlers — i.e. it is a namespace/aggregator (the route (1) factory
    pattern) rather than one unit of logic.

    Two traps this has to avoid. The first is a grouping parenthesis: a line
    like `const actorName = (a && b) ? x : y` opens with `(` but defines no
    function, and counting it would misfile a 155-line request handler as a
    harmless namespace. The second is the opposite miss: the `register` bodies
    never name their handlers, they pass them straight to `app.get(...)`.
    Checking only for `const name = ...` would call those single units of
    logic when they are pure aggregation.
    """
    named_fn = re.compile(r"^\s+const \w+ = (async )?(\([^)]*\)|\w+)\s*=>")
    route_reg = re.compile(r"^\s+app\.(get|post|put|delete)\(")
    for j in range(i + 1, e):
        if named_fn.match(lines[j]) or route_reg.match(lines[j]):
            return True
    return False


def js_function_bodies(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().split("\n")
    out = []
    for i, line in enumerate(lines):
        if (re.search(r"=>\s*\{\s*$", line)
                or re.search(r"\bfunction\s*\w*\s*\([^)]*\)\s*\{", line)):
            e = _closing_brace(lines, i)
            if e:
                out.append((e - i + 1, i + 1, line.strip()[:66],
                            _is_container(lines, i, e)))
    return out


def main():
    c = Checker("size budget")

    files = collected_files()
    measured = [(n, p) for p in files for n in [_lines(p)]]
    measured.sort(reverse=True)

    over = [(n, p) for n, p in measured if n > HARD_LINES]
    warn = [(n, p) for n, p in measured if WARN_LINES < n <= HARD_LINES]

    print("=== enforced scope: %d files, largest %d lines (warn %d / hard %d) ==="
          % (len(measured), measured[0][0] if measured else 0,
             WARN_LINES, HARD_LINES))

    c.check("no enforced source file exceeds the %d-line hard limit"
            % HARD_LINES,
            not over,
            [(n, _rel(p)) for n, p in over])

    if warn:
        print()
        print("  warn band (%d-%d lines) — over the warning threshold, "
              "still within budget:" % (WARN_LINES + 1, HARD_LINES))
        for n, p in warn:
            print("      %4d  %s" % (n, _rel(p)))

    # ---------------------------------------------------------- scope guard
    known = set(_rel(p) for p in files)
    known |= set(DECLARED_EXCEPTIONS)
    known |= set(DECLARED_THIRD_PARTY)
    unclassified = [_rel(p) for p in first_party_files() if _rel(p) not in known]
    c.check("every first-party source file is classified — enforced, or a "
            "declared exception/third-party entry with a reason",
            not unclassified, unclassified)

    missing = [k for k in DECLARED_EXCEPTIONS
               if not os.path.isfile(os.path.join(ROOT, k))]
    c.check("every declared exception still exists on disk (a stale entry "
            "would hide the fact that the reason no longer applies)",
            not missing, missing)
    missing3 = [k for k in DECLARED_THIRD_PARTY
                if not os.path.isfile(os.path.join(ROOT, k))]
    c.check("every declared third-party asset exists on disk", not missing3, missing3)

    total = sum(os.path.getsize(os.path.join(dp, f))
                for dp, _dn, fs in os.walk(os.path.join(ROOT, "public")) for f in fs)
    c.check("public/ total size stays under 3 MiB (third-party vendored)",
            total <= 3 * 1024 * 1024, total)
    largest = max((os.path.getsize(os.path.join(dp, f)), os.path.join(dp, f))
                  for dp, _dn, fs in os.walk(os.path.join(ROOT, "public")) for f in fs)
    c.check("largest first-screen script stays under 1 MiB",
            largest[0] <= 1024 * 1024, (largest[0], _rel(largest[1])))

    c.check("the budget is coherent: the warning threshold sits below the "
            "hard limit, so there is a band to act in",
            WARN_LINES < HARD_LINES, (WARN_LINES, HARD_LINES))

    # ------------------------------------------------- informational: bodies
    print()
    print("=== declared exceptions (not enforced, reason recorded) ===")
    for rel, why in sorted(DECLARED_EXCEPTIONS.items()):
        p = os.path.join(ROOT, rel)
        n = _lines(p) if os.path.isfile(p) else 0
        print("  %5d  %s" % (n, rel))
        print("         %s" % why)

    print()
    print("=== informational: JS function bodies over %d lines (NOT enforced) ==="
          % FUNC_WATCH)
    print("    route (1) factories are namespaces, so they are listed apart.")
    containers, leaves = [], []
    for p in _glob("lib", "*.js") + _glob("", "*.js"):
        for n, ln, sig, is_cont in js_function_bodies(p):
            if n > FUNC_WATCH:
                (containers if is_cont else leaves).append(
                    (n, _rel(p), ln, sig))
    print()
    print("  containers (factory/namespace closures — expected to be large):")
    for n, rel, ln, sig in sorted(containers, reverse=True):
        print("    %4d  %s:%d  %s" % (n, rel, ln, sig))
    print()
    print("  leaf bodies (single units of logic — the real hotspots):")
    if leaves:
        for n, rel, ln, sig in sorted(leaves, reverse=True):
            print("    %4d  %s:%d  %s" % (n, rel, ln, sig))
    else:
        print("    (none over %d lines)" % FUNC_WATCH)

    c.finish()


if __name__ == "__main__":
    main()
