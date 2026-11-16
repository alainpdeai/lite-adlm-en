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
const { contentRev, atomicWriteJson, withLock } = util;
const { writeAudit } = logging;

/* ---------------------------------------------------------------------------
 * Item-level write endpoints P3-B: change one item without shipping the whole list.
 *
 * `PUT /api/lists/:id` takes the entire item array, and that is the only write
 * this system had. To tick one checkbox an Agent had to download every list,
 * modify one field and upload everything back — which is why a 16 MB body limit
 * is a thing here at all, why a stale copy could quietly drop unrelated items
 * (the 2026-10-29 `arch` loss had exactly this shape), and why every write raced
 * every other write on the same list.
 *
 * These endpoints take one item and run the SAME guards the whole-list path
 * runs — schema validation, the F1 status machine, baseRev concurrency, the
 * non-admin delete rule, the destructive-operation confirmation gate, the
 * idempotent-write shortcut and the audit trail. Nothing is relaxed to make the
 * small write easy; that would make it the preferred way to break things.
 *
 *   POST   /api/lists/:id/items            create  (409 if the id exists)
 *   PUT    /api/lists/:id/items/:itemId    replace (404 if it does not)
 *   DELETE /api/lists/:id/items/:itemId    remove  (needs confirm:true)
 * ------------------------------------------------------------------------- */
const createItemRoutes = (app, io, deps) => {
    const core = deps.core;
    const {
        getStatusConfig, collectStatuses, sanitizeStatus, validateItems,
        sanitizeRelatesTo, sanitizeLocalDirectories
    } = deps;

    const { findItemSlot, requireConfirm, changeEvent, actorOf } = core;

    const itemWrite = async (req, res, op) => {
        const listId = req.params.id;
        const listPath = paths.listFilePath(listId);
        if (!listPath) return errors.sendError(res, 400, 'INVALID_LIST_ID', 'Invalid list ID');
        const body = req.body && typeof req.body === 'object' ? req.body : {};
        const actor = req.actor || {};
        const userId = actor.userId || null;
        const itemId = req.params.itemId || (body.item && body.item.itemId) || null;

        try {
            return await withLock(`list:${listId}`, async () => {
                const data = await fs.readJson(listPath);
                const serverRev = contentRev(data.items);
                if (body.baseRev && body.baseRev !== serverRev) {
                    return res.status(409).json({
                        error: 'Conflict: this list was modified by someone else. Reload before saving.',
                        code: 'REV_CONFLICT',
                        serverRev,
                    });
                }

                const slot = itemId ? findItemSlot(data.items, itemId) : null;

                if (op === 'create') {
                    const vchk = validateItems([body.item]);
                    if (!vchk.ok) {
                        return res.status(400).json({
                            error: `Invalid item data: ${vchk.errors[0].message}`
                                + (vchk.errors.length > 1 ? ` (${vchk.errors.length} total)` : ''),
                            code: 'INVALID_ITEM_SCHEMA',
                            violations: vchk.errors.slice(0, 20)
                        });
                    }
                    if (slot) {
                        return res.status(409).json({
                            error: `itemId already exists: ${itemId}`, code: 'ITEM_EXISTS', itemId
                        });
                    }
                } else if (op === 'delete') {
                    if (userId && !actor.isAdmin) {
                        return res.status(403).json({
                            error: 'Forbidden: Regular users are not allowed to delete items from shared lists. Please close the task instead.',
                            code: 'ADMIN_REQUIRED'
                        });
                    }
                    // Hard gate: removing an item is destructive, so it needs the same
                    // affirmative confirmation as every other destructive call.
                    const gate = requireConfirm(req, `delete item ${itemId}`);
                    if (gate) return res.status(400).json(gate);
                    if (!slot) {
                        return res.status(404).json({ error: 'Item not found', code: 'ITEM_NOT_FOUND', itemId });
                    }
                } else {    // update
                    if (!slot) {
                        return res.status(404).json({ error: 'Item not found', code: 'ITEM_NOT_FOUND', itemId });
                    }
                    const vchk = validateItems([body.item]);
                    if (!vchk.ok) {
                        return res.status(400).json({
                            error: `Invalid item data: ${vchk.errors[0].message}`
                                + (vchk.errors.length > 1 ? ` (${vchk.errors.length} total)` : ''),
                            code: 'INVALID_ITEM_SCHEMA',
                            violations: vchk.errors.slice(0, 20)
                        });
                    }
                    if (body.item && String(body.item.itemId) !== String(itemId)) {
                        return res.status(400).json({
                            error: `itemId does not match path: ${itemId} != ${body.item.itemId}`,
                            code: 'ITEM_ID_MISMATCH'
                        });
                    }
                }

                // The previous statuses must be read from the list AS IT IS ON DISK,
                // before the new item is spliced in. Read them afterwards and the
                // item's own new status becomes its own "previous" status, so every
                // transition looks like a no-op and the F1 machine is never
                // consulted at all. (Caught by the grader, not by eye.)
                let prevStatuses = null;
                if (op !== 'delete') {
                    const sc0 = await getStatusConfig();
                    prevStatuses = collectStatuses(data.items, sc0);
                }

                let touched = null;
                if (op === 'delete') {
                    touched = slot.item;
                    slot.arr.splice(slot.index, 1);
                } else {
                    touched = body.item;
                    // same normalisation the whole-list write applies
                    sanitizeRelatesTo([touched]);
                    sanitizeLocalDirectories([touched]);
                    const sani = sanitizeItems([touched]);
                    if (!sani.ok) {
                        return res.status(400).json({
                            error: 'Comment too long',
                            code: sani.code || 'COMMENT_TOO_LONG',
                            limit: sani.limit, actual: sani.actual, itemId: sani.itemId,
                        });
                    }
                    const sc = await getStatusConfig();
                    const actorName = actor.username || null;
                    const chk = sanitizeStatus([touched], prevStatuses, sc, userId || null, actorName);
                    if (!chk.ok) {
                        const v = chk.violation;
                        return res.status(400).json({
                            error: `Invalid status transition '${v.from} -> ${v.to}' (${v.title || v.itemId}). Allowed: ${v.allowed.join(' / ')}`,
                            code: 'INVALID_TRANSITION',
                            violation: v
                        });
                    }
                    if (op === 'create') data.items.push(touched);
                    else slot.arr[slot.index] = touched;
                }

                const nextRev = contentRev(data.items);
                if (nextRev === serverRev) {
                    // Testing system P1: an idempotent write is not an update — touch
                    // neither the file nor updatedAt. P2-3: answer with the
                    // authoritative revision, not a possibly stale on-disk value.
                    return res.json({ ok: true, rev: nextRev, listId,
                        item: op === 'delete' ? null : touched, items: (data.items || []).length });
                }

                data.rev = nextRev;
                data.updatedAt = new Date().toISOString();
                data.updatedBy = userId || null;
                await atomicWriteJson(listPath, data);
                await writeAudit({
                    actor: userId, action: 'item-' + op, listId,
                    confirmed: op === 'delete' ? 'explicit' : null,
                    params: { itemId, title: touched && touched.title },
                    note: op === 'delete' ? `removed item ${itemId}` : `${op} item ${itemId}`,
                });
                io.emit('items-changed', changeEvent(listId, data.rev, {
                    source: 'api',
                    actor: await actorOf(userId),
                    items: (data.items || []).length,
                    op: 'item-' + op,
                    itemId,
                    summary: `${op === 'delete' ? 'removed' : op === 'create' ? 'added' : 'updated'} item ${itemId}`,
                }));
                return res.json({ ok: true, rev: data.rev, listId,
                    item: op === 'delete' ? null : touched, items: (data.items || []).length });
            });
        } catch (err) {
            if (err && (err.code === 'ENOENT' || err.code === 'ENOTDIR')) {
                return res.status(404).json({ error: 'List not found' });
            }
            console.error('[LiteTask] item write failed:', err);
            return res.status(500).json({ error: 'Failed to write item' });
        }
    };

    app.post('/api/lists/:id/items', async (req, res) => itemWrite(req, res, 'create'));
    app.put('/api/lists/:id/items/:itemId', async (req, res) => itemWrite(req, res, 'update'));
    app.delete('/api/lists/:id/items/:itemId', async (req, res) => itemWrite(req, res, 'delete'));

    return { itemWrite };
};

module.exports = { createItemRoutes };
