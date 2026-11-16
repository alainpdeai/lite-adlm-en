'use strict';

// Identity context domain (P0-2). Single place deciding mode, actor, and isAdmin:
//   - loopbackGuard: by default accessible only from loopback addresses;
//   - createAuthGate: single conduit for /api/**, writes immutable req.actor;
//   - shared mode recognizes sessions only; local mode retains backward-compatible
//     "no session + declared identity", where declared id must exist in user store;
//     unauthenticated requests yield anonymous actor (userId=null).

const cfg = require('./config');
const util = require('./util');
const errors = require('./errors');
const session = require('./session');
const { writeAudit } = require('./audit');

const { PASSWORDLESS_LOCAL, REACHABILITY, isLoopbackAddress } = cfg;

const PUBLIC_API_PATHS = Object.freeze({
    '/api/login': true,
    '/api/logout': true,
    '/api/config': true,
    '/api/health': true,
});

const anonymousActor = (mode) => Object.freeze({
    mode,
    userId: null,
    username: null,
    isAdmin: false,
    authenticated: false,
    declared: false,
    anonymous: true,
    source: 'none',
});

const declaredActor = (mode, user, source) => Object.freeze({
    mode,
    userId: user.userId,
    username: user.username,
    isAdmin: util.isUserAdminOf(user),
    authenticated: source === 'session',
    declared: source === 'declared',
    anonymous: false,
    source,
});

const loopbackGuard = (req, res, next) => {
    if (REACHABILITY === 'loopback') {
        const addr = req.socket && req.socket.remoteAddress;
        if (!isLoopbackAddress(addr)) {
            return errors.sendError(res, 403, 'NON_LOOPBACK_SOURCE', 'Loopback access only');
        }
    }
    return next();
};

const declaredIdOf = (req) => {
    const q = req.query || {};
    const b = (req.body && typeof req.body === 'object') ? req.body : {};
    const raw = q.userId || b.userId || b.adminUserId || q.adminUserId;
    return (raw === undefined || raw === null || raw === '') ? null : String(raw);
};

const resolveActor = async (req, allowAnonymous) => {
    if (!PASSWORDLESS_LOCAL) {
        const cookies = session.parseCookies(req.headers && req.headers.cookie);
        const v = session.verifySession(cookies[session.SESSION_COOKIE]);
        if (!v.ok) {
            if (allowAnonymous) return { ok: true, actor: anonymousActor('shared') };
            return { ok: false, status: 401, code: 'AUTH_REQUIRED', message: 'Authentication required' };
        }
        const user = await util.findUserById(v.userId);
        if (!user) {
            session.destroySession(v.sid);
            if (allowAnonymous) return { ok: true, actor: anonymousActor('shared') };
            return { ok: false, status: 401, code: 'AUTH_REQUIRED', message: 'Authentication required' };
        }
        return { ok: true, actor: declaredActor('shared', user, 'session') };
    }

    const raw = declaredIdOf(req);
    if (!raw) return { ok: true, actor: anonymousActor('local') };
    const user = await util.findUserById(raw);
    if (!user) return { ok: false, status: 403, code: 'UNKNOWN_ACTOR', message: 'Untrusted identity' };
    return { ok: true, actor: declaredActor('local', user, 'declared') };
};

const reject = async (res, status, code, note) => {
    // Audit a rejection without ever copying credentials into the record.
    try {
        await writeAudit({ actor: null, action: 'reject', outcome: 'rejected', note: note || code });
    } catch (_e) { /* audit is best-effort on rejection paths */ }
    return errors.sendError(res, status, code, undefined);
};

const createAuthGate = () => async (req, res, next) => {
    try {
        const pathOnly = String(req.originalUrl || req.url || '').split('?')[0];
        if (req.method === 'OPTIONS') {
            req.actor = anonymousActor(PASSWORDLESS_LOCAL ? 'local' : 'shared');
            return next();
        }
        const isPublic = !!PUBLIC_API_PATHS[pathOnly];
        const r = await resolveActor(req, isPublic);
        if (!r.ok) return reject(res, r.status, r.code, r.code.toLowerCase());
        req.actor = r.actor;
        return next();
    } catch (_err) {
        return errors.sendError(res, 500, 'INTERNAL', 'Internal error');
    }
};

const requireAdmin = (actor) => Boolean(actor && actor.isAdmin === true);

module.exports = {
    isLoopbackAddress,
    loopbackGuard,
    createAuthGate,
    resolveActor,
    requireAdmin,
    PUBLIC_API_PATHS,
    anonymousActor,
};