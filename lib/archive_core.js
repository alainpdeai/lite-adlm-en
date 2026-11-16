'use strict';
const path = require('path');
const fs = require('fs-extra');

const cfg = require('./config');
const util = require('./util');
const paths = require('./paths');
const { createTxnSupport } = require('./archive_txn');
const { createSnapshotSupport } = require('./archive_snapshots');

const {
    ARCHIVE_DIR, ARCHIVE_SNAPSHOT_DIR, SHARED_LISTS_DIR,
    AUTO_ARCHIVE_ENABLED, AUTO_ARCHIVE_ENV_MIN,
    DEFAULT_AUTO_ARCHIVE_MIN_CLOSED, DEFAULT_ARCHIVE_WARN_WITHIN,
    MAX_ARCHIVE_SNAPSHOTS
} = cfg;
const { contentRev, atomicWriteJson, withLock } = util;

// Archive data layer (route ①, Round 8). Everything here is a pure data helper:
// no Express `app`, no injected `requireConfirm`. createArchiveCore(deps) closes
// over the injected `getCategories` loader exactly the way the original
// archive.js register() closure did, so behaviour is unchanged.
const createArchiveCore = ({ getCategories, writeAudit }) => {

    // the environment overrides the threshold so one launch can be tuned without
    // editing config. `protected` is a config-only concept: it blocks the *startup
    // sweep*, never the manual POST /api/lists/:id/archive.
    const getArchivePolicy = async () => {
        const cfg = await getCategories();
        const arch = (cfg && cfg.archive) || {};

        let minClosed = Number(arch.minClosed);
        if (!Number.isFinite(minClosed) || minClosed <= 0) minClosed = DEFAULT_AUTO_ARCHIVE_MIN_CLOSED;
        let minSource = 'categories.json';
        if (typeof AUTO_ARCHIVE_ENV_MIN === 'string' && AUTO_ARCHIVE_ENV_MIN.trim() !== '') {
            const envMin = Number(AUTO_ARCHIVE_ENV_MIN);
            if (Number.isFinite(envMin) && envMin > 0) {
                minClosed = envMin;
                minSource = 'env';
            }
        }

        let warnWithin = Number(arch.warnWithin);
        if (!Number.isFinite(warnWithin) || warnWithin < 0) warnWithin = DEFAULT_ARCHIVE_WARN_WITHIN;

        const protectedIds = Array.isArray(arch.protected)
            ? arch.protected.filter((x) => typeof x === 'string' && x)
            : [];

        return {
            enabled: AUTO_ARCHIVE_ENABLED,
            minClosed,
            warnWithin,
            protected: protectedIds,
            minSource
        };
    };

    /* ---------------------------------------------------------------------------
     * Archive (A1) — move closed work out of the active list file so it stays small
     * ------------------------------------------------------------------------- */
    const archivePathFor = (listId) => paths.archiveFilePath(listId);

    const readArchive = async (listId) => {
        const p = archivePathFor(listId);
        if (!p) return { listId, items: [] };
        if (!(await fs.pathExists(p))) return { listId, items: [] };
        try { return await fs.readJson(p); } catch { return { listId, items: [] }; }
    };

    // P1-4: snapshot before any archive mutation.
    //
    // An archive removes items from the active list and appends them to the archive
    // file; until now that was a one-way, unrecoverable edit — the 2026-10-29 loss of
    // 17 `arch` items (recovered by hand from git, commit b780480) proved the gap.
    // writeArchiveSnapshot captures BOTH the active list and the archive file in
    // their exact pre-mutation state, so a single archive action can be audited and
    // rolled back via POST /api/lists/:id/archive-restore.
    const {
        snapshotFileFor, writeArchiveSnapshot, pruneArchiveSnapshots, listArchiveSnapshots,
    } = createSnapshotSupport();

    const txn = createTxnSupport({ writeAudit });
    const {
        TXN_SUFFIX, drillOn, txnFilePath, findPendingTxn, clone,
        txnFailure, auditTxnFailure, restoreFile, restoreFileOrRemove,
        recoverInterruptedTransactions,
    } = txn;


    // Reverse a single archive action: write the captured pre-state back to both the
    // active list and the archive file.
    const restoreArchiveSnapshot = async (listId, stamp, actor = null) => {
        // P0-1: both address keys are validated before the archive lock is taken.
        if (!paths.validateListId(listId).ok || !paths.validateStamp(String(stamp || '')).ok) {
            return { ok: false, error: 'INVALID_LIST_ID', code: 'INVALID_LIST_ID' };
        }
        const fp = paths.snapshotFilePath(listId, stamp);
        if (!fp) return { ok: false, error: 'INVALID_LIST_ID', code: 'INVALID_LIST_ID' };

        return withLock(`list:${listId}`, async () => {
            if (!(await fs.pathExists(ARCHIVE_SNAPSHOT_DIR))) return { ok: false, error: 'no snapshots' };
            const pending = await findPendingTxn(listId);
            if (pending) {
                return txnFailure('ARCHIVE_TXN_PENDING', false, pending.stamp,
                    'List has an unfinished transaction, manual recovery required.');
            }
            if (!(await fs.pathExists(fp))) return { ok: false, error: 'snapshot not found' };
            const snap = await fs.readJson(fp);
            if (!snap || !snap.activeBefore || !snap.archiveBefore) {
                return { ok: false, error: 'snapshot malformed' };
            }
            const listPath = paths.listFilePath(listId);
            if (!listPath || !(await fs.pathExists(listPath))) return { ok: false, error: 'list missing' };

            const activeBefore = clone(await fs.readJson(listPath));
            const archivePath = archivePathFor(listId);
            if (!archivePath) return { ok: false, error: 'INVALID_LIST_ID', code: 'INVALID_LIST_ID' };
            const archiveExisted = await fs.pathExists(archivePath);
            const archiveBefore = archiveExisted
                ? clone(await fs.readJson(archivePath))
                : { listId, items: [] };

            const active = clone(snap.activeBefore);
            const archive = clone(snap.archiveBefore);
            active.updatedAt = new Date().toISOString();
            archive.lastArchivedAt = new Date().toISOString();

            const txnId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
            const txnFile = txnFilePath(listId, txnId);
            const record = {
                listId, action: 'archive-restore', phase: 'prepared',
                snapshotFile: path.basename(fp), stamp: snap.stamp,
                startedAt: new Date().toISOString(),
            };
            await atomicWriteJson(txnFile, record);
            const update = (phase) => atomicWriteJson(txnFile, { ...record, phase });

            let wroteList = false;
            let wroteArchive = false;
            try {
                await atomicWriteJson(listPath, active);
                wroteList = true;
                await update('first-written');
                if (drillOn('crash-after-first-write')) process.exit(1);
                if (drillOn('restore-archive-write')) throw new Error('DRILL_RESTORE_ARCHIVE_WRITE');

                const haveArchive = archive.items && archive.items.length;
                if (haveArchive || archiveExisted) {
                    await fs.ensureDir(ARCHIVE_DIR);
                    await atomicWriteJson(archivePath, archive);
                    wroteArchive = true;
                }
                await update('list-written');
                await fs.remove(txnFile).catch(() => {});
                return {
                    ok: true,
                    restoredActive: (active.items || []).length,
                    restoredArchive: (archive.items || []).length,
                    stamp: snap.stamp,
                };
            } catch (err) {
                let rollbackOk = true;
                try {
                    if (wroteArchive) await restoreFile(archivePath, archiveBefore);
                    if (wroteList) await restoreFile(listPath, activeBefore);
                } catch (_rollbackErr) {
                    rollbackOk = false;
                }
                if (rollbackOk) {
                    await fs.remove(txnFile).catch(() => {});
                    await auditTxnFailure('archive-restore', listId, 'ARCHIVE_TXN_FAILED', snap.stamp, actor);
                    return txnFailure('ARCHIVE_TXN_FAILED', true, snap.stamp,
                        'Archive restore transaction failed, rolled back to prior state.');
                }
                await auditTxnFailure('archive-restore', listId, 'ARCHIVE_TXN_MANUAL_RECOVERY', snap.stamp, actor);
                return txnFailure('ARCHIVE_TXN_MANUAL_RECOVERY', false, snap.stamp,
                    'Archive restore transaction failed and rollback incomplete, manual recovery required.');
            }
        });
    };

    // P1-2: a top-level item is archivable only when its whole subtree is closed
    // (the "keep-whole-tree" rule). A parent-not-done or any-child-not-done case
    // keeps the entire subtree in place — completed children are NOT split off.
    const isFullyClosed = (it) => {
        if (!it || !it.isDone) return false;
        for (const sub of (it.subTasks || [])) {
            if (!isFullyClosed(sub)) return false;
        }
        return true;
    };

    // Pulls every fully-closed top-level subtree (and only those) out of `items`.
    // Partially-closed subtrees stay whole in `kept`. Returns { kept, moved }.
    const splitClosed = (items, listId, listName, onlyIds = null) => {
        const kept = [];
        const moved = [];
        const stamp = new Date().toISOString();
        for (const it of (items || [])) {
            if (!it || typeof it !== 'object') continue;
            if ((!onlyIds || onlyIds.has(it.itemId)) && isFullyClosed(it)) {
                moved.push({ ...it, archivedAt: stamp, archivedFrom: listId });
            } else {
                kept.push(it);
            }
        }
        return { kept, moved };
    };

    const archiveList = async (listId, onlyIds = null, actor = null) => withLock(`list:${listId}`, async () => {
        const listPath = paths.listFilePath(listId);
        if (!listPath) return { error: 'INVALID_LIST_ID' };
        if (!(await fs.pathExists(listPath))) return null;

        const pending = await findPendingTxn(listId);
        if (pending) {
            return txnFailure('ARCHIVE_TXN_PENDING', false, pending.stamp,
                'List has an unfinished transaction, manual recovery required.');
        }

        const data = await fs.readJson(listPath);
        const archive = await readArchive(listId);
        const { kept, moved } = splitClosed(data.items, listId, data.listName, onlyIds);
        if (!moved.length) return { moved: 0, remaining: (data.items || []).length, archiveCount: (archive.items || []).length };

        // P1-4: capture the exact pre-mutation state of BOTH files before writing.
        // A snapshot failure aborts the archive so we never move items without a
        // rollback path.
        const activeBefore = clone(data);
        const archiveBefore = clone(archive);
        const snap = await writeArchiveSnapshot(listId, data.listName, activeBefore, archiveBefore);
        if (!snap) return { error: 'INVALID_LIST_ID' };

        const archiveAfter = clone(archive);
        archiveAfter.listId = listId;
        archiveAfter.listName = data.listName;
        archiveAfter.category = data.category;
        archiveAfter.items = [...(archiveAfter.items || []), ...moved];
        archiveAfter.lastArchivedAt = new Date().toISOString();

        const activeAfter = clone(data);
        activeAfter.items = kept;
        activeAfter.rev = contentRev(kept);
        activeAfter.updatedAt = new Date().toISOString();

        const archivePath = archivePathFor(listId);
        if (!archivePath) return { error: 'INVALID_LIST_ID' };
        const archiveExisted = await fs.pathExists(archivePath);

        const txnId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const txnFile = txnFilePath(listId, txnId);
        const record = {
            listId, action: 'archive', phase: 'prepared',
            snapshotFile: path.basename(snap.file), stamp: snap.stamp,
            startedAt: new Date().toISOString(),
        };
        await atomicWriteJson(txnFile, record);
        const update = (phase) => atomicWriteJson(txnFile, { ...record, phase });

        let wroteArchive = false;
        let wroteList = false;
        try {
            await fs.ensureDir(ARCHIVE_DIR);
            await atomicWriteJson(archivePath, archiveAfter);
            wroteArchive = true;
            await update('first-written');
            if (drillOn('crash-after-first-write')) process.exit(1);
            if (drillOn('archive-list-write')) throw new Error('DRILL_ARCHIVE_LIST_WRITE');

            await atomicWriteJson(listPath, activeAfter);
            wroteList = true;
            await update('list-written');
            await fs.remove(txnFile).catch(() => {});
            return { moved: moved.length, remaining: kept.length, archiveCount: archiveAfter.items.length };
        } catch (err) {
            let rollbackOk = true;
            try {
                if (wroteList) await restoreFile(listPath, activeBefore);
                if (wroteArchive) await restoreFileOrRemove(archivePath, archiveBefore, archiveExisted);
            } catch (_rollbackErr) {
                rollbackOk = false;
            }
            if (rollbackOk) {
                // REQ-P1-TXN-07: a failed action leaves the snapshot set as it
                // was. The snapshot this attempt created is discarded; snapshots
                // that existed before the action are untouched.
                await fs.remove(snap.file).catch(() => {});
                await fs.remove(txnFile).catch(() => {});
                await auditTxnFailure('archive', listId, 'ARCHIVE_TXN_FAILED', snap.stamp, actor);
                return txnFailure('ARCHIVE_TXN_FAILED', true, snap.stamp,
                    'Archive transaction failed, rolled back to prior state.');
            }
            await auditTxnFailure('archive', listId, 'ARCHIVE_TXN_MANUAL_RECOVERY', snap.stamp, actor);
            return txnFailure('ARCHIVE_TXN_MANUAL_RECOVERY', false, snap.stamp,
                'Archive transaction failed and rollback incomplete, manual recovery required.');
        }
    });

    // Startup sweep: keep active files small without waiting for a manual trigger.
    // Lists named in categories.json -> archive.protected are project records: they
    // are skipped, and the skip is logged when they are over the threshold so the
    // exception never becomes an invisible one.
    const autoArchiveSweep = async () => {
        const policy = await getArchivePolicy();
        if (!policy.enabled) {
            console.log('[LiteTask] Auto-archive disabled (LITETASK_AUTO_ARCHIVE=0).');
            return;
        }
        try {
            const files = (await fs.readdir(SHARED_LISTS_DIR))
                .filter(f => f.toLowerCase().endsWith('.json'))
                .filter(f => paths.validateListId(path.basename(f, '.json')).ok);
            for (const file of files) {
                const listId = file.replace(/\.json$/, '');
                const data = await fs.readJson(path.join(SHARED_LISTS_DIR, file));
                const closedTop = (data.items || []).filter(i => i && i.isDone).length;

                if (policy.protected.indexOf(listId) !== -1) {
                    if (closedTop >= policy.minClosed) {
                        console.log(`[LiteTask] ${listId}: ${closedTop} closed item(s) at or over threshold ${policy.minClosed} — protected in categories.json, not auto-archived.`);
                    }
                    continue;
                }

                if (closedTop >= policy.minClosed) {
                    const r = await archiveList(listId);
                    if (r && r.moved) console.log(`[LiteTask] Auto-archived ${r.moved} closed item(s) from ${listId} (threshold ${policy.minClosed}).`);
                } else if (policy.warnWithin > 0 && closedTop >= policy.minClosed - policy.warnWithin) {
                    console.warn(`[LiteTask] ${listId}: ${closedTop} closed item(s) — ${policy.minClosed - closedTop} more will trigger auto-archive on the next start.`);
                }
            }
        } catch (err) {
            console.warn('[LiteTask] Auto-archive sweep skipped:', err.message);
        }
    };

    /* ---------------------------------------------------------------------------
     * Unarchive (P1) — the way back out of the archive
     *
     * 2026-10-29: a manual archive moved 17 items of `arch` into data/archive and
     * there was no path back; they were recovered by hand from git (commit b780480).
     * A one-way archive is a data-loss button, so this endpoint is the first half of
     * the P1 rework (selection and the "maximal closed subtree" rule come later).
     *
     * Restored entries are appended — top-level ones to the end of the list,
     * subtasks to the end of their parent's subTasks. The archive records no
     * position, so the round-trip preserves content and structure, not order.
     * ------------------------------------------------------------------------- */
    const stripArchiveMarkers = (it) => {
        const { archivedAt, archivedFrom, parentItemId, parentTitle, ...rest } = it;   // eslint-disable-line no-unused-vars
        return rest;
    };

    const indexById = (items) => {
        const map = new Map();
        const walk = (arr) => (arr || []).forEach(it => {
            if (!it || !it.itemId || map.has(it.itemId)) return;
            map.set(it.itemId, it);
            walk(it.subTasks);
        });
        walk(items);
        return map;
    };

    const unarchiveList = async (listId, itemIds) => withLock(`list:${listId}`, async () => {
        const listPath = paths.listFilePath(listId);
        if (!listPath) return { error: 'INVALID_LIST_ID' };
        if (!(await fs.pathExists(listPath))) return null;
        const archive = await readArchive(listId);
        const archived = archive.items || [];
        const emptyRun = { moved: 0, reattached: 0, orphaned: 0, archiveCount: archived.length };
        if (!archived.length) return { ...emptyRun, remaining: 0 };

        const wanted = new Set((Array.isArray(itemIds) && itemIds.length)
            ? itemIds : archived.map(i => i && i.itemId));
        const known = new Set(archived.map(i => i && i.itemId));
        const unknown = [...wanted].filter(id => !known.has(id));
        if (unknown.length) return { error: 'UNKNOWN_ARCHIVED_ITEM', unknown };

        const chosen = archived.filter(i => i && wanted.has(i.itemId));
        if (!chosen.length) {
            return { ...emptyRun, remaining: (await fs.readJson(listPath)).items.length };
        }

        const data = await fs.readJson(listPath);
        const items = Array.isArray(data.items) ? [...data.items] : [];
        const byId = indexById(items);
        const chosenIds = new Set(chosen.map(i => i.itemId));

        // A subtask whose parent is restored in this same call has to wait for it,
        // so unresolved ones go back on the queue instead of being orphaned. The
        // pass cap is a guard, not a depth limit: every queued entry is either
        // attached or appended, so the queue drains.
        let reattached = 0;
        let orphaned = 0;
        const queue = [...chosen];
        let guard = chosen.length * 4 + 20;
        while (queue.length && guard > 0) {
            guard -= 1;
            const it = queue.shift();
            const pid = it.parentItemId;
            const parent = pid ? byId.get(pid) : null;
            if (parent) {
                if (!Array.isArray(parent.subTasks)) parent.subTasks = [];
                const restored = stripArchiveMarkers(it);
                parent.subTasks.push(restored);
                byId.set(restored.itemId, restored);
                reattached += 1;
                continue;
            }
            if (pid && chosenIds.has(pid) && guard > 1) {
                queue.push(it);          // its parent is still queued
                continue;
            }
            const restored = stripArchiveMarkers(it);
            items.push(restored);
            byId.set(restored.itemId, restored);
            if (pid) orphaned += 1;      // parent is neither live nor in this batch
        }
        for (const it of queue) {         // guard exhausted: never lose an entry
            items.push(stripArchiveMarkers(it));
            if (it.parentItemId) orphaned += 1;
        }

        const kept = archived.filter(i => i && !wanted.has(i.itemId));
        archive.items = kept;
        if (!kept.length) {
            await fs.remove(archivePathFor(listId)).catch(() => {});
        } else {
            await atomicWriteJson(archivePathFor(listId), archive);
        }

        data.items = items;
        data.rev = contentRev(items);
        data.updatedAt = new Date().toISOString();
        await atomicWriteJson(listPath, data);
        return { moved: chosen.length, reattached, orphaned, remaining: items.length, archiveCount: kept.length };
    });

    // P1-1: read-only preview of what an archive sweep would move, under the
    // "keep-whole-tree" rule (parent not done -> whole subtree kept; child not done
    // -> whole subtree kept). Never mutates the list. isFullyClosed lives above
    // splitClosed and is reused here.
    const flattenClosedSubtree = (it, level, acc) => {
        acc.push({ itemId: it.itemId, title: it.title, level, isTop: level === 0 });
        for (const sub of (it.subTasks || [])) flattenClosedSubtree(sub, level + 1, acc);
    };

    /* P1-4 startup recovery lives in archive_txn.js; exported for server use. */

    return {
        getArchivePolicy,
        archivePathFor,
        readArchive,
        snapshotFileFor,
        writeArchiveSnapshot,
        pruneArchiveSnapshots,
        listArchiveSnapshots,
        restoreArchiveSnapshot,
        isFullyClosed,
        splitClosed,
        archiveList,
        autoArchiveSweep,
        recoverInterruptedTransactions,
        stripArchiveMarkers,
        indexById,
        unarchiveList,
        flattenClosedSubtree,
    };
};

module.exports = { createArchiveCore };
