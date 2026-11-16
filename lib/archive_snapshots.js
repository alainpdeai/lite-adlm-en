'use strict';

// P1-4 snapshot support, extracted to keep archive_core under the 500-line
// first-party budget. Pure data helpers; no Express, no register().

const path = require('path');
const fs = require('fs-extra');

const cfg = require('./config');
const util = require('./util');
const paths = require('./paths');

const { ARCHIVE_SNAPSHOT_DIR, MAX_ARCHIVE_SNAPSHOTS } = cfg;
const { atomicWriteJson } = util;

const snapshotFileFor = (listId, stamp) => paths.snapshotFilePath(listId, stamp);

const pruneArchiveSnapshots = async (listId) => {
    try {
        if (!(await fs.pathExists(ARCHIVE_SNAPSHOT_DIR))) return;
        const prefix = paths.snapshotFilePrefix(listId);
        if (!prefix) return;
        const files = (await fs.readdir(ARCHIVE_SNAPSHOT_DIR))
            .filter(f => f.startsWith(prefix) && f.endsWith('.snapshot.json'))
            .sort();
        const excess = files.length - MAX_ARCHIVE_SNAPSHOTS;
        for (let i = 0; i < excess; i++) {
            await fs.remove(path.join(ARCHIVE_SNAPSHOT_DIR, files[i])).catch(() => {});
        }
    } catch (err) {
        console.warn('[LiteTask] snapshot prune skipped:', err.message);
    }
};

const writeArchiveSnapshot = async (listId, listName, activeBefore, archiveBefore) => {
    const stamp = new Date().toISOString();
    const snap = { listId, listName, stamp, activeBefore, archiveBefore };
    await fs.ensureDir(ARCHIVE_SNAPSHOT_DIR);
    const f = snapshotFileFor(listId, stamp);
    if (!f) return null;
    await atomicWriteJson(f, snap);
    await pruneArchiveSnapshots(listId);
    return { file: f, stamp };
};

const listArchiveSnapshots = async (listId) => {
    const prefix = paths.snapshotFilePrefix(listId);
    if (!prefix) return [];
    if (!(await fs.pathExists(ARCHIVE_SNAPSHOT_DIR))) return [];
    const files = (await fs.readdir(ARCHIVE_SNAPSHOT_DIR))
        .filter(f => f.startsWith(prefix) && f.endsWith('.snapshot.json'))
        .sort().reverse();
    const out = [];
    for (const fn of files) {
        try {
            const snap = await fs.readJson(path.join(ARCHIVE_SNAPSHOT_DIR, fn));
            const activeIds = (snap.activeBefore && snap.activeBefore.items || []).map(i => i.itemId);
            const archiveIds = (snap.archiveBefore && snap.archiveBefore.items || []).map(i => i.itemId);
            out.push({
                file: fn,
                stamp: snap.stamp,
                listName: snap.listName,
                activeItemCount: activeIds.length,
                archiveItemCount: archiveIds.length,
                movedAway: activeIds.length,
            });
        } catch (_err) { /* skip a corrupt snapshot file */ }
    }
    return out;
};

const createSnapshotSupport = () => ({
    snapshotFileFor, writeArchiveSnapshot, pruneArchiveSnapshots, listArchiveSnapshots,
});

module.exports = { createSnapshotSupport };