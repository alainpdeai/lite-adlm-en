'use strict';

// Security Boundary P2-A: an operation audit — "who changed what, when". Split from
// logging.js (route ①, Round 7). AUDIT_FILE is derived from LOG_DIR, so we
// import LOG_DIR from logrotate.js. Depends on fs/path + lib/config + logrotate.

const fs = require('fs-extra');
const path = require('path');
const cfg = require('./config');
const { LOG_DIR } = require('./logrotate');

const AUDIT_FILE = process.env.LITETASK_AUDIT_FILE
    ? path.resolve(process.env.LITETASK_AUDIT_FILE)
    : path.join(LOG_DIR, 'audit.log');
const AUDIT_MAX_BYTES = Math.max(1, Number(process.env.LITETASK_AUDIT_MAX_BYTES || 1024 * 1024));
const AUDIT_KEEP = Math.max(1, Number(process.env.LITETASK_AUDIT_KEEP || 3));

// Lower-cased key names whose values must never reach the audit.
const AUDIT_SECRET_KEYS = new Set([
    'password', 'newpassword', 'oldpassword', 'currentpassword',
    'confirmpassword', 'pwd', 'pass', 'token', 'accesstoken',
    'refreshtoken', 'idtoken', 'secret', 'clientsecret', 'cookie',
    'authorization', 'apikey', 'credential', 'credentials', 'sessionid',
]);

const summarizeForAudit = (value, depth) => {
    depth = depth || 0;
    if (depth > 3) return '[deep]';
    if (Array.isArray(value)) return { len: value.length };
    if (value && typeof value === 'object') {
        const out = {};
        for (const k of Object.keys(value)) {
            out[k] = AUDIT_SECRET_KEYS.has(k.toLowerCase())
                ? '[redacted]'
                : summarizeForAudit(value[k], depth + 1);
        }
        return out;
    }
    if (typeof value === 'string') {
        return value.length > 200 ? value.slice(0, 200) + '...' : value;
    }
    return value;                    // number / boolean / null / undefined
};

let auditChain = Promise.resolve();
const writeAudit = (entry) => {
    const rec = {
        ts: new Date().toISOString(),
        actor: entry.actor || null,
        action: entry.action,
        listId: entry.listId === undefined ? null : entry.listId,
        outcome: entry.outcome === undefined ? 'ok' : entry.outcome,
        confirmed: entry.confirmed === undefined ? null : entry.confirmed,
        params: summarizeForAudit(entry.params || {}),
    };
    if (entry.note) rec.note = String(entry.note).slice(0, 300);
    auditChain = auditChain.then(async () => {
        try {
            await fs.ensureDir(path.dirname(AUDIT_FILE));
            const st = await fs.stat(AUDIT_FILE).catch(() => null);
            if (st && st.size > AUDIT_MAX_BYTES) {
                for (let i = AUDIT_KEEP; i >= 1; i--) {
                    const from = i === 1 ? AUDIT_FILE : `${AUDIT_FILE}.${i - 1}`;
                    const to = `${AUDIT_FILE}.${i}`;
                    if (await fs.pathExists(from)) await fs.move(from, to, { overwrite: true });
                }
            }
            await fs.appendFile(AUDIT_FILE, JSON.stringify(rec) + '\n');
        } catch (err) {
            console.warn('[LiteTask] audit write failed:', err.message);
        }
    });
    return auditChain;
};

module.exports = { AUDIT_FILE, AUDIT_MAX_BYTES, AUDIT_KEEP, summarizeForAudit, writeAudit };
