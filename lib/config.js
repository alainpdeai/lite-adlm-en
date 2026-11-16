'use strict';

// Foundation module (route ①, Round 1).
// Pure, dependency-free configuration: env-derived paths/constants and the
// password-store crypto helpers. No route registration, no module-level I/O
// beyond reading process.env at load time.
//
// NOTE: this file lives in lib/, so the default data/backup paths reach one
// directory up (the project root) — same absolute location the old inline
// constants resolved to when server.js lived in the project root.

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

// The two directories can be relocated so a throwaway instance can be started
// against a copy of the data (hermetic startup tests) without ever touching the
// real data/ or backup/ tree. Defaults are unchanged.
const DATA_DIR = process.env.LITETASK_DATA_DIR
    ? path.resolve(process.env.LITETASK_DATA_DIR)
    : path.join(__dirname, '..', 'data');
const USERS_FILE = path.join(DATA_DIR, 'users.json');

// Local development is passwordless (plan A for "passwordless login"). The data API has
// never been gated — /api/lists answers without credentials and callers report
// their own userId — so the password only ever guarded the login form, and the
// front end was already auto-submitting admin/admin. In local mode /api/login
// therefore accepts a username that names an existing account and ignores any
// password; unknown usernames are still rejected, so no account is invented.
// Set LITETASK_DEV_LOGIN=0 for any shared deployment to reinstate the real
// password check (the scrypt store from B2 is kept intact either way).
const PASSWORDLESS_LOCAL = process.env.LITETASK_DEV_LOGIN !== '0';
const SHARED_LISTS_DIR = path.join(DATA_DIR, 'shared_lists');
const CATEGORIES_FILE = path.join(DATA_DIR, 'categories.json');
const ARCHIVE_DIR = path.join(DATA_DIR, 'archive');
const BACKUP_DIR = process.env.LITETASK_BACKUP_DIR
    ? path.resolve(process.env.LITETASK_BACKUP_DIR)
    : path.join(__dirname, '..', 'backup');
// P1-4: a full pre-mutation snapshot is written before any archive action so
// the move is auditable and reversible. One directory per data tree; pruned to
// MAX_ARCHIVE_SNAPSHOTS per list (see writeArchiveSnapshot).
const ARCHIVE_SNAPSHOT_DIR = path.join(DATA_DIR, 'archive-snapshots');
const MAX_ARCHIVE_SNAPSHOTS = 20;
// A1: auto-archive once a list holds this many closed top-level items.
// The threshold and the protected list ids live in categories.json -> archive;
// the environment still wins, so a single launch can be tuned
// (LITETASK_AUTO_ARCHIVE_MIN_CLOSED=<n>) or switched off (LITETASK_AUTO_ARCHIVE=0)
// without editing the config.
const AUTO_ARCHIVE_ENABLED = process.env.LITETASK_AUTO_ARCHIVE !== '0';
const AUTO_ARCHIVE_ENV_MIN = process.env.LITETASK_AUTO_ARCHIVE_MIN_CLOSED;
const DEFAULT_AUTO_ARCHIVE_MIN_CLOSED = 25;
const DEFAULT_ARCHIVE_WARN_WITHIN = 5;

/* ---------------------------------------------------------------------------
 * Password security (B2)
 * Storage format: scrypt$<N>$<r>$<p>$<saltB64>$<hashB64>
 * Legacy records (plain base64 of the password) are upgraded on startup.
 * ------------------------------------------------------------------------- */
const SCRYPT_N = 16384;
const SCRYPT_R = 8;
const SCRYPT_P = 1;
const KEY_LEN = 64;
const HASH_SCHEME = 'scrypt';
const HASH_PREFIX = HASH_SCHEME + '$';

const isHashedPassword = (stored) => typeof stored === 'string' && stored.startsWith(HASH_PREFIX);

const hashPassword = (plain) => {
    const salt = crypto.randomBytes(16);
    const key = crypto.scryptSync(String(plain), salt, KEY_LEN, { N: SCRYPT_N, r: SCRYPT_R, p: SCRYPT_P });
    return [HASH_SCHEME, SCRYPT_N, SCRYPT_R, SCRYPT_P, salt.toString('base64'), key.toString('base64')].join('$');
};

const verifyPassword = (plain, stored) => {
    if (typeof stored !== 'string' || !stored) return false;
    // Legacy: base64 of the plaintext (kept only so in-flight records still work)
    if (!isHashedPassword(stored)) {
        try {
            const decoded = Buffer.from(stored, 'base64').toString('utf-8');
            return safeEqual(decoded, String(plain));
        } catch {
            return false;
        }
    }
    try {
        // Tolerate records written by an earlier build ("scrypt$$N$r$p$…") by
        // dropping empty segments; migration rewrites them in canonical form.
        const parts = stored.split('$').filter(s => s !== '');
        if (parts.length !== 6 || parts[0] !== HASH_SCHEME) return false;
        const [, n, r, p, saltB64, hashB64] = parts;
        const salt = Buffer.from(saltB64, 'base64');
        const expected = Buffer.from(hashB64, 'base64');
        const actual = crypto.scryptSync(String(plain), salt, expected.length, {
            N: Number(n), r: Number(r), p: Number(p)
        });
        return crypto.timingSafeEqual(actual, expected);
    } catch {
        return false;
    }
};

const safeEqual = (a, b) => {
    const ba = Buffer.from(String(a), 'utf-8');
    const bb = Buffer.from(String(b), 'utf-8');
    if (ba.length !== bb.length) return false;
    return crypto.timingSafeEqual(ba, bb);
};

/* ---------------------------------------------------------------------------
 * P0-2: bind address, reachability and session lifetime.
 * Default is loopback-only; a deliberate non-loopback bind flips REACHABILITY
 * so the guard and the UI can say so instead of silently opening the port.
 * ------------------------------------------------------------------------- */
const BIND_HOST = (() => {
    const raw = process.env.LITETASK_BIND_HOST;
    return (typeof raw === 'string' && raw.trim()) ? raw.trim() : '127.0.0.1';
})();

const isLoopbackAddress = (addr) => {
    if (typeof addr !== 'string') return false;
    let a = addr.trim();
    if (a.startsWith('::ffff:')) a = a.slice(7);
    if (a.startsWith('[') && a.endsWith(']')) a = a.slice(1, -1);
    if (a === '::1' || a === '0:0:0:0:0:0:0:1') return true;
    const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(a);
    return Boolean(m) && Number(m[1]) === 127;
};

const REACHABILITY = isLoopbackAddress(BIND_HOST) ? 'loopback' : 'non-loopback';

// Test hook LITETASK_SESSION_TTL_MS (short-lived sessions in the P0 grader);
// otherwise hours, clamped to [1h, 24h].
const SESSION_TTL_MS = (() => {
    const ms = Number(process.env.LITETASK_SESSION_TTL_MS);
    if (Number.isFinite(ms) && ms > 0) return ms;
    const h = Number(process.env.LITETASK_SESSION_TTL_HOURS);
    const hours = Number.isFinite(h) && h > 0 ? Math.min(24, Math.max(1, h)) : 8;
    return Math.round(hours * 3600000);
})();

const OPEN_RATE = (() => {
    const m = /^(\d+)\/(\d+)$/.exec(String(process.env.LITETASK_OPEN_RATE || '10/10').trim());
    const limit = m ? Math.max(1, Number(m[1])) : 10;
    const windowSec = m ? Math.max(1, Number(m[2])) : 10;
    return { limit, windowSec };
})();

/* ---------------------------------------------------------------------------
 * P1-2: the dead `securityModel` site field is never read for behaviour.
 * describeLegacySiteConfig only reports *existence* — any value type is inert,
 * and the callback is pure (no I/O, no env reads, no throw).
 * ------------------------------------------------------------------------- */
const LEGACY_SITE_KEY = 'securityModel';
const DEFAULT_SITE_CONFIG_PATH = path.join(__dirname, '..', 'config', 'site.json');

const describeLegacySiteConfig = (site) => {
    if (!site || typeof site !== 'object' || Array.isArray(site)) return [];
    return Object.prototype.hasOwnProperty.call(site, LEGACY_SITE_KEY) ? [LEGACY_SITE_KEY] : [];
};

// Test-only read redirect (T-1). It never participates in mode selection and
// never changes any write location; an unusable value falls back to the default.
const resolveSiteConfigPath = () => {
    const raw = process.env.LITETASK_SITE_CONFIG;
    if (typeof raw === 'string' && raw.trim() && path.isAbsolute(raw.trim())) {
        const candidate = path.resolve(raw.trim());
        try {
            if (fs.statSync(candidate).isFile()) {
                return { path: candidate, redirected: true };
            }
        } catch (_err) { /* fall through to the default */ }
    }
    return { path: DEFAULT_SITE_CONFIG_PATH, redirected: false };
};

// Capacity guard: the whole list is written on every save, so the JSON body cap
// must be large enough to hold it (and stay tunable).
const JSON_BODY_LIMIT = (() => {
    const mb = Number(process.env.LITETASK_JSON_LIMIT_MB || 16);
    return `${Number.isFinite(mb) && mb > 0 ? mb : 16}mb`;
})();

module.exports = {
    DATA_DIR, USERS_FILE, PASSWORDLESS_LOCAL, SHARED_LISTS_DIR, CATEGORIES_FILE,
    ARCHIVE_DIR, BACKUP_DIR, ARCHIVE_SNAPSHOT_DIR, MAX_ARCHIVE_SNAPSHOTS,
    AUTO_ARCHIVE_ENABLED, AUTO_ARCHIVE_ENV_MIN, DEFAULT_AUTO_ARCHIVE_MIN_CLOSED,
    DEFAULT_ARCHIVE_WARN_WITHIN,
    BIND_HOST, REACHABILITY, SESSION_TTL_MS, OPEN_RATE, isLoopbackAddress,
    LEGACY_SITE_KEY, DEFAULT_SITE_CONFIG_PATH, describeLegacySiteConfig, resolveSiteConfigPath,
    SCRYPT_N, SCRYPT_R, SCRYPT_P, KEY_LEN, HASH_SCHEME, HASH_PREFIX,
    isHashedPassword, hashPassword, verifyPassword, safeEqual, JSON_BODY_LIMIT
};
