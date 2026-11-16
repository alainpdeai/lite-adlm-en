'use strict';

// Path & Identifier domain (P0-1). Resolves "request input -> file path" through single conduit:
//   - Whitelist validation for listId / stamp;
//   - Secondary validation inside path constructors; returns null on invalid input;
//   - Membership check calls realpath on nearest existing ancestor; symlink/junction escape returns false.
// All validation functions are pure functions with zero I/O; only realpathNearest / belongsTo touch disk.

const path = require('path');
const fs = require('fs-extra');

const cfg = require('./config');
const errors = require('./errors');

const { SHARED_LISTS_DIR, ARCHIVE_DIR, ARCHIVE_SNAPSHOT_DIR } = cfg;

const LIST_ID_MAX_LEN = 32;
const STAMP_MAX_LEN = 40;
const LIST_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$/;
const STAMP_RE = /^[0-9A-Za-z][0-9A-Za-z._:-]{0,39}$/;

const validateListId = (raw) => {
    if (typeof raw !== 'string') return { ok: false, reason: 'not-string' };
    if (raw.length < 1 || raw.length > LIST_ID_MAX_LEN) return { ok: false, reason: 'length' };
    if (!/^[\x21-\x7E]+$/.test(raw)) return { ok: false, reason: 'non-ascii-or-control' };
    if (/[.\/%\\\s]/.test(raw)) return { ok: false, reason: 'forbidden-char' };
    if (!LIST_ID_RE.test(raw)) return { ok: false, reason: 'charset' };
    return { ok: true };
};

const validateStamp = (raw) => {
    if (typeof raw !== 'string') return { ok: false, reason: 'not-string' };
    if (raw.length < 1 || raw.length > STAMP_MAX_LEN) return { ok: false, reason: 'length' };
    if (raw.includes('..')) return { ok: false, reason: 'traversal' };
    if (/[\/\\%\s\x00]/.test(raw)) return { ok: false, reason: 'separator' };
    if (!STAMP_RE.test(raw)) return { ok: false, reason: 'charset' };
    return { ok: true };
};

const isInside = (rootAbs, candidateAbs) => {
    try {
        const rel = path.relative(rootAbs, candidateAbs);
        return rel !== '' && rel !== '..'
            && !rel.startsWith('..' + path.sep)
            && !path.isAbsolute(rel);
    } catch (_err) {
        return false;
    }
};

// Resolve the nearest existing ancestor of `p` and re-attach the missing suffix.
// A symlink/junction inside the tree is therefore resolved to its real target.
const realpathNearest = async (p) => {
    let cur = path.resolve(p);
    const missing = [];
    for (let i = 0; i < 64; i++) {
        try {
            const real = await fs.realpath(cur);
            return missing.length ? path.join(real, ...missing.slice().reverse()) : real;
        } catch (err) {
            if (err && err.code !== 'ENOENT' && err.code !== 'ENOTDIR') return null;
            const parent = path.dirname(cur);
            if (parent === cur) return path.resolve(p);
            missing.push(path.basename(cur));
            cur = parent;
        }
    }
    return path.resolve(p);
};

const belongsTo = async (rootAbs, fileAbs) => {
    try {
        const rootReal = await realpathNearest(rootAbs);
        const fileReal = await realpathNearest(fileAbs);
        if (!rootReal || !fileReal) return false;
        if (path.resolve(fileReal) === path.resolve(rootReal)) return true;
        return isInside(rootReal, fileReal);
    } catch (_err) {
        return false;
    }
};

const listFilePath = (listId) => {
    if (!validateListId(listId).ok) return null;
    return path.join(SHARED_LISTS_DIR, `${listId}.json`);
};

const archiveFilePath = (listId) => {
    if (!validateListId(listId).ok) return null;
    return path.join(ARCHIVE_DIR, `${listId}.json`);
};

const snapshotFilePrefix = (listId) => {
    if (!validateListId(listId).ok) return null;
    return `${listId}-`;
};

const snapshotFilePath = (listId, stamp) => {
    if (!validateListId(listId).ok || !validateStamp(stamp).ok) return null;
    const safeStamp = String(stamp).replace(/[:.]/g, '-');
    return path.join(ARCHIVE_SNAPSHOT_DIR, `${listId}-${safeStamp}.snapshot.json`);
};

// Express prefix guard for /api/lists/:id and /api/archive/:id.
const listIdParamGuard = (req, res, next) => {
    const raw = req.params && req.params.id;
    const v = validateListId(raw);
    if (!v.ok) return errors.sendError(res, 400, 'INVALID_LIST_ID', 'Invalid list identifier');
    req.listId = raw;
    return next();
};

// Reads body.stamp; a missing stamp is left to the handler (it has its own 400).
const stampFieldGuard = (req, res, next) => {
    const raw = req.body && req.body.stamp;
    if (raw === undefined || raw === null || raw === '') return next();
    const v = validateStamp(raw);
    if (!v.ok) return errors.sendError(res, 400, 'INVALID_STAMP', 'Invalid snapshot timestamp');
    req.stamp = raw;
    return next();
};

module.exports = {
    LIST_ID_MAX_LEN, STAMP_MAX_LEN, LIST_ID_RE, STAMP_RE,
    validateListId, validateStamp, isInside, realpathNearest, belongsTo,
    listFilePath, archiveFilePath, snapshotFilePath, snapshotFilePrefix,
    listIdParamGuard, stampFieldGuard,
};