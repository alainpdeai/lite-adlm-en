'use strict';
const path = require('path');
const fs = require('fs-extra');

const cfg = require('./config');
const logging = require('./logging');
const paths = require('./paths');
const errors = require('./errors');

const { SHARED_LISTS_DIR } = cfg;
const { writeAudit } = logging;

// Archive HTTP surface (route ①, Round 8). The six archive routes, verbatim from
// the old archive.js register(); they only differ in that the data helpers now
// arrive through `core` and `requireConfirm` through `deps`, which is exactly what
// the original closure provided.
const createArchiveRoutes = (app, io, deps) => {
    const requireConfirm = deps.requireConfirm;
    const core = deps.core;

    const {
        getArchivePolicy, readArchive, listArchiveSnapshots, restoreArchiveSnapshot,
        archiveList, unarchiveList, isFullyClosed, flattenClosedSubtree
    } = core;

    app.post('/api/lists/:id/archive', async (req, res) => {
        const listId = req.listId || req.params.id;
        if (!paths.validateListId(listId).ok) {
            return errors.sendError(res, 400, 'INVALID_LIST_ID', 'Invalid list identifier');
        }
        const actor = req.actor || {};
        if (!actor.isAdmin) {
            return res.status(403).json({
                error: 'Forbidden: Only administrators can archive lists',
                code: 'ADMIN_REQUIRED',
            });
        }
        const userId = actor.userId || null;
        // Security boundary P2-C hard gate: archiving moves closed items out of the active list.
        // An affirmative `confirm: true` is required — an omitted field is no longer
        // read as "the UI already asked", because a script that never asked omits
        // it too and the server cannot tell the two apart.
        const gate = requireConfirm(req, 'Archiving will move closed items out of the active list');
        if (gate) return res.status(400).json(gate);
        try {
            // P1-3: optional whitelist — only archive the checked candidates.
            const rawIds = req.body.itemIds;
            const onlyIds = Array.isArray(rawIds) && rawIds.length
                ? new Set(rawIds.map(String)) : null;
            const r = await archiveList(listId, onlyIds, actor);
            if (r && r.txnFailure) {
                return res.status(500).json({
                    error: r.error, code: r.code,
                    compensated: r.compensated, snapshotStamp: r.snapshotStamp,
                });
            }
            if (!r) return res.status(404).json({ error: 'List not found' });
            await writeAudit({
                actor: userId, action: 'archive', listId,
                confirmed: 'explicit',
                params: req.body || {},
                note: `${r.moved} item(s) moved to archive, ${r.remaining} remaining`,
            });
            res.json({ success: true, ...r });
        } catch (err) {
            res.status(500).json({ error: 'Failed to archive list' });
        }
    });

    // P1-4: list the snapshots a list has accumulated (audit trail).
    app.get('/api/lists/:id/archive-snapshots', async (req, res) => {
        const listId = req.listId || req.params.id;
        if (!paths.validateListId(listId).ok) {
            return errors.sendError(res, 400, 'INVALID_LIST_ID', 'Invalid list identifier');
        }
        const actor = req.actor || {};
        if (!actor.isAdmin) {
            return res.status(403).json({
                error: 'Forbidden: Only administrators can view archive snapshots',
                code: 'ADMIN_REQUIRED',
            });
        }
        try {
            const snaps = await listArchiveSnapshots(listId);
            res.json({ listId, count: snaps.length, snapshots: snaps });
        } catch (err) {
            res.status(500).json({ error: 'Failed to list archive snapshots' });
        }
    });

    // P1-4: roll a list back to the state captured by one snapshot (reverse a single
    // archive action). Stamp is the snapshot's `stamp` field.
    app.post('/api/lists/:id/archive-restore', async (req, res) => {
        const listId = req.listId || req.params.id;
        if (!paths.validateListId(listId).ok) {
            return errors.sendError(res, 400, 'INVALID_LIST_ID', 'Invalid list identifier');
        }
        const actor = req.actor || {};
        if (!actor.isAdmin) {
            return res.status(403).json({
                error: 'Forbidden: Only administrators can restore archive snapshots',
                code: 'ADMIN_REQUIRED',
            });
        }
        const userId = actor.userId || null;
        const stamp = req.body && req.body.stamp;
        if (!stamp) return res.status(400).json({ error: 'stamp is required', code: 'INVALID_STAMP' });
        // P0-1: the stamp is an address key too; reject it before the archive lock.
        if (!paths.validateStamp(stamp).ok) {
            return errors.sendError(res, 400, 'INVALID_STAMP', 'Invalid snapshot timestamp');
        }
        // Security boundary P2-C hard gate: rolling a list back rewrites it wholesale — whatever
        // the snapshot does not carry is dropped. Same gate as archiving.
        const gate = requireConfirm(req, 'Snapshot restore will overwrite the active list');
        if (gate) return res.status(400).json(gate);
        try {
            const r = await restoreArchiveSnapshot(listId, stamp, actor);
            if (r && r.txnFailure) {
                return res.status(500).json({
                    error: r.error, code: r.code,
                    compensated: r.compensated, snapshotStamp: r.snapshotStamp,
                });
            }
            if (!r || !r.ok) return res.status(404).json({ error: r && r.error ? r.error : 'restore failed' });
            await writeAudit({
                actor: userId, action: 'archive-restore', listId,
                confirmed: 'explicit',
                params: req.body || {},
                note: `rolled back to snapshot ${stamp}`,
            });
            res.json({ success: true, ...r });
        } catch (err) {
            res.status(500).json({ error: 'Failed to restore archive snapshot' });
        }
    });

    app.post('/api/lists/:id/unarchive', async (req, res) => {
        const listId = req.listId || req.params.id;
        const listPath = paths.listFilePath(listId);
        if (!listPath) return errors.sendError(res, 400, 'INVALID_LIST_ID', 'Invalid list identifier');
        const actor = req.actor || {};
        if (!actor.isAdmin) {
            return res.status(403).json({
                error: 'Forbidden: Only administrators can unarchive lists',
                code: 'ADMIN_REQUIRED',
            });
        }
        const userId = actor.userId || null;
        try {
            if (req.body.baseRev) {
                const cur = await fs.readJson(listPath).catch(() => null);
                if (cur && cur.rev && cur.rev !== req.body.baseRev) {
                    return res.status(409).json({
                        code: 'REV_CONFLICT',
                        error: 'List changed since this request was built; reload and retry.'
                    });
                }
            }
            const itemIds = Array.isArray(req.body.itemIds) ? req.body.itemIds : null;
            const r = await unarchiveList(listId, itemIds);
            if (!r) return res.status(404).json({ error: 'List not found' });
            if (r.error === 'UNKNOWN_ARCHIVED_ITEM') {
                return res.status(400).json({
                    code: r.error,
                    error: 'These ids are not in the archive: ' + r.unknown.join(', '),
                    unknown: r.unknown
                });
            }
            await writeAudit({
                actor: userId, action: 'unarchive', listId,
                params: {
                    moved: r.moved, reattached: r.reattached,
                    orphaned: r.orphaned, archiveCount: r.archiveCount,
                },
                note: `moved ${r.moved} item(s) from the archive `
                    + `(reattached ${r.reattached}, orphaned ${r.orphaned})`,
            });
            res.json({ success: true, ...r });
        } catch (err) {
            res.status(500).json({ error: 'Failed to unarchive list' });
        }
    });

    app.get('/api/lists/:id/archive-preview', async (req, res) => {
        const listId = req.listId || req.params.id;
        const listPath = paths.listFilePath(listId);
        if (!listPath) return errors.sendError(res, 400, 'INVALID_LIST_ID', 'Invalid list identifier');
        if (!(await fs.pathExists(listPath))) {
            return res.status(404).json({ error: 'List not found' });
        }
        try {
            const data = await fs.readJson(listPath);
            const items = data.items || [];
            const candidates = [];
            const excluded = [];
            let hasPartial = false;
            for (const it of items) {
                if (isFullyClosed(it)) {
                    flattenClosedSubtree(it, 0, candidates);
                } else {
                    const reason = !it.isDone
                        ? 'Parent task unfinished (subtree preserved per keep-whole-tree rule)'
                        : 'Contains unfinished subtasks (subtree preserved per keep-whole-tree rule)';
                    excluded.push({ itemId: it.itemId, title: it.title, reason });
                    hasPartial = true;
                }
            }
            res.json({
                listId,
                listName: data.listName || '',
                candidates,
                excluded,
                hasPartialCompletion: hasPartial,
                totalMovable: candidates.length
            });
        } catch (err) {
            res.status(500).json({ error: 'Failed to compute archive preview' });
        }
    });

    // Read-only view of the auto-archive policy and of what a sweep would do right
    // now. `wouldArchive` is the exact predicate autoArchiveSweep() applies, so the
    // decision is inspectable without restarting the server.
    app.get('/api/archive-status', async (req, res) => {
        try {
            const policy = await getArchivePolicy();
            const files = (await fs.readdir(SHARED_LISTS_DIR))
                .filter(f => f.toLowerCase().endsWith('.json'))
                .filter(f => paths.validateListId(path.basename(f, '.json')).ok);
            const lists = [];
            for (const file of files) {
                const listId = file.replace(/\.json$/, '');
                const data = await fs.readJson(path.join(SHARED_LISTS_DIR, file));
                const items = data.items || [];
                const closed = items.filter(i => i && i.isDone).length;
                const isProtected = policy.protected.indexOf(listId) !== -1;
                const distance = policy.minClosed - closed;
                lists.push({
                    listId,
                    listName: data.listName || '',
                    category: data.category || '',
                    total: items.length,
                    closed,
                    threshold: policy.minClosed,
                    protected: isProtected,
                    wouldArchive: policy.enabled && !isProtected && closed >= policy.minClosed,
                    untilArchive: isProtected ? null : (distance > 0 ? distance : 0),
                    warning: policy.enabled && !isProtected && policy.warnWithin > 0
                        && closed >= policy.minClosed - policy.warnWithin && closed < policy.minClosed
                });
            }
            lists.sort((a, b) => a.listId.localeCompare(b.listId));
            res.json({
                enabled: policy.enabled,
                minClosed: policy.minClosed,
                warnWithin: policy.warnWithin,
                thresholdSource: policy.minSource,
                protected: policy.protected,
                lists
            });
        } catch (err) {
            res.status(500).json({ error: 'Failed to read archive status' });
        }
    });

    app.get('/api/archive/:id', async (req, res) => {
        const listId = req.listId || req.params.id;
        if (!paths.validateListId(listId).ok) {
            return errors.sendError(res, 400, 'INVALID_LIST_ID', 'Invalid list identifier');
        }
        try {
            const doc = await readArchive(listId);
            res.json({ listId: doc.listId, listName: doc.listName || '', items: doc.items || [], lastArchivedAt: doc.lastArchivedAt || null });
        } catch (err) {
            res.status(500).json({ error: 'Failed to read archive' });
        }
    });
};

module.exports = { createArchiveRoutes };
