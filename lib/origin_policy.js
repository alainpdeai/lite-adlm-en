'use strict';

// P1-5: origin normalization and request classification. Pure functions, no I/O,
// no third-party dependency. `http` is the only same-origin scheme because this
// service has no TLS; cross-origin callers must match an exact allowlist entry.

const wildcard = /[*]/;

const normalizeOrigin = (value) => {
    if (typeof value !== 'string' || !value.trim()) return { ok: false, reason: 'not-string' };
    let u;
    try {
        u = new URL(value.trim());
    } catch (_err) {
        return { ok: false, reason: 'parse' };
    }
    const scheme = u.protocol.replace(':', '').toLowerCase();
    if (scheme !== 'http' && scheme !== 'https') return { ok: false, reason: 'scheme' };
    if (u.username || u.password) return { ok: false, reason: 'credentials' };
    if (u.pathname !== '/' && u.pathname !== '') return { ok: false, reason: 'path' };
    if (u.search || u.hash) return { ok: false, reason: 'query' };
    if (wildcard.test(u.hostname)) return { ok: false, reason: 'wildcard' };
    return {
        ok: true,
        origin: u.origin.toLowerCase(),
        scheme,
        host: u.hostname.toLowerCase(),
        port: u.port || '',
    };
};

const parseAllowList = (raw) => {
    if (raw === undefined || raw === null || String(raw).trim() === '') {
        return { origins: [], invalid: [], empty: true };
    }
    const parts = String(raw).split(',').map((s) => s.trim());
    if (parts.length === 1 && parts[0] === '') {
        return { origins: [], invalid: [], empty: true };
    }
    const invalid = [];
    const origins = [];
    for (const part of parts) {
        if (!part || wildcard.test(part)) {
            invalid.push(part || '*');
            continue;
        }
        const n = normalizeOrigin(part);
        if (!n.ok) {
            invalid.push(part);
            continue;
        }
        origins.push(n.origin);
    }
    if (invalid.length) return { origins: [], invalid, empty: false };
    return { origins: [...new Set(origins)], invalid: [], empty: false };
};

const isLoopbackHostname = (hostname) => {
    if (typeof hostname !== 'string') return false;
    let h = hostname.trim().toLowerCase();
    if (h.startsWith('[') && h.endsWith(']')) h = h.slice(1, -1);
    if (h === 'localhost' || h === '::1' || h === '0:0:0:0:0:0:0:1') return true;
    if (h.startsWith('::ffff:')) h = h.slice(7);
    const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(h);
    return Boolean(m) && Number(m[1]) === 127;
};

const splitHost = (header) => {
    const raw = String(header || '');
    if (raw.startsWith('[')) {
        const end = raw.indexOf(']');
        if (end > 0) return { host: raw.slice(1, end), port: raw.slice(end + 2) };
    }
    const i = raw.lastIndexOf(':');
    if (i > 0) return { host: raw.slice(0, i), port: raw.slice(i + 1) };
    return { host: raw, port: '' };
};

// Returns 'absent' | 'same-origin' | 'allowlisted' | 'cross-origin'.
const classifyRequest = (req, allowOrigins) => {
    const headers = (req && req.headers) || {};
    const originRaw = headers.origin || headers.Origin;
    if (!originRaw) return 'absent';
    const n = normalizeOrigin(String(originRaw));
    if (!n.ok) return 'cross-origin';

    const host = splitHost(headers.host || headers.Host);
    const defaultPort = n.scheme === 'http' ? '80' : '443';
    const originPort = n.port || defaultPort;
    const hostPort = host.port || defaultPort;
    const loopback = isLoopbackHostname(n.host) && isLoopbackHostname(host.host);
    if (n.scheme === 'http' && loopback && String(originPort) === String(hostPort)) {
        return 'same-origin';
    }

    const allow = (allowOrigins && Array.isArray(allowOrigins.origins)) ? allowOrigins.origins : [];
    if (allow.includes(n.origin)) return 'allowlisted';
    return 'cross-origin';
};

module.exports = {
    normalizeOrigin, parseAllowList, isLoopbackHostname, classifyRequest,
};