# -*- coding: utf-8 -*-
"""
M2 step 2 — remove the legacy files (after m2_backup_legacy.py reports OK).

Scope is exactly the 7 files the M2 task names, plus the directories that exist
only to hold them. `data/users/` itself is kept: server.js references it in the
migration and user-deletion paths.

Refuses to run unless the matching backup directory is present and complete.
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
BACKUP = os.path.join(ROOT, 'backup')
STAMP = sys.argv[1] if len(sys.argv) > 1 else None
APPLY = '--apply' in sys.argv

TARGETS = [
    '_legacy_backup_20261027/01.json',
    '_legacy_backup_20261027/02.json',
    '_legacy_backup_20261027/03.json',
    '_legacy_backup_20261027/04.json',
    'users/user_1791622363912/01.json',
    'users/user_admin/01.json',
    'users/user_admin/02.json',
]
# removed only if empty afterwards
DIRS = [
    '_legacy_backup_20261027',
    'users/user_1791622363912',
    'users/user_admin',
]


def main():
    if not STAMP:
        print('usage: m2_remove_legacy.py <stamp> [--apply]')
        return 2

    dest = os.path.join(BACKUP, 'legacy_m2_' + STAMP)
    missing = [t for t in TARGETS
               if not os.path.isfile(os.path.join(dest, t.replace('/', os.sep)))]
    if missing:
        print('REFUSING: backup incomplete, missing %s' % missing)
        return 3
    print('backup verified present: %s' % dest)

    # also refuse if a target vanished from data/ already (double-run guard)
    absent = [t for t in TARGETS
              if not os.path.isfile(os.path.join(DATA, t.replace('/', os.sep)))]
    if absent:
        print('already gone from data/: %s' % absent)

    if not APPLY:
        print()
        print('DRY RUN — nothing removed. Re-run with --apply.')
        for t in TARGETS:
            p = os.path.join(DATA, t.replace('/', os.sep))
            print('  would remove %-38s %s' % (
                t, ('%d B' % os.path.getsize(p)) if os.path.isfile(p) else 'absent'))
        return 0

    print()
    removed = 0
    for t in TARGETS:
        p = os.path.join(DATA, t.replace('/', os.sep))
        if os.path.isfile(p):
            os.remove(p)
            removed += 1
            print('  removed %s' % t)
    for d in DIRS:
        p = os.path.join(DATA, d.replace('/', os.sep))
        if os.path.isdir(p) and not os.listdir(p):
            os.rmdir(p)
            print('  removed empty dir %s/' % d)
        elif os.path.isdir(p):
            print('  kept non-empty dir %s/' % d)

    print()
    print('REMOVED %d file(s). data/users/ kept (referenced by server.js).' % removed)
    return 0


if __name__ == '__main__':
    sys.exit(main())
