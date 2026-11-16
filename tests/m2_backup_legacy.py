# -*- coding: utf-8 -*-
"""
M2 step 1 — back up the legacy files before touching them.

Copies every file listed below into backup/legacy_m2_<stamp>/ keeping its path
relative to data/, then verifies each copy byte-for-byte (sha256 + size) so the
backup is proven usable rather than assumed.

Nothing is deleted here; deletion is a separate step that only runs after this
reports OK.
"""
import hashlib
import io
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
BACKUP = os.path.join(ROOT, 'backup')
STAMP = sys.argv[1] if len(sys.argv) > 1 else 'nostamp'
DEST = os.path.join(BACKUP, 'legacy_m2_' + STAMP)

# relative to data/ — exactly the scope the M2 task names
TARGETS = [
    '_legacy_backup_20261027/01.json',
    '_legacy_backup_20261027/02.json',
    '_legacy_backup_20261027/03.json',
    '_legacy_backup_20261027/04.json',
    'users/user_1791622363912/01.json',
    'users/user_admin/01.json',
    'users/user_admin/02.json',
]


def sha256(path):
    h = hashlib.sha256()
    with io.open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    print('backup dir: %s' % DEST)
    rows = []
    total = 0
    for rel in TARGETS:
        src = os.path.join(DATA, rel)
        if not os.path.isfile(src):
            print('  MISSING  %s' % rel)
            rows.append((rel, 'MISSING'))
            continue
        dst = os.path.join(DEST, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

        s_src, s_dst = sha256(src), sha256(dst)
        n_src, n_dst = os.path.getsize(src), os.path.getsize(dst)
        ok = (s_src == s_dst) and (n_src == n_dst)
        total += n_src
        rows.append((rel, 'OK' if ok else 'MISMATCH', n_src, s_src[:16]))
        print('  %-8s %-34s %7d B  sha256=%s' % (
            'OK' if ok else 'MISMATCH', rel, n_src, s_src[:16]))

    print()
    print('files: %d   bytes: %d' % (len([r for r in rows if r[1] == 'OK']), total))
    bad = [r for r in rows if r[1] != 'OK']
    if bad:
        print('BACKUP INCOMPLETE: %s' % bad)
        return 1
    print('BACKUP OK — every file copied and byte-verified.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
