'use strict';
const path = require('path');
const fs = require('fs-extra');

const cfg = require('./config');
const util = require('./util');
const logging = require('./logging');
const paths = require('./paths');
const errors = require('./errors');
const { sanitizeItems } = require('./schema');

const { SHARED_LISTS_DIR } = cfg;
const { contentRev, atomicWriteJson, withLock, diffItems } = util;
const { writeAudit } = logging;

// Lists HTTP surface (route ①, Round 9): the four /api/lists routes plus the
// read-only /api/integrity report. Verbatim from the old lib/lists.js register(),
// except that the shared helpers now arrive through `core` and the injected
// validators through `deps`.
const createListRoutes = (app, io, deps) => {
    const core = deps.core;
    const {
        getStatusConfig, collectStatuses, sanitizeStatus, validateItems,
        sanitizeRelatesTo, sanitizeLocalDirectories
    } = deps;

    const {
        listsETag, answerWithETag, actorOf, changeEvent, requireConfirm,
        collectItemIds, indexAllItemIds
    } = core;

    // Lists API - Shared across all users
    app.get('/api/lists', async (req, res) => {
        try {
            await fs.ensureDir(SHARED_LISTS_DIR);
            const files = await fs.readdir(SHARED_LISTS_DIR);
            const lists = [];
            for (const file of files) {
                if (!file.toLowerCase().endsWith('.json')) continue;
                if (!paths.validateListId(path.basename(file, '.json')).ok) continue;
                const data = await fs.readJson(path.join(SHARED_LISTS_DIR, file));
                // B3: expose the optimistic-concurrency token the client must send back
                data.rev = contentRev(data.items);
                lists.push(data);
            }
            lists.sort((a,b) => a.listId.localeCompare(b.listId));
            answerWithETag(req, res, listsETag(lists), lists);
        } catch (err) {
            res.status(500).json({ error: 'Failed to read shared lists' });
        }
    });

    // Incremental sync P3-A: one list, conditionally. The collection route above is the one
    // the board uses, but a caller that only touched one item should not have to
    // download all four lists to find out what happened.
    app.get('/api/lists/:id', async (req, res) => {
        const listId = req.params.id;
        const listPath = paths.listFilePath(listId);
        if (!listPath) return errors.sendError(res, 400, 'INVALID_LIST_ID', 'Invalid list identifier');
        try {
            const data = await fs.readJson(listPath);
            data.rev = contentRev(data.items);
            answerWithETag(req, res, `"${data.rev}"`, data);
        } catch (err) {
            if (err && (err.code === 'ENOENT' || err.code === 'ENOTDIR')) {
                return res.status(404).json({ error: 'List not found', code: 'LIST_NOT_FOUND' });
            }
            res.status(500).json({ error: 'Failed to read list' });
        }
    });

    app.post('/api/lists', async (req, res) => {
        try {
            const { listName } = req.body;
            if (!listName || !listName.trim()) {
                return res.status(400).json({ error: 'List name is required' });
            }
            await fs.ensureDir(SHARED_LISTS_DIR);
            const files = await fs.readdir(SHARED_LISTS_DIR);

            let maxId = 0;
            files.forEach(f => {
                const num = parseInt(f.split('.')[0]);
                if (!isNaN(num) && num > maxId) maxId = num;
            });
            const listId = String(maxId + 1).padStart(2, '0');
            const now = new Date();
            const pad = (n) => String(n).padStart(2, '0');
            const createdAt = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;

            const newList = {
                listId,
                listName: listName.trim(),
                owner: (req.actor && (req.actor.username || req.actor.userId)) || 'Shared',
                createdAt,
                items: [],
                rev: contentRev([])
            };

            const listPath = paths.listFilePath(listId);
            if (!listPath) return errors.sendError(res, 400, 'INVALID_LIST_ID', 'Invalid list identifier');
            await withLock('lists:create', async () => {
                await atomicWriteJson(listPath, newList);
            });
            res.json(newList);
        } catch (err) {
            res.status(500).json({ error: 'Failed to create list' });
        }
    });

    app.put('/api/lists/:id', async (req, res) => {
        const listId = req.params.id;
        const listPath = paths.listFilePath(listId);
        if (!listPath) return errors.sendError(res, 400, 'INVALID_LIST_ID', 'Invalid list identifier');

        try {
            const type = req.body && req.body.type;
            if (type === 'RENAME') {
                const { listName } = req.body;
                return await withLock(`list:${listId}`, async () => {
                    const data = await fs.readJson(listPath);
                    data.listName = listName.trim();
                    data.rev = contentRev(data.items);
                    await atomicWriteJson(listPath, data);
                    return res.json(data);
                });
            } else if (type === 'UPDATE_ITEMS') {
                const { items, baseRev, force } = req.body;
                const actor = req.actor || {};
                const userId = actor.userId || null;
                sanitizeRelatesTo(items);
                sanitizeLocalDirectories(items);
                // P2-5: comments are rebuilt from a whitelist before validation
                // and before contentRev, so a rejected write leaves no bytes.
                const sani = sanitizeItems(items);
                if (!sani.ok) {
                    return res.status(400).json({
                        error: 'Comment content exceeds maximum length',
                        code: sani.code || 'COMMENT_TOO_LONG',
                        limit: sani.limit, actual: sani.actual, itemId: sani.itemId,
                    });
                }
                // Contract & schema P1: reject malformed items before any disk write.
                const vchk = validateItems(items);
                if (!vchk.ok) {
                    return res.status(400).json({
                        error: `Invalid item data: ${vchk.errors[0].message}`
                            + (vchk.errors.length > 1 ? ` (${vchk.errors.length} errors total)` : ''),
                        code: 'INVALID_ITEM_SCHEMA',
                        violations: vchk.errors.slice(0, 20)
                    });
                }
                // B3 follow-up: an explicit force overwrites whatever is on disk. Only
                // sent after the user inspected the diff (or passed --force on the CLI).
                const forceOverwrite = force === true;
                return await withLock(`list:${listId}`, async () => {
                const data = await fs.readJson(listPath);

                // B3: optimistic concurrency. baseRev is the rev the client loaded.
                // A mismatch means the stored items changed since then (another tab,
                // another user, or a direct file edit) — refuse instead of clobbering.
                const serverRev = contentRev(data.items);
                if (baseRev && baseRev !== serverRev && !forceOverwrite) {
                    return res.status(409).json({
                        error: 'Conflict: this list was modified by someone else. Reload before saving.',
                        code: 'REV_CONFLICT',
                        serverRev,
                        items: data.items,
                        // Field-level comparison the UI renders for side-by-side diffing
                        diff: diffItems(items, data.items),
                        updatedAt: data.updatedAt || null,
                        updatedBy: data.updatedBy || null
                    });
                }
                if (forceOverwrite && baseRev && baseRev !== serverRev) {
                    const d = diffItems(items, data.items).counts;
                    console.log(`[B3] force overwrite list ${listId}: rev ${serverRev} -> (client ${baseRev}); ` +
                                `+${d.added} / -${d.removed} / ~${d.changed} items, ${d.fields} fields`);
                }

                // Check if non-admin user is trying to delete existing items or subtasks
                if (userId && !actor.isAdmin) {
                    const existingIds = collectItemIds(data.items);
                    const newIds = collectItemIds(items);

                    for (const id of existingIds) {
                        if (!newIds.has(id)) {
                            return res.status(403).json({ 
                                error: 'Forbidden: Regular users are not allowed to delete items from shared lists. Please close the task instead.',
                                code: 'ADMIN_REQUIRED'
                            });
                        }
                    }
                }

                // F1: clamp / validate workflow status + keep isDone in lockstep
                const sc = await getStatusConfig();
                const prevStatuses = collectStatuses(data.items, sc);
                const actorName = actor.username || null;
                const chk = sanitizeStatus(items, prevStatuses, sc, userId, actorName);
                if (!chk.ok) {
                    const v = chk.violation;
                    return res.status(400).json({
                        error: `Invalid status transition '${v.from} -> ${v.to}' (${v.title || v.itemId}). Allowed: ${v.allowed.join(' / ')}`,
                        code: 'INVALID_TRANSITION',
                        violation: v
                    });
                }

                // Testing system P1: an idempotent write is not an update. Rewriting
                // byte-identical items used to bump updatedAt/updatedBy and hit the
                // disk as a metadata-only diff — every grading run re-committed
                // exam/test with unchanged items, burying real business changes.
                // Identical content hash => there is nothing to record: answer 200
                // and touch neither updatedAt nor the file. Concurrency (baseRev)
                // and schema checks above still run first, so this cannot mask a
                // conflict or an illegal payload.
                const nextRev = contentRev(items);
                const prevRev = contentRev(data.items);
                if (nextRev === prevRev) {
                    // P2-3: the response must carry the authoritative revision even
                    // when the on-disk value is stale; never write it back.
                    return res.json({ ...data, rev: nextRev });
                }
                // Security Boundary P2-C / P2-A: a forced overwrite that drops items that
                // already exist is the most destructive thing this API can do — the
                // 2026-10-29 `arch` loss was exactly this shape. It needs an
                // explicit confirmation and it needs a trace.
                const beforeIds = new Set((data.items || [])
                    .filter(i => i && i.itemId).map(i => i.itemId));
                const afterIds = new Set((Array.isArray(items) ? items : [])
                    .filter(i => i && i.itemId).map(i => i.itemId));
                let removedCount = 0;
                for (const id of beforeIds) {
                    if (!afterIds.has(id)) removedCount++;
                }
                const destructive = !!forceOverwrite && removedCount > 0;
                if (destructive) {
                    const gate = requireConfirm(
                        req, `Full list overwrite will delete ${removedCount} existing item(s)`,
                        { removed: removedCount });
                    if (gate) return res.status(400).json(gate);
                }

                data.items = items;
                data.rev = nextRev;
                data.updatedAt = new Date().toISOString();
                data.updatedBy = userId || null;
                await atomicWriteJson(listPath, data);
                await writeAudit({
                    actor: userId,
                    action: destructive ? 'overwrite' : 'update-items',
                    listId,
                    // After the hard gate there is no "implicit" here: what passes the gate must be explicit confirmation.
                    confirmed: destructive ? 'explicit' : null,
                    params: req.body || {},
                    note: destructive
                        ? `forced overwrite dropped ${removedCount} existing item(s)`
                        : `${(items || []).length} item(s) written`,
                });
                io.emit('items-changed', changeEvent(listId, data.rev, {
                    source: 'api',
                    actor: await actorOf(userId),
                    items: (items || []).length,
                    summary: destructive
                        ? `overwrite dropped ${removedCount} item(s)`
                        : `${(items || []).length} item(s) written`,
                }));
                return res.json(data);
                });
            }
            res.status(400).json({ error: 'Unknown update type' });
        } catch (err) {
            // A genuinely missing list surfaces here as ENOENT (readJson); keep the
            // 404 semantics. Any other failure is a real 500.
            if (err && (err.code === 'ENOENT' || err.code === 'ENOTDIR')) {
                return res.status(404).json({ error: 'List not found', code: 'LIST_NOT_FOUND' });
            }
            res.status(500).json({ error: 'Failed to update list' });
        }
    });

    app.delete('/api/lists/:id', async (req, res) => {
        const listId = req.params.id;
        // P0-1: identifier first; the prefix guard also runs before this handler.
        const listPath = paths.listFilePath(listId);
        if (!listPath) return errors.sendError(res, 400, 'INVALID_LIST_ID', 'Invalid list identifier');
        const actor = req.actor || {};
        if (!actor.isAdmin) {
            return res.status(403).json({
                error: 'Forbidden: Only administrators can delete shared lists',
                code: 'ADMIN_REQUIRED',
            });
        }
        const userId = actor.userId || null;

        // Security Boundary P2-C hard gate: this endpoint removes a whole list file — the
        // single most destructive thing in the API — and until now it had no gate
        // at all, not even the old "confirm: false" one. It gets the same
        // affirmative confirmation as the other three, and the refusal names how
        // much would go with it.
        let itemCount = 0;
        if (await fs.pathExists(listPath)) {
            const doc = await fs.readJson(listPath).catch(() => null);
            itemCount = doc && Array.isArray(doc.items) ? doc.items.length : 0;
        }
        const gate = requireConfirm(req, `Deleting list will remove ${itemCount} item(s) together with it`);
        if (gate) return res.status(400).json(Object.assign(gate, { items: itemCount }));

        if (await fs.pathExists(listPath)) {
            await fs.remove(listPath);
        }
        // Security Boundary P2-A: deleting a list deletes every item in it.
        await writeAudit({
            actor: userId, action: 'delete-list', listId,
            confirmed: 'explicit',
            params: req.query || {},
            note: `list file removed (${itemCount} item(s) inside)`,
        });
        res.json({ success: true });
    });

    /* ---------------------------------------------------------------------------
     * Integrity Report P3-D + P3-E: dangling relations and duplicate itemIds.
     *
     * `relatesTo` is typed by hand and by Agents, and nothing has ever checked that
     * the thing on the other end exists. An edge to an item that was deleted, moved
     * to the archive or never created is invisible: the graph silently loses a link,
     * the gap report quietly stops counting it as coverage, and the board still
     * looks healthy. Likewise an itemId is only unique by convention — a copy/paste
     * across two lists makes two unrelated tasks share an identity, and every
     * per-item operation (relations, the new item endpoints, traces) then addresses
     * the wrong one.
     *
     * This is the cheap version: a READ-ONLY report, on purpose.
     *   * it never refuses a write — rejecting existing data would lock the board
     *     until somebody cleaned it by hand, and the honest first step is to see
     *     how much there is;
     *   * archived items count as existing, because F3 deliberately treats archived
     *     referrers as coverage evidence — reporting those as dangling would be
     *     noise dressed up as a finding;
     *   * a whole-list scan of four lists is milliseconds, so no cache.
     * The strict variant (refuse an edge whose target does not exist) is a separate
     * decision, and this report is what it would be based on.
     * ------------------------------------------------------------------------- */
    app.get('/api/integrity', async (req, res) => {
        try {
            const index = await indexAllItemIds();
            const seen = new Map();       // itemId -> [{listId, title}]
            const dangling = [];

            const listFiles = (await fs.readdir(SHARED_LISTS_DIR))
                .filter(f => f.toLowerCase().endsWith('.json'))
                .filter(f => paths.validateListId(path.basename(f, '.json')).ok);
            let itemCount = 0;
            for (const f of listFiles) {
                const doc = await fs.readJson(path.join(SHARED_LISTS_DIR, f)).catch(() => null);
                if (!doc) continue;
                const listId = doc.listId || path.parse(f).name;
                const walk = (arr) => (arr || []).forEach(it => {
                    if (!it || typeof it !== 'object') return;
                    itemCount++;
                    if (it.itemId) {
                        const key = String(it.itemId);
                        const occurrences = seen.get(key) || [];
                        occurrences.push({ listId, title: it.title || '' });
                        seen.set(key, occurrences);
                    }
                    for (const e of (it.relatesTo || [])) {
                        if (!e || typeof e !== 'object') continue;
                        const targetList = String(e.listId || '');
                        const targetItem = String(e.itemId || '');
                        if (!targetList || !targetItem) continue;
                        const set = index.get(targetList);
                        if (!set) {
                            dangling.push({ listId, itemId: it.itemId || null,
                                title: it.title || '', relation: e.relation || '',
                                target: { listId: targetList, itemId: targetItem },
                                reason: 'target-list-missing' });
                        } else if (!set.has(targetItem)) {
                            dangling.push({ listId, itemId: it.itemId || null,
                                title: it.title || '', relation: e.relation || '',
                                target: { listId: targetList, itemId: targetItem },
                                reason: 'target-item-missing' });
                        }
                    }
                    walk(it.subTasks);
                });
                walk(doc.items);
            }

            const duplicates = [];
            for (const [itemId, occurrences] of seen.entries()) {
                if (occurrences.length < 2) continue;
                const lists = new Set(occurrences.map(o => o.listId));
                duplicates.push({ itemId, count: occurrences.length,
                    crossList: lists.size > 1, occurrences });
            }
            duplicates.sort((a, b) => b.count - a.count || a.itemId.localeCompare(b.itemId));

            res.json({
                ok: dangling.length === 0 && duplicates.length === 0,
                checkedAt: new Date().toISOString(),
                lists: listFiles.length,
                items: itemCount,
                counts: { dangling: dangling.length, duplicates: duplicates.length },
                danglingEdges: dangling,
                duplicateItemIds: duplicates,
                note: 'read-only report: archived items count as existing, nothing is '
                    + 'rejected on write (see the endpoint comment in server.js)',
            });
        } catch (err) {
            res.status(500).json({ error: 'Failed to build the integrity report' });
        }
    });
};

module.exports = { createListRoutes };
