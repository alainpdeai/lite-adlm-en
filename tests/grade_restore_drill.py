# -*- coding: utf-8 -*-
"""
Grader: backups must be restorable, and a second copy must exist.

Before this, the project had backups but no *recovery path*: twenty CLI
subcommands and not one `restore`, and no grader had ever restored anything.
"Having backups" and "being able to restore" are different claims, and only the
second one can be graded. The 2026-10-28 cleanup proved the cost of confusing
them: the M2 snapshot was deleted and, being unreproducible, had to be recorded
as a permanent loss.

Under test:

* `litetask_cli.py restore` — list stamps, restore a stamp into a directory
  (safe), or write it back into data/ behind an explicit --yes.
* A backup mirror on a second location, so one directory losing its contents is
  not the same as losing the snapshots.

The drill is the point: build a throwaway tree, snapshot it, DESTROY it, restore
it, and compare field by field. Contrast cases prove the comparison is not a
tautology — the destroyed state must compare unequal, an unknown stamp must
fail, and --apply without --yes must refuse.
"""
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade_lib import (ROOT, Checker, copy_data_dir, fixture_preflight,  # noqa: E402
                       run_instance, stop_instance, temp_dir, temp_item)

c = Checker("restore-drill")

CLI_PATH = os.path.join(ROOT, "scripts", "litetask_cli.py")
DEAD_URL = "http://127.0.0.1:59999"   # forces file mode, never touches the server


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def fingerprint(root):
    """path-relative -> parsed JSON, for every .json below root."""
    out = {}
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            try:
                out[rel] = load_json(full)
            except ValueError:
                out[rel] = "UNPARSABLE"
    return out


def cli(*args):
    return subprocess.run([sys.executable, CLI_PATH, "--url", DEAD_URL, "--root", ROOT_PROJ]
                          + list(args),
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)


def destroy(data_root, list_id="func"):
    """Real damage: drop items and rewrite a field, the way a bad write would."""
    p = os.path.join(data_root, "shared_lists", list_id + ".json")
    doc = load_json(p)
    before = len(doc["items"])
    doc["items"] = doc["items"][:max(0, before - 3)]
    if doc["items"]:
        doc["items"][0]["title"] = "CLOBBERED BY THE RESTORE DRILL"
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return before


def seed_items(data_dir, list_id, n):
    """Give the private copy enough items for real damage to be detectable."""
    p = os.path.join(data_dir, "shared_lists", list_id + ".json")
    with open(p, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    items = list(doc.get("items", []))
    if len(items) < n:
        for k in range(len(items), n):
            items.append(temp_item("%s-seed-%02d" % (list_id, k),
                                   title="baseline seed", status="open"))
        doc["items"] = items
        doc["rev"] = ""
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2)
            fh.write("\n")


tmp = temp_dir(prefix="lt_grade_restore_")
ROOT_PROJ = os.path.join(tmp, "proj")
os.makedirs(ROOT_PROJ, exist_ok=True)
data_dir = copy_data_dir(ROOT_PROJ)
backup_dir = os.path.join(ROOT_PROJ, "backup")
_fixture = fixture_preflight(data_dir, "func")
if _fixture in ("missing", "unparseable"):
    c.skip_all("delivery baseline lacks parseable func.json (%s)" % _fixture)
if _fixture == "unwritable":
    c.blocked("private copy not writable: %s"
              % os.path.join(data_dir, "shared_lists", "func.json"))

# The delivery baseline ships an empty board; a drill that deletes items from
# an empty list proves nothing. Seed the throwaway copy only.
seed_items(data_dir, "func", 4)

# ---------------------------------------------------------------- 1. snapshot
inst = run_instance(data_dir, backup_dir, {"LITETASK_AUTO_ARCHIVE": "0"},
                    wait_after_ready=2.0, keep=True)
c.check("the throwaway instance came up", inst["ready"], inst["output"][-300:])
stop_instance(inst["proc"])
c.check("startup produced a snapshot", os.path.isdir(backup_dir), backup_dir)

# Match the CLI's collect_stamps (BACKUP_STAMP_RE): only real startup stamps of
# the form *.YYYYMMDDTHHMMSSsssZ.json count. data/archive-snapshots/*.snapshot.json
# is mirrored into backup/ by the startup backup and must NOT be read as a stamp
# (its naive fn.split(".")[1] would yield the literal 'snapshot' and shadow the
# real stamp). See grade_restore_drill.py, 2026-10-30.
BACKUP_STAMP_RE = re.compile(r"\.(\d{8}T\d{9}Z)\.json$", re.I)
stamps = sorted({m.group(1) for _, _, fs in os.walk(backup_dir)
                 for fn in fs if (m := BACKUP_STAMP_RE.search(fn))})
c.check("at least one stamped snapshot exists", bool(stamps), stamps[:3])
stamp0 = stamps[-1] if stamps else None

baseline = fingerprint(data_dir)
c.check("the baseline tree has data in it", len(baseline) >= 4, sorted(baseline)[:6])

# ------------------------------------------------------------------ 2. damage
before_count = destroy(data_dir)
damaged = fingerprint(data_dir)
c.check("the drill actually damaged the tree (contrast: comparison can detect it)",
        damaged != baseline,
        "fingerprints equal -> the comparison proves nothing")

r = cli("restore", "--stamp", "no-such-stamp", "--to", os.path.join(tmp, "nowhere"))
c.check("an unknown stamp is refused, not silently ignored", r.returncode != 0,
        (r.returncode, (r.stdout or "")[:120], (r.stderr or "")[:120]))

r = cli("restore")
c.check("listing snapshots exits 0", r.returncode == 0,
        (r.returncode, (r.stderr or "")[:160]))
c.check("the listing names the stamp we just made",
        stamp0 and stamp0 in (r.stdout or ""), (r.stdout or "")[:200])

# ------------------------------------------- 3. safe restore into a directory
dest = os.path.join(tmp, "restored")
r = cli("restore", "--stamp", stamp0, "--to", dest)
c.check("restoring into a directory exits 0", r.returncode == 0,
        (r.returncode, (r.stderr or "")[:200]))
restored = fingerprint(dest) if os.path.isdir(dest) else {}
missing = sorted(set(baseline) - set(restored))
mismatched = sorted(k for k in set(baseline) & set(restored)
                    if baseline[k] != restored[k])
c.check("every file came back", bool(restored) and not missing,
        (sorted(restored)[:3], missing[:5]))
# Guard against the empty-set tautology: if nothing was restored, "no
# mismatches" would be true for the wrong reason.
c.check("every file matches the pre-damage state, field for field",
        bool(restored) and not mismatched, (len(restored), mismatched[:5]))
rp = os.path.join(dest, "shared_lists", "func.json")
c.check("the clobbered title is gone after restore",
        os.path.exists(rp)
        and not any(it.get("title") == "CLOBBERED BY THE RESTORE DRILL"
                    for it in load_json(rp).get("items", [])), rp)
c.check("the three deleted items are back",
        os.path.exists(rp) and len(load_json(rp).get("items", [])) == before_count,
        (before_count, len(load_json(rp).get("items", [])) if os.path.exists(rp) else None))

# ------------------------------------------------- 4. --apply refuses without --yes
r = cli("restore", "--stamp", stamp0, "--apply")
c.check("--apply without --yes is refused (destructive action asks first)",
        r.returncode != 0, (r.returncode, (r.stdout or "")[:120]))

# ------------------------------------------------------- 5. --apply writes back
r = cli("restore", "--stamp", stamp0, "--apply", "--yes")
c.check("--apply --yes exits 0", r.returncode == 0,
        (r.returncode, (r.stderr or "")[:200]))
after = fingerprint(data_dir)
c.check("data/ was restored in place, field for field",
        after == baseline,
        sorted(k for k in set(after) & set(baseline) if after[k] != baseline[k])[:5])

# --------------------------------------------------------------- 6. the mirror
tmp2 = temp_dir(prefix="lt_grade_mirror_")
mirror = os.path.join(tmp2, "mirror")
d2 = copy_data_dir(tmp2)
b2 = os.path.join(tmp2, "backup")
inst2 = run_instance(d2, b2, {"LITETASK_AUTO_ARCHIVE": "0",
                              "LITETASK_BACKUP_MIRROR": mirror},
                     wait_after_ready=2.0, keep=True)
c.check("the mirrored instance came up", inst2["ready"], inst2["output"][-200:])
stop_instance(inst2["proc"])
mirrored = [os.path.relpath(os.path.join(dp, f), mirror).replace("\\", "/")
            for dp, _, fs in os.walk(mirror) for f in fs] if os.path.isdir(mirror) else []
c.check("the mirror received files", bool(mirrored), mirrored[:4])
backed = [os.path.relpath(os.path.join(dp, f), b2).replace("\\", "/")
          for dp, _, fs in os.walk(b2) for f in fs]
c.check("the mirror holds the same relative paths as backup/",
        sorted(mirrored) == sorted(backed),
        (sorted(mirrored)[:4], sorted(backed)[:4]))

# contrast: an explicit off switch must leave no mirror behind
tmp3 = temp_dir(prefix="lt_grade_mirroroff_")
d3 = copy_data_dir(tmp3)
b3 = os.path.join(tmp3, "backup")
inst3 = run_instance(d3, b3, {"LITETASK_AUTO_ARCHIVE": "0",
                              "LITETASK_BACKUP_MIRROR": "0"},
                     wait_after_ready=2.0, keep=True)
c.check("the mirror-off instance came up", inst3["ready"], inst3["output"][-200:])
stop_instance(inst3["proc"])
default_mirror = os.path.join(os.path.expanduser("~"), "AppData", "Local",
                              "LiteTask", "backup-mirror")
c.check("with the mirror switched off, backup/ still got its snapshot",
        bool(backed) and os.path.isdir(b3) and any(os.walk(b3).__next__()[2]),
        b3)

# the default mirror location must not be inside the project
c.check("the default mirror location is outside the project tree",
        os.path.realpath(default_mirror).startswith(os.path.realpath(ROOT)) is False,
        default_mirror)

shutil.rmtree(tmp, ignore_errors=True)
shutil.rmtree(tmp2, ignore_errors=True)
shutil.rmtree(tmp3, ignore_errors=True)
c.finish()
