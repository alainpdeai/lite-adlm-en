'use strict';

// Foundation module (route ①, Round 1).
// Leaf helpers shared across every domain: content revisioning, the per-key
// async mutex, atomic JSON writes, the conflict diff, stamping, and the admin /
// username lookups. These depend only on crypto/fs/path and the USERS_FILE
// constant from lib/config — never on server.js module state.

const crypto = require('crypto');
const fs = require('fs-extra');
const path = require('path');
const { USERS_FILE } = require('./config');

// Concurrent-write protection (B3)
//  1. rev          – optimistic concurrency token derived from item content
//  2. withLock     – per-key async mutex, serialises read-modify-write per file
//  3. atomicWrite  – write to temp file then rename, with retry (NTFS locks)
const contentRev = (items) =>
    crypto.createHash('sha256').update(JSON.stringify(items || [])).digest('hex').slice(0, 16);

const lockQueue = new Map();
const withLock = async (key, fn) => {
    const prev = lockQueue.get(key) || Promise.resolve();
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    lockQueue.set(key, prev.then(() => gate));
    // A rejected previous fn() is already released in its own finally; swallow
    // it so it cannot poison this waiter's chain (which would otherwise throw
    // here and leave later waiters stuck forever).
    try {
        await prev;
    } catch (_e) { /* previous holder failed; gate was released, proceed */ }
    try {
        return await fn();
    } finally {
        release();
    }
};

const atomicWriteJson = async (filePath, data) => {
    const tmp = `${filePath}.tmp-${process.pid}-${Date.now()}`;
    await fs.writeJson(tmp, data, { spaces: 2 });
    let lastErr = null;
    for (let attempt = 0; attempt < 6; attempt++) {
        try {
            await fs.move(tmp, filePath, { overwrite: true });
            return true;
        } catch (err) {
            lastErr = err;
            // NTFS may hold a short-lived lock (AV/indexer) — back off and retry
            await new Promise(r => setTimeout(r, 150 * (attempt + 1)));
        }
    }
    // Last resort: in-place write (keeps data flowing, may lose atomicity)
    await fs.writeJson(filePath, data, { spaces: 2 });
    await fs.remove(tmp).catch(() => {});
    if (lastErr) console.warn(`[LiteTask] Atomic write fell back for ${path.basename(filePath)}: ${lastErr.code || lastErr.message}`);
    return true;
};

/* ---------------------------------------------------------------------------
 * B3 follow-up — conflict diff
 * When a save is rejected with 409 REV_CONFLICT the server returns a structured,
 * field-level diff between "what the client tried to save" (mine) and "what is
 * now on disk" (server). The UI uses it to render a side-by-side comparison and
 * to let the user pick, per field, which side wins; the CLI prints a summary.
 * ------------------------------------------------------------------------- */
const DIFF_FIELD_LABELS = {
    title: 'Title',
    status: 'Status',
    isDone: 'Done',
    priority: 'Priority',
    dueDate: 'Due Date',
    comment: 'Comment',
    blockedReason: 'Blocked Reason',
    localDirectory: 'Primary Path',
    localDirectories: 'Linked Paths',
    relatesTo: 'Relations',
    createdByAgent: 'Creator (Agent)',
    createdBy: 'Creator',
    assignedTo: 'Assigned To'
};

// Volatile / derived keys: never worth showing as a user-facing conflict.
const DIFF_IGNORE_KEYS = new Set([
    'rev', 'updatedAt', 'updatedBy', 'statusHistory',
    'archivedAt', 'archivedFrom', 'createdAt', 'createdById',
    'closedAt', 'closedBy', 'closedById', 'itemId', 'subTasks'
]);

// Order-insensitive value normalisation so object key order never fakes a diff.
const normVal = (v) => {
    if (v === undefined) return null;
    if (Array.isArray(v)) return v.map(normVal);
    if (v && typeof v === 'object') {
        return Object.keys(v).sort().reduce((o, k) => { o[k] = normVal(v[k]); return o; }, {});
    }
    return v;
};
const stableEqual = (a, b) => JSON.stringify(normVal(a)) === JSON.stringify(normVal(b));

// Flattens a (possibly nested, via subTasks) item array into Map<itemId, {item, parentId}>
const flattenItems = (arr, out = new Map(), parentId = null) => {
    for (const it of (Array.isArray(arr) ? arr : [])) {
        if (!it || typeof it !== 'object' || !it.itemId) continue;
        const id = String(it.itemId);
        if (out.has(id)) continue;
        out.set(id, { item: it, parentId });
        if (Array.isArray(it.subTasks) && it.subTasks.length) flattenItems(it.subTasks, out, id);
    }
    return out;
};

const diffItems = (mineArr, serverArr) => {
    const mine = flattenItems(mineArr);
    const server = flattenItems(serverArr);
    const added = [];    // only in my version   (I created them)
    const removed = [];  // only on the server   (they created them, or I deleted them)
    const changed = [];  // in both, but at least one comparable field differs

    for (const [id, m] of mine) {
        if (!server.has(id)) added.push({ itemId: id, title: m.item.title || '', parentId: m.parentId });
    }
    for (const [id, s] of server) {
        if (!mine.has(id)) removed.push({ itemId: id, title: s.item.title || '', parentId: s.parentId });
    }
    for (const [id, m] of mine) {
        const s = server.get(id);
        if (!s) continue;
        const fields = [];
        const keys = new Set([...Object.keys(m.item), ...Object.keys(s.item)]);
        for (const k of keys) {
            if (DIFF_IGNORE_KEYS.has(k)) continue;
            if (stableEqual(m.item[k], s.item[k])) continue;
            fields.push({
                field: k,
                label: DIFF_FIELD_LABELS[k] || k,
                mine: m.item[k] === undefined ? null : m.item[k],
                server: s.item[k] === undefined ? null : s.item[k]
            });
        }
        if (fields.length) {
            changed.push({ itemId: id, title: m.item.title || s.item.title || '', fields });
        }
    }
    return {
        added, removed, changed,
        counts: {
            added: added.length,
            removed: removed.length,
            changed: changed.length,
            fields: changed.reduce((n, c) => n + c.fields.length, 0)
        }
    };
};

const stampNow = () => {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

// P0-2: admin rights come from users.json, never from the literal string.
// The legacy equivalence rules are kept, but only for a record that exists.
const isUserAdminOf = (user) => Boolean(user
    && (user.isAdmin || user.username === 'admin' || user.userId === 'user_admin'));

const adminFlags = (users) => {
    const set = new Set();
    for (const u of (Array.isArray(users) ? users : [])) {
        if (u && u.userId && isUserAdminOf(u)) set.add(String(u.userId));
    }
    return set;
};

const findUserById = async (userId) => {
    if (!userId) return null;
    try {
        const users = await fs.readJson(USERS_FILE);
        return users.find(x => x.userId === userId) || null;
    } catch {
        return null;
    }
};

const isUserAdmin = async (userId) => isUserAdminOf(await findUserById(userId));

// Resolve a userId to a username so server-side closes still record an owner
const usernameOf = async (userId) => {
    if (!userId) return null;
    try {
        const users = await fs.readJson(USERS_FILE);
        const u = users.find(x => x.userId === userId);
        return u ? (u.username || null) : null;
    } catch {
        return null;
    }
};

module.exports = {
    contentRev, withLock, atomicWriteJson,
    DIFF_FIELD_LABELS, DIFF_IGNORE_KEYS, normVal, stableEqual, flattenItems, diffItems,
    stampNow, isUserAdmin, isUserAdminOf, adminFlags, findUserById, usernameOf, lockQueue
};
