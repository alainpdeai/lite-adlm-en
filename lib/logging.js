'use strict';

// Foundation aggregator (route ①, Round 7).
// logging.js now wires the request-log middleware and the /api/config,
// /api/audit, /api/health routes via register(); the heavy helpers live in
// logrotate.js (request log), audit.js (P2-A operation audit) and backup.js
// (startup backup + mirror). This file carries only the constants/helpers that
// register() itself needs (STARTED_AT, SECURITY_MODEL, DEV_AUTO_LOGIN,
// stampToDate) and re-exports the full public surface, so every existing
// require('./lib/logging') caller keeps working unchanged.

const fs = require('fs-extra');
const path = require('path');
const cfg = require('./config');
const paths = require('./paths');
const session = require('./session');

const { DATA_DIR, CATEGORIES_FILE, SHARED_LISTS_DIR, BACKUP_DIR, PASSWORDLESS_LOCAL,
    BIND_HOST, REACHABILITY } = cfg;

const {
    LOG_DIR, LOG_FILE, LOG_MAX_BYTES, LOG_KEEP,
    rotateLogIfNeeded, writeLogLine,
} = require('./logrotate');
const {
    AUDIT_FILE, AUDIT_MAX_BYTES, AUDIT_KEEP,
    summarizeForAudit, writeAudit,
} = require('./audit');
const {
    MIRROR_DIR, BACKUP_STAMP_RE, BACKUP_KEEP, getMirrorStatus,
    latestBackupStamp, backupAllJson, mirrorBackups,
    pruneStamps, pruneOldBackups,
} = require('./backup');

const STARTED_AT = new Date();

/* ---------------------------------------------------------------------------
 * Security boundary P2-B: name the security model out loud.
 *
 * The switch between "local, no password" and "shared, password required" is a
 * single environment variable, and until now the UI only ever received a
 * boolean. A boolean cannot tell a user which world they are standing in — and
 * a local-mode instance pointed at a shared machine looks exactly like a
 * misconfigured one from the inside. The model is therefore described once
 * here and rendered by the UI as a standing banner, not a login-page footnote.
 * ------------------------------------------------------------------------- */
const SECURITY_MODEL = PASSWORDLESS_LOCAL
    ? {
        mode: 'local-passwordless',
        requiresPassword: false,
        label: 'Local Passwordless Mode',
        hint: 'Sign in with a username only (no password required). Intended for single-user local machine use. Binds to loopback by default.',
    }
    : {
        mode: 'shared-authenticated',
        requiresPassword: true,
        label: 'Shared Authenticated Mode',
        hint: 'Requires username + password login, issuing a signed server session. For team members in a trusted network.',
    };

// Runtime config for the frontend (e.g. dev auto-login convenience)
const DEV_AUTO_LOGIN = PASSWORDLESS_LOCAL; // default ON for local dev; set LITETASK_DEV_LOGIN=0 for shared deployment

const stampToDate = (stamp) => {
    // 20261029T155329063Z -> 2026-10-29T15:53:29.063Z
    const m = String(stamp || '').match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(\d{3})Z$/);
    if (!m) return null;
    return new Date(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}.${m[7]}Z`);
};

// Install the request-log middleware and the config / audit / health routes.
// Called once from server.js at the same point the inline block used to live,
// so registration order (middleware -> config -> audit -> health) is preserved.
const register = (app, io, deps) => {
    const site = (deps && deps.site) || {};
    const openFolder = (deps && deps.openFolder) || { configured: false, rootCount: 0 };

    app.use((req, res, next) => {
        const t0 = process.hrtime.bigint();
        res.on('finish', () => {
            const ms = Math.round(Number(process.hrtime.bigint() - t0) / 1e4) / 100;
            // P0-2: sessions live in a cookie, never a URL; this is a defensive
            // scrub so a future caller cannot turn a query token into a log line.
            const safeUrl = String(req.originalUrl || '')
                .replace(/([?&](?:token|session|cookie)=)[^&]*/gi, '$1***');
            writeLogLine(`${new Date().toISOString()} ${req.method} ${safeUrl} ${res.statusCode} ${ms}ms`);
        });
        next();
    });

    // Single /api/config implementation (F3): branding + security model together.
    app.get('/api/config', (req, res) => {
        res.json({
            projectName: site.projectName || 'Lite ADLM',
            subtitle: site.subtitle || 'Shared Task Tree',
            loginSubtitle: site.loginSubtitle || 'Team Shared Workspace',
            goal: typeof site.goal === 'string' ? site.goal : '',
            devAutoLogin: DEV_AUTO_LOGIN,
            passwordless: PASSWORDLESS_LOCAL,
            securityModel: SECURITY_MODEL,
            reachability: REACHABILITY,
            bindHost: BIND_HOST,
            openFolder,
        });
    });

    // Security boundary P2-A: read the operation audit back. Admin-only — it names who did
    // what, which is exactly the record an ordinary user has no claim on.
    app.get('/api/audit', async (req, res) => {
        const actor = req.actor || {};
        if (!actor.isAdmin) {
            return res.status(403).json({
                error: 'Forbidden: Only administrators can read the audit log',
                code: 'ADMIN_REQUIRED',
            });
        }
        const asked = Number(req.query.limit || 200);
        const limit = Number.isFinite(asked) && asked > 0 ? Math.min(asked, 1000) : 200;
        try {
            const raw = await fs.readFile(AUDIT_FILE, 'utf8').catch(() => '');
            const lines = raw.split('\n').filter(Boolean).slice(-limit);
            const entries = [];
            for (const line of lines) {
                try {
                    entries.push(JSON.parse(line));
                } catch (err) {                                  // noqa: no-empty
                    // a torn line is dropped, never fatal: the audit is evidence,
                    // and losing one line must not lose the ones around it.
                }
            }
            res.json({ count: entries.length, file: AUDIT_FILE, entries });
        } catch (err) {
            res.status(500).json({ error: 'Failed to read audit log' });
        }
    });

    /* ---------------------------------------------------------------------------
     * P0 observability: /api/health (P0-1, first half)
     *
     * Answers "what does this process believe about itself": when it started,
     * whether its data tree is usable, how many items each list holds, how old the
     * newest backup is, and which login model is in force. Crucially it answers
     * **non-200** when that state is unusable — a health endpoint that always
     * returns 200 is not a health endpoint, it is a liveness ornament.
     * ------------------------------------------------------------------------- */
    app.get('/api/health', async (req, res) => {
        const report = {
            ok: true,
            startedAt: STARTED_AT.toISOString(),
            // 2026-10-29 fix: elapsed ms / 1000 = seconds, then round to 2 decimals.
            // The previous code divided by 100 twice (=/10000), so uptimeSec read
            // 1/10 of the real value (e.g. 36 min reported as 218s).
            uptimeSec: Math.round((Date.now() - STARTED_AT.getTime()) / 1000 * 100) / 100,
            pid: process.pid,
            nodeVersion: process.version,
            dataDir: { path: DATA_DIR, readable: false },
            lists: [],
            categories: { path: CATEGORIES_FILE, readable: false, parsable: false },
            backup: { dir: BACKUP_DIR, latestStamp: null, latestAt: null, ageSec: null },
            mirror: getMirrorStatus(),
            reachability: REACHABILITY,
            bindHost: BIND_HOST,
            openFolder,
            sessions: { active: session.activeSessionCount() },
            mode: {
                passwordless: PASSWORDLESS_LOCAL,
                devAutoLogin: DEV_AUTO_LOGIN,
                securityModel: SECURITY_MODEL,
            },
            log: { dir: LOG_DIR, file: LOG_FILE },
            audit: { dir: LOG_DIR, file: AUDIT_FILE }
        };
        const reasons = [];

        try {
            await fs.access(DATA_DIR, fs.constants.R_OK);
            await fs.readdir(DATA_DIR);
            report.dataDir.readable = true;
        } catch (err) {
            reasons.push('dataDir not readable: ' + err.message);
        }

        try {
            const raw = await fs.readFile(CATEGORIES_FILE, 'utf8');
            JSON.parse(raw);
            report.categories.readable = true;
            report.categories.parsable = true;
        } catch (err) {
            try {
                await fs.access(CATEGORIES_FILE, fs.constants.R_OK);
                report.categories.readable = true;   // present, but unparsable
            } catch (err2) {
                report.categories.readable = false;
            }
            reasons.push('categories.json not usable: ' + err.message);
        }

        try {
            const files = await fs.readdir(SHARED_LISTS_DIR);
            for (const f of files) {
                if (!f.toLowerCase().endsWith('.json')) continue;
                const listId = path.parse(f).name;
                if (!paths.validateListId(listId).ok) continue;
                const doc = await fs.readJson(path.join(SHARED_LISTS_DIR, f));
                report.lists.push({
                    listId,
                    items: Array.isArray(doc.items) ? doc.items.length : 0,
                    rev: doc.rev || null
                });
            }
        } catch (err) {
            reasons.push('shared lists unreadable: ' + err.message);
        }

        try {
            const stamp = await latestBackupStamp(BACKUP_DIR);
            report.backup.latestStamp = stamp || null;
            const at = stampToDate(stamp);
            if (at) {
                report.backup.latestAt = at.toISOString();
                report.backup.ageSec = Math.round((Date.now() - at.getTime()) / 1000);
            }
            if (MIRROR_DIR) {
                // P1-6: never report a stamp for a mirror that failed this run.
                // The real status comes from getMirrorStatus(); nothing to patch.
            }
        } catch (err) {
            reasons.push('backup dir unreadable: ' + err.message);
        }

        if (reasons.length) {
            report.ok = false;
            report.reason = reasons.join('; ');
            return res.status(503).json(report);
        }
        res.json(report);
    });
};

module.exports = {
    LOG_DIR, LOG_FILE, LOG_MAX_BYTES, LOG_KEEP, STARTED_AT, MIRROR_DIR,
    AUDIT_FILE, AUDIT_MAX_BYTES, AUDIT_KEEP, SECURITY_MODEL, DEV_AUTO_LOGIN,
    BACKUP_STAMP_RE, BACKUP_KEEP, getMirrorStatus,
    rotateLogIfNeeded, writeLogLine, writeAudit, summarizeForAudit,
    stampToDate, latestBackupStamp, backupAllJson, mirrorBackups,
    pruneStamps, pruneOldBackups, register
};
