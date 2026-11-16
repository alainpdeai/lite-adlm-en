'use strict';

// Status-flow domain helpers (route ①, Round 6).
// Extracted from server.js so the orchestrator stays thin. These are pure
// helpers shared by the lists and links domains; they are injected at register
// time, not imported by the domain modules, so the dependency direction stays
// server -> lib.

const { getCategories } = require('./categories');
const { stampNow } = require('./util');

const DEFAULT_STATUSES = [
    { value: 'open', label: 'Open', color: '#64748b', closed: false },
    { value: 'in-progress', label: 'In Progress', color: '#2563eb', closed: false },
    { value: 'blocked', label: 'Blocked', color: '#e11d48', closed: false },
    { value: 'verified', label: 'Verified', color: '#7c3aed', closed: false },
    { value: 'done', label: 'Done', color: '#059669', closed: true }
];
const DEFAULT_STATUS_FLOW = {
    'open': ['in-progress', 'blocked', 'done'],
    'in-progress': ['open', 'blocked', 'verified', 'done'],
    'blocked': ['open', 'in-progress', 'done'],
    'verified': ['in-progress', 'blocked', 'done'],
    'done': ['open', 'in-progress', 'blocked', 'verified']
};
const STATUS_HISTORY_LIMIT = 20;

const getStatusConfig = async () => {
    const cfg = await getCategories();
    const statuses = Array.isArray(cfg.statuses) && cfg.statuses.length ? cfg.statuses : DEFAULT_STATUSES;
    const flow = (cfg.statusFlow && typeof cfg.statusFlow === 'object' && !Array.isArray(cfg.statusFlow))
        ? cfg.statusFlow : DEFAULT_STATUS_FLOW;
    const values = statuses.map(s => String(s.value));
    const closedValues = statuses.filter(s => s && s.closed).map(s => String(s.value));
    const closedSet = new Set(closedValues.length ? closedValues : ['done']);
    return { statuses, flow, values, closedSet };
};

// Derive the status a record currently represents (legacy items only carry isDone)
const deriveStatus = (it, cfg) => {
    const v = typeof it?.status === 'string' ? it.status : null;
    if (v && cfg.values.includes(v)) return v;
    return it?.isDone ? 'done' : 'open';
};

const collectStatuses = (items, cfg, out = new Map()) => {
    if (!Array.isArray(items)) return out;
    for (const it of items) {
        if (!it || typeof it !== 'object') continue;
        if (it.itemId) out.set(String(it.itemId), deriveStatus(it, cfg));
        if (Array.isArray(it.subTasks)) collectStatuses(it.subTasks, cfg, out);
    }
    return out;
};

// Normalise every item/subtask: clamp unknown values, keep isDone in sync with
// the closed state, reject illegal transitions, and record the change.
const sanitizeStatus = (items, prevStatuses, cfg, actorId, actorName) => {
    const walk = (arr) => {
        if (!Array.isArray(arr)) return null;
        for (const it of arr) {
            if (!it || typeof it !== 'object') continue;
            const prev = (it.itemId && prevStatuses.has(String(it.itemId)))
                ? prevStatuses.get(String(it.itemId))
                : deriveStatus(it, cfg);
            let next = typeof it.status === 'string' ? it.status : prev;
            if (!cfg.values.includes(next)) next = it.isDone ? 'done' : 'open';

            if (next !== prev) {
                const allowed = Array.isArray(cfg.flow[prev]) ? cfg.flow[prev] : null;
                if (allowed && !allowed.includes(next)) {
                    return { itemId: it.itemId || null, title: it.title || '', from: prev, to: next, allowed };
                }
            }

            it.status = next;
            const isClosed = cfg.closedSet.has(next);
            it.isDone = isClosed;
            if (isClosed) {
                if (!it.closedAt) it.closedAt = stampNow();
                if (!it.closedBy && actorName) it.closedBy = actorName;
                if (!it.closedById && actorId) it.closedById = actorId;
            } else {
                it.closedBy = null;
                it.closedById = null;
                it.closedAt = null;
            }

            if (next !== prev) {
                const hist = Array.isArray(it.statusHistory)
                    ? it.statusHistory.filter(h => h && typeof h === 'object') : [];
                hist.push({ from: prev, to: next, at: stampNow(), by: actorId || null });
                it.statusHistory = hist.slice(-STATUS_HISTORY_LIMIT);
            } else if (!Array.isArray(it.statusHistory)) {
                it.statusHistory = [];
            }
            if (typeof it.blockedReason !== 'string') it.blockedReason = it.blockedReason ? String(it.blockedReason) : '';

            const bad = walk(it.subTasks);
            if (bad) return bad;
        }
        return null;
    };
    const bad = walk(items);
    return bad ? { ok: false, violation: bad } : { ok: true };
};

module.exports = { getStatusConfig, deriveStatus, collectStatuses, sanitizeStatus };
