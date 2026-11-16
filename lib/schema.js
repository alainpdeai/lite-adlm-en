'use strict';

// Item-schema + multi-path link sanitizers (route ①, Round 6).
// Extracted from server.js. Pure helpers shared by the lists domain; injected
// at register time so the domain module stays free of server.js scope.

// Ensure relatesTo is a clean array of { listId, itemId, relation } on every item/subtask
const sanitizeRelatesTo = (items) => {
    const walk = (arr) => {
        if (!Array.isArray(arr)) return;
        for (const it of arr) {
            if (!it || typeof it !== 'object') continue;
            if (!Array.isArray(it.relatesTo)) {
                it.relatesTo = [];
            } else {
                it.relatesTo = it.relatesTo
                    .filter(r => r && typeof r === 'object' && r.listId && r.itemId)
                    .map(r => ({
                        listId: String(r.listId),
                        itemId: String(r.itemId),
                        relation: (typeof r.relation === 'string' && r.relation) ? r.relation : 'related'
                    }));
            }
            if (it.subTasks) walk(it.subTasks);
        }
    };
    walk(items);
    return items;
};

// F2: multi-path source links. `localDirectory` stays the primary path (legacy,
// always first); `localDirectories` holds any number of extra paths/URLs.
const sanitizeLocalDirectories = (items) => {
    const walk = (arr) => {
        if (!Array.isArray(arr)) return;
        for (const it of arr) {
            if (!it || typeof it !== 'object') continue;
            const primary = (typeof it.localDirectory === 'string' && it.localDirectory.trim())
                ? it.localDirectory.trim() : '';
            const extra = (Array.isArray(it.localDirectories) ? it.localDirectories : [])
                .filter(p => typeof p === 'string' && p.trim())
                .map(p => p.trim())
                .slice(0, 20);
            const seen = new Set();
            const merged = [primary, ...extra].filter(p => {
                const k = p.replace(/[\\/]+$/, '').toLowerCase();
                if (!p || seen.has(k)) return false;
                seen.add(k);
                return true;
            });
            it.localDirectory = merged[0] || '';
            it.localDirectories = merged.slice(1);
            if (it.subTasks) walk(it.subTasks);
        }
    };
    walk(items);
    return items;
};

// ---------------------------------------------------------------------------
// Item schema validation (contract and schema P1)
//
// The server used to accept any JSON shape and only discover bad data when a
// downstream reader crashed. We now validate field names + types before a write
// and reject malformed items with a readable 400 INVALID_ITEM_SCHEMA.
//
// Design: validate KNOWN fields (name + type + enum), require the two essential
// fields (itemId, title), and TOLERATE unknown fields. Toleration is deliberate:
// historical data carries dual-write legacy fields (isDone/status) and possibly
// other forward-compat fields; the contract says existing data must never be
// judged illegal. New illegality = missing required, wrong type, or enum
// out-of-range on a known field.
// ---------------------------------------------------------------------------
const ITEM_FIELD_TYPES = {
    itemId: 'string',
    title: 'string',
    isDone: 'boolean',
    status: 'string',
    statusHistory: 'array',
    blockedReason: 'string',
    dueDate: 'string',
    priority: 'string',
    assignedTo: 'string',
    createdBy: 'string',
    createdByAgent: 'string',
    createdById: 'string',
    createdAt: 'string',
    // closed* accept null (set on close, cleared on reopen) or string
    closedBy: ['string', 'null'],
    closedById: ['string', 'null'],
    closedAt: ['string', 'null'],
    localDirectory: 'string',
    localDirectories: 'array',
    comment: 'string',
    subTasks: 'array',
    relatesTo: 'array',
};
const ITEM_ENUM_FIELDS = {
    status: ['open', 'in-progress', 'blocked', 'verified', 'done'],
    priority: ['High', 'Medium', 'Low'],
};
const ITEM_REQUIRED = ['itemId', 'title'];

const jsonTypeOf = (v) => {
    if (v === null) return 'null';
    if (Array.isArray(v)) return 'array';
    return typeof v;
};

const validateOneItem = (it, errors) => {
    for (const f of ITEM_REQUIRED) {
        const v = it[f];
        if (v === undefined || v === null || v === '') {
            errors.push({ itemId: it.itemId || null, field: f,
                message: `Required field missing or empty: ${f}` });
        }
    }
    for (const [f, expected] of Object.entries(ITEM_FIELD_TYPES)) {
        if (!(f in it)) continue;
        const v = it[f];
        const allowed = Array.isArray(expected) ? expected : [expected];
        const actual = jsonTypeOf(v);
        if (!allowed.includes(actual)) {
            errors.push({ itemId: it.itemId || null, field: f,
                message: `Field type error: ${f} expected ${allowed.join('/')}, got ${actual}` });
        }
        if (ITEM_ENUM_FIELDS[f] && jsonTypeOf(v) === 'string'
            && !ITEM_ENUM_FIELDS[f].includes(v)) {
            errors.push({ itemId: it.itemId || null, field: f,
                message: `Enum out of range: ${f}=${v}, allowed ${ITEM_ENUM_FIELDS[f].join('/')}` });
        }
    }
    // unknown fields are intentionally tolerated (see header note)
};

const validateItems = (items) => {
    const errors = [];
    const walk = (arr, where) => {
        if (!Array.isArray(arr)) {
            errors.push({ itemId: null, field: where || 'items',
                message: 'items must be an array' });
            return;
        }
        for (const it of arr) {
            if (!it || typeof it !== 'object') {
                errors.push({ itemId: null, field: where || 'items',
                    message: 'Each item must be an object' });
                continue;
            }
            validateOneItem(it, errors);
            if (Array.isArray(it.subTasks)) walk(it.subTasks, (it.itemId || '?') + '/subTasks');
        }
    };
    walk(items);
    return { ok: errors.length === 0, errors };
};

const { sanitizeCommentsInPlace } = require('./comment_sanitizer');

// P2-5: comment sanitisation is normalisation, not validation. It runs after the
// path/relation sanitizers and before validateItems + contentRev.
const sanitizeItems = (items) => {
    const r = sanitizeCommentsInPlace(items);
    return r && r.ok === false ? r : { ok: true, violations: (r && r.violations) || [] };
};

module.exports = { sanitizeRelatesTo, sanitizeLocalDirectories, validateItems, sanitizeItems };
