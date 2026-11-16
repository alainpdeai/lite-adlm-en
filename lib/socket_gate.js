'use strict';

// P1-5: one place that decides who may open a Socket.IO connection.
//   * engine middleware rejects cross-origin handshakes with a fixed 403;
//   * io.use enforces the shared-mode session (same rule as guard.resolveActor);
//   * local mode and no-Origin clients stay allowed (P0 red line).

const cfg = require('./config');
const session = require('./session');
const util = require('./util');
const audit = require('./audit');
const { parseAllowList, classifyRequest } = require('./origin_policy');

const rejectAudit = (note) => {
    try {
        void audit.writeAudit({
            actor: null, action: 'reject', outcome: 'rejected', params: {}, note,
        });
    } catch (_err) { /* audit is best-effort on rejection paths */ }
};

const installSocketGate = (io, options) => {
    const opts = options || {};
    const allowOrigins = opts.allowOrigins || parseAllowList(process.env.LITETASK_SOCKET_ALLOW_ORIGINS);

    io.engine.use((req, res, next) => {
        let verdict;
        try {
            verdict = classifyRequest(req, allowOrigins);
        } catch (_err) {
            verdict = 'cross-origin';       // conservative on internal failure
        }
        if (verdict === 'cross-origin') {
            rejectAudit('ORIGIN_FORBIDDEN');
            try {
                res.writeHead(403, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ code: 'ORIGIN_FORBIDDEN', message: 'Origin not allowed' }));
            } catch (_err) { /* socket already gone */ }
            return;
        }
        return next();
    });

    io.use(async (socket, next) => {
        try {
            if (cfg.PASSWORDLESS_LOCAL) {
                socket.data.actor = { mode: 'local', userId: null, source: 'anonymous' };
                return next();
            }
            const req = socket.request || {};
            const cookies = session.parseCookies((req.headers || {}).cookie);
            const v = session.verifySession(cookies[session.SESSION_COOKIE]);
            if (!v.ok) {
                rejectAudit('AUTH_REQUIRED');
                return next(new Error('AUTH_REQUIRED'));
            }
            const user = await util.findUserById(v.userId);
            if (!user) {
                session.destroySession(v.sid);
                rejectAudit('AUTH_REQUIRED');
                return next(new Error('AUTH_REQUIRED'));
            }
            socket.data.actor = { mode: 'shared', userId: user.userId, source: 'session' };
            return next();
        } catch (_err) {
            rejectAudit('AUTH_REQUIRED');
            return next(new Error('AUTH_REQUIRED'));
        }
    });

    return allowOrigins;
};

module.exports = { installSocketGate };