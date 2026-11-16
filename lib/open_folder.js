'use strict';

// Process invocation domain (P0-3). Converts folder opening from shell execution to parameterized spawn:
//   1. Type / length / null-byte / URL / relative path -> 400
//   2. Allowed root not configured -> 403
//   3. realpath + membership check -> 403
//   4. Existence -> 404
//   5. Directory type check -> 400
//   6. Readability -> 403
//   7. Launcher availability -> 503
//   8. Rate limit -> 429
// All rejections occur before spawn; successes and denials are logged to audit.

const fs = require('fs-extra');
const path = require('path');
const { spawn } = require('child_process');

const paths = require('./paths');
const errors = require('./errors');

const MAX_PATH_LEN = 260;

const resolveAllowedRoots = (siteRoot) => {
    const raw = process.env.LITETASK_OPEN_ROOT
        || process.env.LITETASK_PROJECT_ROOT
        || (typeof siteRoot === 'string' ? siteRoot : '');
    if (!raw || !String(raw).trim()) return { configured: false, roots: [] };
    const seen = new Set();
    const roots = [];
    for (const part of String(raw).split(path.delimiter)) {
        const t = part.trim();
        if (!t) continue;
        const abs = path.resolve(t);
        if (seen.has(abs)) continue;
        seen.add(abs);
        try {
            if (fs.statSync(abs).isDirectory()) roots.push(abs);
        } catch (_err) { /* a missing root is ignored */ }
    }
    return { configured: roots.length > 0, roots };
};

const invalid = (code, status, message) => ({ ok: false, code, status, message });

const validateFolderPath = async (raw, roots) => {
    if (typeof raw !== 'string' || !raw || raw.length > MAX_PATH_LEN || raw.includes('\0')) {
        return invalid('INVALID_PATH', 400, 'Path must be an absolute path');
    }
    if (/^[A-Za-z][A-Za-z0-9+.-]*:\/\//.test(raw)) {
        return invalid('INVALID_PATH', 400, 'URL is not a local directory path');
    }
    if (!path.isAbsolute(raw) || raw.startsWith('\\\\') || raw.startsWith('//')) {
        return invalid('INVALID_PATH', 400, 'Path must be an absolute path');
    }
    if (!Array.isArray(roots) || roots.length === 0) {
        return invalid('OPEN_ROOT_NOT_CONFIGURED', 403, 'Allowed root not configured, feature disabled');
    }

    const abs = path.resolve(raw);
    let root = null;
    for (const r of roots) {
        const rAbs = path.resolve(r);
        if (abs === rAbs || await paths.belongsTo(rAbs, abs)) { root = rAbs; break; }
    }
    if (!root) return invalid('PATH_OUTSIDE_ALLOWED_ROOT', 403, 'Path outside allowed root');

    let st = null;
    try { st = await fs.stat(abs); } catch (_err) { st = null; }
    if (!st) return invalid('PATH_NOT_FOUND', 404, 'Path does not exist');
    if (!st.isDirectory()) return invalid('NOT_A_DIRECTORY', 400, 'Target is not a directory');
    try { await fs.access(abs, fs.constants.R_OK); }
    catch (_err) { return invalid('PATH_NOT_READABLE', 403, 'Path is not readable'); }

    return { ok: true, abs, rel: path.relative(root, abs), root };
};

const launcherForPlatform = (platform, override) => {
    if (override) return { cmd: override, argsFor: (p) => [p] };
    if (platform === 'win32') {
        const sysRoot = process.env.SystemRoot || 'C:\\Windows';
        return { cmd: path.join(sysRoot, 'explorer.exe'), argsFor: (p) => [p] };
    }
    if (platform === 'darwin') return { cmd: 'open', argsFor: (p) => [p] };
    return { cmd: 'xdg-open', argsFor: (p) => [p] };
};

let commandCache = { cmd: null, present: false, at: 0 };

const commandExists = (cmd) => {
    if (!cmd) return false;
    const now = Date.now();
    if (commandCache.cmd === cmd && now - commandCache.at < 10000) return commandCache.present;
    let present = false;
    if (path.isAbsolute(cmd) || cmd.includes('/') || cmd.includes('\\')) {
        present = fs.existsSync(cmd);
    } else {
        const ext = process.platform === 'win32'
            ? (process.env.PATHEXT || '.EXE;.CMD;.BAT;.COM').split(';')
            : [''];
        for (const dir of String(process.env.PATH || '').split(path.delimiter)) {
            if (!dir) continue;
            for (const e of ext) {
                if (fs.existsSync(path.join(dir, cmd + e))) { present = true; break; }
            }
            if (present) break;
        }
    }
    commandCache = { cmd, present, at: now };
    return present;
};

const spawnLauncher = (cmd, args) => {
    try {
        const child = spawn(cmd, args, {
            shell: false,
            detached: true,
            stdio: 'ignore',
            windowsHide: true,
        });
        child.on('error', (err) => {
            console.warn('[LiteTask] open-folder launcher failed:', err.code || err.message);
        });
        child.unref();
        return { ok: true, pid: child.pid };
    } catch (err) {
        return { ok: false, error: err && err.message };
    }
};

const rateBuckets = new Map();
const parseRate = (raw) => {
    const m = /^(\d+)\/(\d+)$/.exec(String(raw || '10/10').trim());
    if (!m) return { limit: 10, windowMs: 10000 };
    return {
        limit: Math.max(1, Number(m[1])),
        windowMs: Math.max(1, Number(m[2])) * 1000,
    };
};

const allowRate = (key, rate) => {
    const now = Date.now();
    const b = rateBuckets.get(key);
    if (!b || now >= b.reset) {
        rateBuckets.set(key, { count: 1, reset: now + rate.windowMs });
        return true;
    }
    if (b.count >= rate.limit) return false;
    b.count += 1;
    return true;
};

const register = (app, deps) => {
    const roots = (deps && deps.roots) || [];
    const writeAudit = deps && deps.writeAudit;
    const rate = parseRate(process.env.LITETASK_OPEN_RATE);
    const launcherOverride = process.env.LITETASK_OPEN_LAUNCHER;

    app.post('/api/open-folder', async (req, res) => {
        const actor = req.actor || {};
        const actorId = actor.userId || null;
        const deny = async (code, status, message, extra) => {
            if (typeof writeAudit === 'function') {
                try {
                    await writeAudit({
                        actor: actorId, action: 'open-folder', outcome: 'rejected',
                        params: {}, note: code,
                    });
                } catch (_e) { /* audit is best-effort */ }
            }
            return errors.sendError(res, status, code, message, extra);
        };

        const raw = req.body && req.body.folderPath;
        const v = await validateFolderPath(raw, roots);
        if (!v.ok) return deny(v.code, v.status, v.message);

        const l = launcherForPlatform(process.platform, launcherOverride);
        if (!commandExists(l.cmd)) {
            return deny('LAUNCHER_UNAVAILABLE', 503, 'System file manager unavailable',
                { launcher: path.basename(l.cmd) });
        }
        if (!allowRate(actorId || 'anonymous', rate)) {
            return deny('TOO_MANY_REQUESTS', 429, 'Too many requests');
        }

        const r = spawnLauncher(l.cmd, l.argsFor(v.abs));
        if (!r.ok) return deny('LAUNCHER_UNAVAILABLE', 503, 'System file manager unavailable');

        res.json({ success: true, path: v.rel });
        if (typeof writeAudit === 'function') {
            void writeAudit({
                actor: actorId, action: 'open-folder', outcome: 'ok',
                params: { rootIndex: roots.indexOf(v.root), relPath: v.rel },
                note: 'opened',
            });
        }
    });
};

module.exports = {
    resolveAllowedRoots, validateFolderPath, launcherForPlatform,
    commandExists, spawnLauncher, register,
};