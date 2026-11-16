'use strict';

// P1-4 transaction support, extracted from archive_core so both modules stay
// under the 500-line first-party budget. Records live beside snapshots with a
// `.txn.json` suffix so they never enter the snapshot quota.

const path = require('path');
const fs = require('fs-extra');

const cfg = require('./config');
const util = require('./util');
const paths = require('./paths');

const { ARCHIVE_DIR, ARCHIVE_SNAPSHOT_DIR } = cfg;
const { atomicWriteJson, withLock } = util;

const TXN_SUFFIX = '.txn.json';

const createTxnSupport = (deps) => {
    const writeAudit = deps && deps.writeAudit;

    const drillFaults = () => String(process.env.LITETASK_DRILL_FAULT || '')
        .split(',').map(s => s.trim()).filter(Boolean);
    const drillOn = (name) => drillFaults().includes(name);

    const txnFilePath = (listId, txnId) =>
        path.join(ARCHIVE_SNAPSHOT_DIR, `${listId}-${txnId}${TXN_SUFFIX}`);

    const listTxnFiles = async (listId) => {
        if (!(await fs.pathExists(ARCHIVE_SNAPSHOT_DIR))) return [];
        const prefix = paths.snapshotFilePrefix(listId);
        if (!prefix) return [];
        return (await fs.readdir(ARCHIVE_SNAPSHOT_DIR))
            .filter(f => f.startsWith(prefix) && f.endsWith(TXN_SUFFIX))
            .sort();
    };

    const findPendingTxn = async (listId) => {
        const files = await listTxnFiles(listId);
        if (!files.length) return null;
        const fp = path.join(ARCHIVE_SNAPSHOT_DIR, files[0]);
        try { return await fs.readJson(fp); } catch { return { phase: 'unreadable', listId }; }
    };

    const clone = (doc) => JSON.parse(JSON.stringify(doc));

    const txnFailure = (code, compensated, stamp, message) => ({
        ok: false, txnFailure: true, status: 500, code,
        compensated: Boolean(compensated), snapshotStamp: stamp || null,
        error: message || code,
    });

    const auditTxnFailure = async (action, listId, code, stamp, actor) => {
        if (typeof writeAudit !== 'function') return;
        try {
            await writeAudit({
                actor: (actor && actor.userId) || null, action, listId,
                outcome: 'failed', params: {},
                note: `code=${code}; stamp=${stamp || ''}`,
            });
        } catch (_err) { /* audit is best-effort */ }
    };

    const restoreFile = async (p, doc) => {
        if (drillOn('compensate')) throw new Error('DRILL_COMPENSATE');
        await atomicWriteJson(p, clone(doc));
    };

    const restoreFileOrRemove = async (p, doc, existed) => {
        if (!existed) { await fs.remove(p).catch(() => {}); return; }
        await restoreFile(p, doc);
    };

    const recoverInterruptedTransactions = async () => {
        const out = { recovered: 0, committed: 0, failed: 0 };
        if (!(await fs.pathExists(ARCHIVE_SNAPSHOT_DIR))) return out;
        const files = (await fs.readdir(ARCHIVE_SNAPSHOT_DIR))
            .filter(f => f.endsWith(TXN_SUFFIX));
        for (const fn of files) {
            const fp = path.join(ARCHIVE_SNAPSHOT_DIR, fn);
            let rec = null;
            try { rec = await fs.readJson(fp); } catch (_err) {
                console.warn(`[LiteTask] Transaction record unparseable, kept for manual review: ${fn}`);
                out.failed += 1;
                continue;
            }
            if (!rec || !paths.validateListId(rec.listId || '').ok) {
                console.warn(`[LiteTask] Transaction record missing valid listId, kept for manual review: ${fn}`);
                out.failed += 1;
                continue;
            }
            await withLock(`list:${rec.listId}`, async () => {
                if (rec.phase === 'list-written') {
                    await fs.remove(fp).catch(() => {});
                    out.committed += 1;
                    return;
                }
                const snapPath = paths.snapshotFilePath(rec.listId, rec.stamp);
                let snap = null;
                try { snap = snapPath ? await fs.readJson(snapPath) : null; } catch (_err) { snap = null; }
                if (!snap || !snap.activeBefore || !snap.archiveBefore) {
                    console.warn(`[LiteTask] Transaction record missing usable snapshot, kept for manual review: ${fn}`);
                    out.failed += 1;
                    return;
                }
                try {
                    const listPath = paths.listFilePath(rec.listId);
                    if (!listPath) throw new Error('INVALID_LIST_ID');
                    await atomicWriteJson(listPath, clone(snap.activeBefore));
                    await fs.ensureDir(ARCHIVE_DIR);
                    const archivePath = paths.archiveFilePath(rec.listId);
                    if (!archivePath) throw new Error('INVALID_LIST_ID');
                    const haveArchive = (snap.archiveBefore.items || []).length;
                    if (haveArchive) {
                        await atomicWriteJson(archivePath, clone(snap.archiveBefore));
                    } else if (await fs.pathExists(archivePath)) {
                        await fs.remove(archivePath).catch(() => {});
                    }
                    await fs.remove(fp).catch(() => {});
                    out.recovered += 1;
                } catch (err) {
                    console.warn(`[LiteTask] Startup recovery failed, kept record: ${fn} (${err.message})`);
                    out.failed += 1;
                }
            });
        }
        if (out.failed > 0) {
            console.warn(`[LiteTask] ${out.failed} unfinished transaction(s) require manual recovery (see data/archive-snapshots/*.txn.json)`);
        }
        return out;
    };

    return {
        TXN_SUFFIX, drillOn, txnFilePath, listTxnFiles, findPendingTxn,
        clone, txnFailure, auditTxnFailure, restoreFile, restoreFileOrRemove,
        recoverInterruptedTransactions,
    };
};

module.exports = { createTxnSupport };