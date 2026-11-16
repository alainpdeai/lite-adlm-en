const express = require('express');
const http = require('http');
const os = require('os');
const crypto = require('crypto');
const fs = require('fs-extra');
const path = require('path');
const chokidar = require('chokidar');
const { Server } = require('socket.io');

const paths = require('./lib/paths');
const guards = require('./lib/guard');
const openFolder = require('./lib/open_folder');
const originPolicy = require('./lib/origin_policy');
const socketGate = require('./lib/socket_gate');
const backupModule = require('./lib/backup');
const shutdown = require('./lib/shutdown');
const csp = require('./lib/csp');

const app = express();
const server = http.createServer(app);
const io = new Server(server);

// P0-2: reject non-loopback sources before any body parsing or routing.
app.use(guards.loopbackGuard);

// ---- Modular foundation (route ①) ----
// Shared helpers now live in lib/{config,util,logging,categories,status,schema,
// bootstrap}. The orchestrator pulls them into module scope below and wires them
// into the per-domain register(app, io, deps) calls; it owns startup + socket
// wiring only, so it stays a thin orchestrator.
const cfg = require('./lib/config');
const util = require('./lib/util');
const logging = require('./lib/logging');
const archive = require('./lib/archive');
const links = require('./lib/links');
const actors = require('./lib/actors');
const lists = require('./lib/lists');
const categories = require('./lib/categories');
const status = require('./lib/status');
const schema = require('./lib/schema');
const bootstrap = require('./lib/bootstrap');

const { requireConfirm, actorOf } = lists;
const {
    getCategories
} = categories;
const {
    getStatusConfig, collectStatuses, sanitizeStatus
} = status;
const {
    sanitizeRelatesTo, sanitizeLocalDirectories, validateItems
} = schema;
const {
    saveUsers, initSharedLists, initCategories, migrateUserPasswords
} = bootstrap;
const {
    DATA_DIR, USERS_FILE, PASSWORDLESS_LOCAL, SHARED_LISTS_DIR, CATEGORIES_FILE,
    ARCHIVE_DIR, BACKUP_DIR, ARCHIVE_SNAPSHOT_DIR, MAX_ARCHIVE_SNAPSHOTS,
    AUTO_ARCHIVE_ENABLED, AUTO_ARCHIVE_ENV_MIN, DEFAULT_AUTO_ARCHIVE_MIN_CLOSED,
    DEFAULT_ARCHIVE_WARN_WITHIN, SCRYPT_N, SCRYPT_R, SCRYPT_P, KEY_LEN,
    HASH_SCHEME, HASH_PREFIX, isHashedPassword, hashPassword, verifyPassword,
    safeEqual, JSON_BODY_LIMIT,
    contentRev, withLock, atomicWriteJson, DIFF_FIELD_LABELS, DIFF_IGNORE_KEYS,
    normVal, stableEqual, flattenItems, diffItems, stampNow, isUserAdmin, usernameOf,
    writeAudit, LOG_DIR, LOG_FILE, AUDIT_FILE, STARTED_AT, SECURITY_MODEL,
    DEV_AUTO_LOGIN, MIRROR_DIR, BACKUP_STAMP_RE, BACKUP_KEEP, backupAllJson,
    BIND_HOST, REACHABILITY
} = Object.assign({}, cfg, util, logging);

// ---- Site / first-run initialization config (drives branding + admin) ----
// config/site.json is the one file the operator edits during `npm run init`
// (or by hand). It is optional: every value has a sane default so the system
// still boots if the file is missing or partially filled.
let SITE = {};
const SITE_CFG = cfg.resolveSiteConfigPath();
try {
    SITE = fs.readJsonSync(SITE_CFG.path);
    if (typeof SITE !== 'object' || SITE === null) SITE = {};
} catch (err) {
    // Missing/invalid site config is non-fatal; defaults below apply.
    SITE = {};
}
const BRAND = (SITE.logPrefix && String(SITE.logPrefix).trim()) || 'ADLM';
const LP = BRAND;
const OPEN_ROOTS = openFolder.resolveAllowedRoots(SITE.project && SITE.project.root);
const ALLOW_ORIGINS = originPolicy.parseAllowList(process.env.LITETASK_SOCKET_ALLOW_ORIGINS);

// Capacity & performance P2: express.json() defaults to a 100 kB body, and a write here is
// always the *whole* list — there is no partial update. At ~300 items a save
// was therefore refused with 413, which makes the one write path this system
// has unusable well before rendering ever becomes the bottleneck. The cap is
// raised to something that matches "send the entire list", and stays tunable.
app.use(express.json({ limit: JSON_BODY_LIMIT }));
// P2-4: CSP must run before static so the HTML response carries the header.
app.use(csp.createCspMiddleware({ htmlPath: path.join(__dirname, 'public', 'index.html') }));
app.use(express.static(path.join(__dirname, 'public')));

// P0-2: one identity gate for every /api route; handlers consume req.actor.
// P0-1: the identifier guard runs after the identity gate, so 401/403 wins over
// 400 (the order is part of the contract).
app.use('/api', guards.createAuthGate());
app.use('/api/lists/:id', paths.listIdParamGuard);
app.use('/api/archive/:id', paths.listIdParamGuard);

// Concurrent-write protection (B3) and leaf helpers (contentRev / withLock /
// atomicWriteJson / diff / flatten / stamp / admin lookups) are provided by
// lib/util.js; status + schema + bootstrap helpers by lib/{status,schema,
// bootstrap}.js. They are injected into the domain modules at register time so
// the modules stay free of server.js scope.

// Initialize data dirs and initial admin user
fs.ensureDirSync(DATA_DIR);
fs.ensureDirSync(SHARED_LISTS_DIR);

if (!fs.existsSync(USERS_FILE)) {
    // First run: seed the initial admin from config/site.json (init settings),
    // falling back to the legacy admin/admin defaults if unset.
    const a = (SITE.admin && typeof SITE.admin === 'object') ? SITE.admin : {};
    const defaultUsers = [{
        userId: a.userId || 'user_admin',
        username: a.username || 'admin',
        password: hashPassword(a.password || 'admin'),
        isAdmin: true
    }];
    fs.writeJsonSync(USERS_FILE, defaultUsers, { spaces: 2 });
}

initSharedLists();
initCategories();
migrateUserPasswords();

// Watcher for real-time events on JSON changes in shared lists and users
const watcher = chokidar.watch([SHARED_LISTS_DIR, USERS_FILE], {
    ignored: /(^|[\/\\])\../,
    persistent: true,
    ignoreInitial: true,
});

watcher.on('all', async (event, filePath) => {
    if (!filePath.endsWith('.json')) return;
    // Incremental sync P3-A: the event used to be an empty ping, so every client had to
    // refetch everything and re-render to find out whether anything had even
    // changed. It now says which list, what revision, and (when the file knows)
    // who wrote it — a client that already holds that revision can stop there.
    const listId = path.basename(filePath, '.json');
    const payload = { listId, rev: null, source: 'file', at: new Date().toISOString() };
    try {
        const doc = await fs.readJson(filePath);
        if (doc && Array.isArray(doc.items)) payload.rev = contentRev(doc.items);
        payload.actor = await actorOf(doc && doc.updatedBy);
    } catch (err) {
        // A file being rewritten is momentarily unparsable; the event is still
        // worth sending — clients fall back to refetching.
    }
    io.emit('file-changed', payload);
});

// A watcher only sees events while this process is alive. The rule for editing
// a list by hand is "stop the instance -> edit the JSON -> start it again", so
// by construction the edits that matter most are made while nothing is
// listening: no 'file-changed' can ever fire for them, and a browser left open
// keeps the pre-stop snapshot forever (closed tasks still shown as open).
// Tell each socket to refetch as it connects, which covers exactly that case.
// Emitted to the connecting socket only -- broadcasting this would make every
// open tab refetch whenever somebody opens another one.
io.on('connection', (socket) => {
    socket.emit('resync');
});

actors.register(app, io, { saveUsers });

links.register(app, io, { getCategories, getStatusConfig });
lists.register(app, io, { getStatusConfig, collectStatuses, sanitizeStatus, validateItems, sanitizeRelatesTo, sanitizeLocalDirectories });

archive.register(app, io, { requireConfirm, getCategories, writeAudit });
// P0-3: validated, parameterized launcher. No shell, no command string.
openFolder.register(app, { roots: OPEN_ROOTS.roots, writeAudit });

// Single /api/config implementation (branding + security model) is in logging.js.
logging.register(app, io, {
    site: SITE,
    openFolder: { configured: OPEN_ROOTS.configured, rootCount: OPEN_ROOTS.roots.length },
});

// P1-5: one origin/session gate for Socket.IO, installed before listen.
socketGate.installSocketGate(io, { allowOrigins: ALLOW_ORIGINS });

// P2-9: install signal handling before listen so startup Ctrl+C is covered.
// The first startup log line is unchanged.
shutdown.installShutdown({ server, io, watcher, brand: LP });

const PORT = process.env.PORT || (SITE.port && Number(SITE.port) > 0 ? Number(SITE.port) : 3000);
server.on('error', (err) => {
    if (err.code === 'EADDRINUSE') {
        console.error(
            `\n[${LP}] ERROR: Port ${PORT} is already in use.\n` +
            `  Another ${BRAND} instance may already be running.\n` +
            `  Stop it first, or start on a different port:\n` +
            `    PORT=${Number(PORT) + 1} node server.js\n`
        );
    } else {
        console.error(`[${LP}] ERROR: cannot bind to ${BIND_HOST}:${PORT} (${err.code || err.message})`);
    }
    process.exit(1);
});
server.listen(PORT, BIND_HOST, async () => {
    console.log(`Server running on http://localhost:${PORT}`);
    console.log(`[${LP}] bind=${BIND_HOST} reachability=${REACHABILITY} mode=${PASSWORDLESS_LOCAL ? 'local-passwordless' : 'shared-authenticated'}`);
    if (REACHABILITY === 'non-loopback') {
        console.warn(`[${LP}] WARNING: listening on a non-loopback address (${BIND_HOST}); the service is reachable from the network.`);
    }
    if (SITE_CFG.redirected) {
        console.log(`[${LP}] site config redirected: ${SITE_CFG.path}`);
    }
    const legacyKeys = cfg.describeLegacySiteConfig(SITE);
    if (legacyKeys.length) {
        console.warn(`[${LP}] WARNING: Deprecated fields ${legacyKeys.join(',')} ignored; security mode is controlled exclusively by LITETASK_DEV_LOGIN (set to 0 for shared auth).`);
    }
    const mirrorCfg = backupModule.MIRROR_CONFIG;
    if (mirrorCfg.enabled) {
        console.log(`[${LP}] backup-mirror: enabled -> ${mirrorCfg.dir}`);
    } else if (mirrorCfg.reason === 'unset') {
        console.log(`[${LP}] Mirror backup disabled by default (enable via LITETASK_BACKUP_MIRROR=<absolute-path>)`);
    } else if (mirrorCfg.reason === 'explicit-off') {
        console.log(`[${LP}] Mirror backup explicitly disabled (${mirrorCfg.reason})`);
    } else {
        console.warn(`[${LP}] Invalid mirror backup config, treated as disabled (${mirrorCfg.reason})`);
    }
    if (ALLOW_ORIGINS.empty) {
        console.log(`[${LP}] Origin whitelist empty: cross-origin Sockets rejected`);
    } else if (ALLOW_ORIGINS.invalid.length) {
        console.warn(`[${LP}] Invalid origin whitelist, cleared: ${ALLOW_ORIGINS.invalid.join(',')}`);
    }
    if (process.env.LITETASK_DRILL_FAULT) {
        console.warn(`[${LP}] WARNING: Drill injection enabled: ${process.env.LITETASK_DRILL_FAULT}`);
    }
    try {
        const rec = await archive.recoverInterruptedTransactions();
        if (rec && rec.failed) {
            console.warn(`[${LP}] WARNING: ${rec.failed} unfinished transaction(s) require manual recovery (see data/archive-snapshots/*.txn.json)`);
        }
    } catch (err) {
        console.warn(`[${LP}] Startup recovery failed:`, err.message);
    }
    try {
        await backupAllJson();
    } catch (err) {
        // A failed snapshot must not make the local board unavailable.
        console.warn(`[${LP}] Startup backup failed:`, err.message);
    }
    // A1: keep active list files small (runs once all helpers are initialised)
    archive.autoArchiveSweep();
});
