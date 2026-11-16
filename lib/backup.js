'use strict';

// Startup backup + mirror (P0 / P1-6).
//
// P1-6 changes the mirror from "on by default, in the user profile" to
// "off unless explicitly enabled with an absolute, validated path":
//   unset / empty      -> off (reason 'unset')
//   0/off/false/none   -> off ('explicit-off')
//   relative path      -> off ('not-absolute')
//   inside project/data/backup -> off ('inside-project')
//   outside the user profile on Windows -> off ('outside-profile')
//   otherwise          -> on  ('explicit')
//
// Derivation is pure: it never creates, probes or chmods a directory. Directory
// preparation happens only when an enabled mirror is actually used.

const fs = require('fs-extra');
const path = require('path');
const os = require('os');
const cfg = require('./config');

const { DATA_DIR, BACKUP_DIR } = cfg;

const PROJECT_ROOT = path.join(__dirname, '..');
const OFF_VALUES = ['0', 'off', 'false', 'none'];

const realpathNearestSync = (p) => {
    let cur = path.resolve(p);
    const missing = [];
    for (let i = 0; i < 64; i++) {
        try {
            const real = fs.realpathSync(cur);
            return missing.length ? path.join(real, ...missing.slice().reverse()) : real;
        } catch (err) {
            if (err && err.code !== 'ENOENT' && err.code !== 'ENOTDIR') return path.resolve(p);
            const parent = path.dirname(cur);
            if (parent === cur) return path.resolve(p);
            missing.push(path.basename(cur));
            cur = parent;
        }
    }
    return path.resolve(p);
};

const insideOrEqual = (root, candidate) => {
    try {
        const rootReal = realpathNearestSync(root);
        const candidateReal = realpathNearestSync(candidate);
        const rel = path.relative(rootReal, candidateReal);
        return rel === '' || (rel !== '..' && !rel.startsWith('..' + path.sep) && !path.isAbsolute(rel));
    } catch (_err) {
        return false;
    }
};

const describeMirrorConfig = (raw) => {
    const value = raw === undefined ? process.env.LITETASK_BACKUP_MIRROR : raw;
    if (value === undefined || value === null || String(value).trim() === '') {
        return { enabled: false, dir: null, reason: 'unset' };
    }
    const trimmed = String(value).trim();
    if (OFF_VALUES.includes(trimmed.toLowerCase())) {
        return { enabled: false, dir: null, reason: 'explicit-off' };
    }
    if (!path.isAbsolute(trimmed)) {
        return { enabled: false, dir: null, reason: 'not-absolute' };
    }
    const candidate = path.resolve(trimmed);
    if (insideOrEqual(PROJECT_ROOT, candidate)
        || insideOrEqual(DATA_DIR, candidate)
        || insideOrEqual(BACKUP_DIR, candidate)) {
        return { enabled: false, dir: null, reason: 'inside-project' };
    }
    if (process.platform === 'win32' && !insideOrEqual(os.homedir(), candidate)) {
        return { enabled: false, dir: null, reason: 'outside-profile' };
    }
    return { enabled: true, dir: candidate, reason: 'explicit' };
};

const MIRROR_CONFIG = describeMirrorConfig();
const MIRROR_DIR = MIRROR_CONFIG.enabled ? MIRROR_CONFIG.dir : null;

const mirrorState = {
    enabled: false,
    dir: null,
    reason: MIRROR_CONFIG.reason,
    latestStamp: null,
    lastAttempt: null,
};

const getMirrorStatus = () => ({
    enabled: mirrorState.enabled,
    dir: mirrorState.enabled ? mirrorState.dir : null,
    reason: mirrorState.reason,
    latestStamp: mirrorState.latestStamp,
    lastAttempt: mirrorState.lastAttempt,
});

// Snapshot filenames carry a fixed-width ISO stamp, e.g.
// categories.20261029T155329063Z.json -- that stamp is what rotation keys on.
const BACKUP_STAMP_RE = /\.(\d{8}T\d{9}Z)\.json$/i;

// Rotation cap: how many of the newest startup snapshots to keep.
const BACKUP_KEEP = Math.max(1, Number(process.env.LITETASK_BACKUP_KEEP || 5));

const latestBackupStamp = async (dir) => {
    let best = null;
    let entries;
    try {
        entries = await fs.readdir(dir, { withFileTypes: true });
    } catch (err) {
        return null;
    }
    for (const entry of entries) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
            const deeper = await latestBackupStamp(full);
            if (deeper && (!best || deeper > best)) best = deeper;
            continue;
        }
        const m = entry.name.match(BACKUP_STAMP_RE);
        if (m && (!best || m[1] > best)) best = m[1];
    }
    return best;
};

// Delete every snapshot older than the newest `keep` stamps. Only files whose
// name matches the snapshot pattern are touched. Generalised over the directory
// so the mirror can reuse the exact same rule.
const pruneStamps = async (dir, keep) => {
    const byStamp = new Map();
    const walk = async (d) => {
        let entries;
        try {
            entries = await fs.readdir(d, { withFileTypes: true });
        } catch (err) {
            return;
        }
        for (const entry of entries) {
            const full = path.join(d, entry.name);
            if (entry.isDirectory()) {
                await walk(full);
                continue;
            }
            const m = entry.name.match(BACKUP_STAMP_RE);
            if (!m) continue;
            const stamp = m[1];
            if (!byStamp.has(stamp)) byStamp.set(stamp, []);
            byStamp.get(stamp).push(full);
        }
    };
    await walk(dir);
    // Fixed-width ISO stamps sort lexicographically the same as chronologically
    const stamps = Array.from(byStamp.keys()).sort().reverse();
    const doomed = stamps.slice(keep);
    let removed = 0;
    for (const s of doomed) {
        for (const f of byStamp.get(s)) {
            await fs.remove(f);
            removed++;
        }
    }
    if (removed) {
        console.log(`[LiteTask] Backup rotation: removed ${removed} file(s) from ${doomed.length} old snapshot(s); keeping newest ${Math.min(keep, stamps.length)} of ${stamps.length} (${dir})`);
    }
    return { kept: Math.min(keep, stamps.length), removed };
};

const pruneOldBackups = async () => pruneStamps(BACKUP_DIR, BACKUP_KEEP);

const prepareMirrorDir = async () => {
    if (!MIRROR_CONFIG.enabled) return { ok: false, code: MIRROR_CONFIG.reason };
    try {
        await fs.ensureDir(MIRROR_CONFIG.dir);
        if (process.platform !== 'win32') {
            await fs.chmod(MIRROR_CONFIG.dir, 0o700);
        } else {
            console.warn('[LiteTask] Mirror root is under user profile; permissions depend on user directory ACL');
        }
        mirrorState.enabled = true;
        mirrorState.dir = MIRROR_CONFIG.dir;
        mirrorState.reason = 'explicit';
        return { ok: true };
    } catch (err) {
        console.warn('[LiteTask] Mirror directory unavailable:', err.message);
        mirrorState.enabled = false;
        mirrorState.dir = null;
        mirrorState.reason = 'not-writable';
        return { ok: false, code: 'MIRROR_NOT_WRITABLE' };
    }
};

const backupAllJson = async () => {
    const stamp = new Date().toISOString().replace(/[-:.]/g, '');
    const sources = [];
    const walk = async (dir) => {
        const entries = await fs.readdir(dir, { withFileTypes: true });
        for (const entry of entries) {
            const full = path.join(dir, entry.name);
            if (entry.isDirectory()) await walk(full);
            else if (entry.isFile() && entry.name.toLowerCase().endsWith('.json')) sources.push(full);
        }
    };
    await walk(DATA_DIR);
    for (const src of sources) {
        const relative = path.relative(DATA_DIR, src);
        const parsed = path.parse(relative);
        const target = path.join(BACKUP_DIR, parsed.dir, `${parsed.name}.${stamp}.json`);
        await fs.ensureDir(path.dirname(target));
        await fs.copyFile(src, target);
    }
    console.log(`[LiteTask] Startup backup: ${sources.length} JSON file(s) -> ${BACKUP_DIR} (stamp ${stamp})`);
    await pruneOldBackups();

    let mirrored = 0;
    let mirrorResult = { enabled: false, ok: null, code: null };
    if (MIRROR_CONFIG.enabled) {
        const prep = await prepareMirrorDir();
        if (!prep.ok) {
            mirrorState.lastAttempt = {
                stamp, ok: false, code: prep.code, at: new Date().toISOString(),
            };
            mirrorResult = { enabled: false, ok: false, code: prep.code };
        } else {
            const r = await mirrorBackups(stamp);
            mirrored = r.copied || 0;
            mirrorState.lastAttempt = {
                stamp, ok: r.ok, code: r.code || null, at: new Date().toISOString(),
            };
            if (r.ok) {
                mirrorState.latestStamp = stamp;
            } else {
                mirrorState.enabled = false;
                mirrorState.reason = 'mirror-failed';
            }
            mirrorResult = { enabled: mirrorState.enabled, ok: r.ok, code: r.code || null };
        }
    }
    return { count: sources.length, stamp, mirrored, mirror: mirrorResult };
};

// Copy the snapshots of one stamp to the mirror, keeping the same relative
// layout, then apply the same rotation cap so the mirror cannot grow forever.
// Never throws: a failed mirror must not make the local board unavailable.
const mirrorBackups = async (stamp) => {
    if (!MIRROR_CONFIG.enabled) return { ok: false, copied: 0, code: MIRROR_CONFIG.reason };
    let copied = 0;
    try {
        const walk = async (dir) => {
            let entries;
            try {
                entries = await fs.readdir(dir, { withFileTypes: true });
            } catch (err) {
                return;
            }
            for (const entry of entries) {
                const full = path.join(dir, entry.name);
                if (entry.isDirectory()) {
                    await walk(full);
                    continue;
                }
                if (!BACKUP_STAMP_RE.test(entry.name)) continue;
                if (stamp && entry.name.indexOf(`.${stamp}.`) === -1) continue;
                const rel = path.relative(BACKUP_DIR, full);
                const target = path.join(MIRROR_CONFIG.dir, rel);
                await fs.ensureDir(path.dirname(target));
                await fs.copyFile(full, target);
                copied++;
            }
        };
        await walk(BACKUP_DIR);
        if (copied) await pruneStamps(MIRROR_CONFIG.dir, BACKUP_KEEP);
        console.log(`[LiteTask] Backup mirror: ${copied} file(s) -> ${MIRROR_CONFIG.dir}`);
        return { ok: true, copied };
    } catch (err) {
        console.warn('[LiteTask] Backup mirror failed:', err.message);
        return { ok: false, copied, code: 'MIRROR_COPY_FAILED' };
    }
};

module.exports = {
    MIRROR_CONFIG, MIRROR_DIR, BACKUP_STAMP_RE, BACKUP_KEEP,
    describeMirrorConfig, prepareMirrorDir, getMirrorStatus,
    latestBackupStamp, pruneStamps, pruneOldBackups, backupAllJson, mirrorBackups,
};