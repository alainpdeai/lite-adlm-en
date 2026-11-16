# Archiving, Pruning & Backups

As projects grow, unbounded task accumulation degrades JSON parsing performance, UI responsiveness, and graph traversal speed. Lite ADLM provides a two-phase transactional archiving engine that prunes completed tasks from active lists into separate archive files while maintaining total traceability.

---

## 1. Archiving Rules (Subtree Preservation)

To guarantee that task context is never fractured:
- **Subtree Integrity**: Only top-level tasks whose **entire subtree is completed** can be archived. If a parent task has even a single open subtask, the whole subtree remains in the active list.
- **Preview First**: The system requires a dry-run preview (`GET /api/lists/:id/archive-preview` or `python scripts/litetask_cli.py --root . archive --category <cat> --dry-run`) before committing changes.
- **Explicit Confirmation**: Archive execution requires an explicit `confirm: true` payload to prevent accidental one-click data moves.

---

## 2. Two-Phase Transactional Execution

Archiving runs as a two-phase transaction:

1. **Pre-flight Check**: Validates that all candidate item IDs exist and satisfy the subtree-completion criterion.
2. **Snapshot Creation**: Writes a timestamped point-in-time snapshot to `data/archive-snapshots/<listId>_<stamp>.json`.
3. **Archive Append**: Appends completed items to `data/archive/<listId>_archive.json`.
4. **Active List Pruning**: Removes archived items from `data/shared_lists/<listId>.json`, bumps the revision hash, and broadcasts live WebSocket updates to all connected browser clients.

---

## 3. Instant Rollback Drill

Archived data is never permanently lost:

- **Full Recovery**: If an archive operation was performed by mistake, it can be instantly undone via `POST /api/lists/:id/archive-restore` or the "Rollback Archive" button in the web UI.
- **Snapshot Integrity**: The active list is atomically restored from its snapshot file, and archived items are removed from the archive file, restoring the exact state prior to archiving.

---

## 4. Automated Rolling Backups

In addition to transactional snapshots, Lite ADLM runs automatic rolling backups on every mutating write:

- **Location**: `backup/shared_lists/`.
- **Retention**: Keeps the 10 most recent backups per list, automatically pruning older files.
- **Format**: `<listId>_backup_<timestamp>.json`.
- **Integrity**: Verified by test suite `tests/grade_backup_rotation.py` and `tests/grade_restore_drill.py`.
