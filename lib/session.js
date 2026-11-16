'use strict';

// Session domain (P0-2). Stateful sid + HMAC-SHA256 signed Cookie:
//   lt_session=<sid>.<exp>.<sig>
// Sessions only exist in memory Map and expire upon process exit. Cookie does
// not carry role; role is re-verified from users.json every time. verifySession
// never throws exceptions, uniformly returns 401 externally without distinction.

const crypto = require('crypto');
const cfg = require('./config');

const SESSION_COOKIE = 'lt_session';
const SESSION_TTL_MS = cfg.SESSION_TTL_MS;

const rawSecret = process.env.LITETASK_SESSION_SECRET;
const SECRET = (typeof rawSecret === 'string' && rawSecret.length >= 16)
    ? rawSecret
    : crypto.randomBytes(32);

const sessions = new Map();      // sid -> { userId, exp }

const b64url = (buf) => buf.toString('base64')
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');

const sign = (sid, exp) => b64url(
    crypto.createHmac('sha256', SECRET).update(`${sid}.${exp}`).digest());

const safeEqual = (a, b) => {
    const ba = Buffer.from(String(a), 'utf8');
    const bb = Buffer.from(String(b), 'utf8');
    if (ba.length !== bb.length) return false;
    try { return crypto.timingSafeEqual(ba, bb); } catch (_e) { return false; }
};

const parseCookies = (header) => {
    const out = {};
    if (typeof header !== 'string' || !header) return out;
    for (const part of header.split(';')) {
        const i = part.indexOf('=');
        if (i < 0) continue;
        const k = part.slice(0, i).trim();
        const v = part.slice(i + 1).trim();
        if (k) out[k] = v;
    }
    return out;
};

const buildSetCookie = (value, opts) => {
    const o = opts || {};
    const maxAge = Number.isFinite(o.maxAgeSec) ? Math.max(0, Math.floor(o.maxAgeSec)) : Math.floor(SESSION_TTL_MS / 1000);
    let cookie = `${SESSION_COOKIE}=${value}; HttpOnly; SameSite=Lax; Path=/; Max-Age=${maxAge}`;
    if (o.secure) cookie += '; Secure';
    return cookie;
};

const buildClearCookie = () => `${SESSION_COOKIE}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0`;

const issueSession = (userId, opts) => {
    const o = opts || {};
    const now = Number.isFinite(o.now) ? o.now : Date.now();
    const ttlMs = (Number.isFinite(o.ttlMs) && o.ttlMs > 0) ? o.ttlMs : SESSION_TTL_MS;
    const sid = b64url(crypto.randomBytes(32));
    const exp = now + ttlMs;
    sessions.set(sid, { userId, exp });
    const value = `${sid}.${exp}.${sign(sid, exp)}`;
    return {
        sid, value, exp, expiresAt: exp,
        cookie: buildSetCookie(value, { maxAgeSec: Math.floor(ttlMs / 1000), secure: o.secure }),
    };
};

const verifySession = (cookieValue, opts) => {
    if (typeof cookieValue !== 'string' || !cookieValue) return { ok: false, reason: 'missing' };
    const parts = cookieValue.split('.');
    if (parts.length !== 3) return { ok: false, reason: 'malformed' };
    const [sid, expStr, sig] = parts;
    const exp = Number(expStr);
    if (!sid || !Number.isFinite(exp)) return { ok: false, reason: 'malformed' };
    if (!safeEqual(sig, sign(sid, exp))) return { ok: false, reason: 'bad-signature' };
    const rec = sessions.get(sid);
    if (!rec) return { ok: false, reason: 'revoked' };
    if (rec.exp !== exp) return { ok: false, reason: 'bad-signature' };
    const now = (opts && Number.isFinite(opts.now)) ? opts.now : Date.now();
    if (exp <= now) {
        sessions.delete(sid);
        return { ok: false, reason: 'expired' };
    }
    return { ok: true, sid, userId: rec.userId, exp };
};

const destroySession = (sid) => {
    if (sid) sessions.delete(sid);
};

const destroySessionsForUser = (userId) => {
    if (!userId) return 0;
    let n = 0;
    for (const [sid, rec] of sessions.entries()) {
        if (rec && rec.userId === userId) {
            sessions.delete(sid);
            n++;
        }
    }
    return n;
};

const activeSessionCount = () => sessions.size;

module.exports = {
    SESSION_COOKIE, SESSION_TTL_MS,
    parseCookies, issueSession, verifySession, destroySession,
    destroySessionsForUser, activeSessionCount,
    buildSetCookie, buildClearCookie,
};