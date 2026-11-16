var __getOwnPropNames = Object.getOwnPropertyNames;
var __commonJS = (cb, mod) => function __require() {
  try {
    return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
  } catch (e) {
    throw mod = 0, e;
  }
};

// tests/_artifacts/_skill_build/lib/config.js
var require_config = __commonJS({
  "tests/_artifacts/_skill_build/lib/config.js"(exports2, module2) {
    "use strict";
    var crypto2 = require("crypto");
    var fs2 = require("fs");
    var path2 = require("path");
    var DATA_DIR2 = process.env.LITETASK_DATA_DIR ? path2.resolve(process.env.LITETASK_DATA_DIR) : path2.join(__dirname, "data");
    var USERS_FILE2 = path2.join(DATA_DIR2, "users.json");
    var PASSWORDLESS_LOCAL2 = process.env.LITETASK_DEV_LOGIN !== "0";
    var SHARED_LISTS_DIR2 = path2.join(DATA_DIR2, "shared_lists");
    var CATEGORIES_FILE2 = path2.join(DATA_DIR2, "categories.json");
    var ARCHIVE_DIR2 = path2.join(DATA_DIR2, "archive");
    var BACKUP_DIR2 = process.env.LITETASK_BACKUP_DIR ? path2.resolve(process.env.LITETASK_BACKUP_DIR) : path2.join(__dirname, "backup");
    var ARCHIVE_SNAPSHOT_DIR2 = path2.join(DATA_DIR2, "archive-snapshots");
    var MAX_ARCHIVE_SNAPSHOTS2 = 20;
    var AUTO_ARCHIVE_ENABLED2 = process.env.LITETASK_AUTO_ARCHIVE !== "0";
    var AUTO_ARCHIVE_ENV_MIN2 = process.env.LITETASK_AUTO_ARCHIVE_MIN_CLOSED;
    var DEFAULT_AUTO_ARCHIVE_MIN_CLOSED2 = 25;
    var DEFAULT_ARCHIVE_WARN_WITHIN2 = 5;
    var SCRYPT_N2 = 16384;
    var SCRYPT_R2 = 8;
    var SCRYPT_P2 = 1;
    var KEY_LEN2 = 64;
    var HASH_SCHEME2 = "scrypt";
    var HASH_PREFIX2 = HASH_SCHEME2 + "$";
    var isHashedPassword2 = (stored) => typeof stored === "string" && stored.startsWith(HASH_PREFIX2);
    var hashPassword2 = (plain) => {
      const salt = crypto2.randomBytes(16);
      const key = crypto2.scryptSync(String(plain), salt, KEY_LEN2, { N: SCRYPT_N2, r: SCRYPT_R2, p: SCRYPT_P2 });
      return [HASH_SCHEME2, SCRYPT_N2, SCRYPT_R2, SCRYPT_P2, salt.toString("base64"), key.toString("base64")].join("$");
    };
    var verifyPassword2 = (plain, stored) => {
      if (typeof stored !== "string" || !stored) return false;
      if (!isHashedPassword2(stored)) {
        try {
          const decoded = Buffer.from(stored, "base64").toString("utf-8");
          return safeEqual2(decoded, String(plain));
        } catch {
          return false;
        }
      }
      try {
        const parts = stored.split("$").filter((s) => s !== "");
        if (parts.length !== 6 || parts[0] !== HASH_SCHEME2) return false;
        const [, n, r, p, saltB64, hashB64] = parts;
        const salt = Buffer.from(saltB64, "base64");
        const expected = Buffer.from(hashB64, "base64");
        const actual = crypto2.scryptSync(String(plain), salt, expected.length, {
          N: Number(n),
          r: Number(r),
          p: Number(p)
        });
        return crypto2.timingSafeEqual(actual, expected);
      } catch {
        return false;
      }
    };
    var safeEqual2 = (a, b) => {
      const ba = Buffer.from(String(a), "utf-8");
      const bb = Buffer.from(String(b), "utf-8");
      if (ba.length !== bb.length) return false;
      return crypto2.timingSafeEqual(ba, bb);
    };
    var BIND_HOST2 = (() => {
      const raw = process.env.LITETASK_BIND_HOST;
      return typeof raw === "string" && raw.trim() ? raw.trim() : "127.0.0.1";
    })();
    var isLoopbackAddress = (addr) => {
      if (typeof addr !== "string") return false;
      let a = addr.trim();
      if (a.startsWith("::ffff:")) a = a.slice(7);
      if (a.startsWith("[") && a.endsWith("]")) a = a.slice(1, -1);
      if (a === "::1" || a === "0:0:0:0:0:0:0:1") return true;
      const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(a);
      return Boolean(m) && Number(m[1]) === 127;
    };
    var REACHABILITY2 = isLoopbackAddress(BIND_HOST2) ? "loopback" : "non-loopback";
    var SESSION_TTL_MS = (() => {
      const ms = Number(process.env.LITETASK_SESSION_TTL_MS);
      if (Number.isFinite(ms) && ms > 0) return ms;
      const h = Number(process.env.LITETASK_SESSION_TTL_HOURS);
      const hours = Number.isFinite(h) && h > 0 ? Math.min(24, Math.max(1, h)) : 8;
      return Math.round(hours * 36e5);
    })();
    var OPEN_RATE = (() => {
      const m = /^(\d+)\/(\d+)$/.exec(String(process.env.LITETASK_OPEN_RATE || "10/10").trim());
      const limit = m ? Math.max(1, Number(m[1])) : 10;
      const windowSec = m ? Math.max(1, Number(m[2])) : 10;
      return { limit, windowSec };
    })();
    var LEGACY_SITE_KEY = "securityModel";
    var DEFAULT_SITE_CONFIG_PATH = path2.join(__dirname, "..", "config", "site.json");
    var describeLegacySiteConfig = (site) => {
      if (!site || typeof site !== "object" || Array.isArray(site)) return [];
      return Object.prototype.hasOwnProperty.call(site, LEGACY_SITE_KEY) ? [LEGACY_SITE_KEY] : [];
    };
    var resolveSiteConfigPath = () => {
      const raw = process.env.LITETASK_SITE_CONFIG;
      if (typeof raw === "string" && raw.trim() && path2.isAbsolute(raw.trim())) {
        const candidate = path2.resolve(raw.trim());
        try {
          if (fs2.statSync(candidate).isFile()) {
            return { path: candidate, redirected: true };
          }
        } catch (_err) {
        }
      }
      return { path: DEFAULT_SITE_CONFIG_PATH, redirected: false };
    };
    var JSON_BODY_LIMIT2 = (() => {
      const mb = Number(process.env.LITETASK_JSON_LIMIT_MB || 16);
      return `${Number.isFinite(mb) && mb > 0 ? mb : 16}mb`;
    })();
    module2.exports = {
      DATA_DIR: DATA_DIR2,
      USERS_FILE: USERS_FILE2,
      PASSWORDLESS_LOCAL: PASSWORDLESS_LOCAL2,
      SHARED_LISTS_DIR: SHARED_LISTS_DIR2,
      CATEGORIES_FILE: CATEGORIES_FILE2,
      ARCHIVE_DIR: ARCHIVE_DIR2,
      BACKUP_DIR: BACKUP_DIR2,
      ARCHIVE_SNAPSHOT_DIR: ARCHIVE_SNAPSHOT_DIR2,
      MAX_ARCHIVE_SNAPSHOTS: MAX_ARCHIVE_SNAPSHOTS2,
      AUTO_ARCHIVE_ENABLED: AUTO_ARCHIVE_ENABLED2,
      AUTO_ARCHIVE_ENV_MIN: AUTO_ARCHIVE_ENV_MIN2,
      DEFAULT_AUTO_ARCHIVE_MIN_CLOSED: DEFAULT_AUTO_ARCHIVE_MIN_CLOSED2,
      DEFAULT_ARCHIVE_WARN_WITHIN: DEFAULT_ARCHIVE_WARN_WITHIN2,
      BIND_HOST: BIND_HOST2,
      REACHABILITY: REACHABILITY2,
      SESSION_TTL_MS,
      OPEN_RATE,
      isLoopbackAddress,
      LEGACY_SITE_KEY,
      DEFAULT_SITE_CONFIG_PATH,
      describeLegacySiteConfig,
      resolveSiteConfigPath,
      SCRYPT_N: SCRYPT_N2,
      SCRYPT_R: SCRYPT_R2,
      SCRYPT_P: SCRYPT_P2,
      KEY_LEN: KEY_LEN2,
      HASH_SCHEME: HASH_SCHEME2,
      HASH_PREFIX: HASH_PREFIX2,
      isHashedPassword: isHashedPassword2,
      hashPassword: hashPassword2,
      verifyPassword: verifyPassword2,
      safeEqual: safeEqual2,
      JSON_BODY_LIMIT: JSON_BODY_LIMIT2
    };
  }
});

// tests/_artifacts/_skill_build/lib/errors.js
var require_errors = __commonJS({
  "tests/_artifacts/_skill_build/lib/errors.js"(exports2, module2) {
    "use strict";
    var CODES = Object.freeze({
      INVALID_LIST_ID: "INVALID_LIST_ID",
      INVALID_STAMP: "INVALID_STAMP",
      INVALID_PATH: "INVALID_PATH",
      NOT_A_DIRECTORY: "NOT_A_DIRECTORY",
      AUTH_REQUIRED: "AUTH_REQUIRED",
      SESSION_INVALID: "SESSION_INVALID",
      UNKNOWN_ACTOR: "UNKNOWN_ACTOR",
      ADMIN_REQUIRED: "ADMIN_REQUIRED",
      NON_LOOPBACK_SOURCE: "NON_LOOPBACK_SOURCE",
      OPEN_ROOT_NOT_CONFIGURED: "OPEN_ROOT_NOT_CONFIGURED",
      PATH_OUTSIDE_ALLOWED_ROOT: "PATH_OUTSIDE_ALLOWED_ROOT",
      PATH_NOT_READABLE: "PATH_NOT_READABLE",
      LIST_NOT_FOUND: "LIST_NOT_FOUND",
      PATH_NOT_FOUND: "PATH_NOT_FOUND",
      INVALID_CREDENTIALS: "INVALID_CREDENTIALS",
      TOO_MANY_REQUESTS: "TOO_MANY_REQUESTS",
      LAUNCHER_UNAVAILABLE: "LAUNCHER_UNAVAILABLE",
      ARCHIVE_TXN_FAILED: "ARCHIVE_TXN_FAILED",
      ARCHIVE_TXN_MANUAL_RECOVERY: "ARCHIVE_TXN_MANUAL_RECOVERY",
      ARCHIVE_TXN_PENDING: "ARCHIVE_TXN_PENDING",
      INTERNAL: "INTERNAL"
    });
    var DEFAULT_MESSAGES = Object.freeze({
      INVALID_LIST_ID: "Invalid list identifier",
      INVALID_STAMP: "Invalid snapshot timestamp",
      INVALID_PATH: "Path must be an absolute path",
      NOT_A_DIRECTORY: "Target is not a directory",
      AUTH_REQUIRED: "Authentication required",
      SESSION_INVALID: "Invalid session",
      UNKNOWN_ACTOR: "Untrusted identity",
      ADMIN_REQUIRED: "Administrator access required",
      NON_LOOPBACK_SOURCE: "Loopback access only",
      OPEN_ROOT_NOT_CONFIGURED: "Allowed root not configured, feature disabled",
      PATH_OUTSIDE_ALLOWED_ROOT: "Path outside allowed root",
      PATH_NOT_READABLE: "Path is not readable",
      LIST_NOT_FOUND: "List not found",
      PATH_NOT_FOUND: "Path does not exist",
      INVALID_CREDENTIALS: "Invalid credentials",
      TOO_MANY_REQUESTS: "Too many requests",
      LAUNCHER_UNAVAILABLE: "System file manager unavailable",
      ARCHIVE_TXN_FAILED: "Archive transaction failed, rolled back to prior state",
      ARCHIVE_TXN_MANUAL_RECOVERY: "Archive transaction failed and rollback incomplete, manual recovery required",
      ARCHIVE_TXN_PENDING: "List has an unfinished transaction, manual recovery required",
      INTERNAL: "Internal error"
    });
    var isCode = (code) => Object.prototype.hasOwnProperty.call(CODES, code);
    var errorBody = (code, message, extra) => {
      const key = isCode(code) ? code : CODES.INTERNAL;
      const body = {
        error: typeof message === "string" && message.length > 0 ? message : DEFAULT_MESSAGES[key],
        code: key
      };
      if (extra && typeof extra === "object" && !Array.isArray(extra)) {
        for (const [k, v] of Object.entries(extra)) {
          if (k === "error" || k === "code") continue;
          body[k] = v;
        }
      }
      return body;
    };
    var sendError = (res, status2, code, message, extra) => {
      return res.status(status2).json(errorBody(code, message, extra));
    };
    module2.exports = {
      CODES,
      DEFAULT_MESSAGES,
      errorBody,
      sendError
    };
  }
});

// tests/_artifacts/_skill_build/lib/paths.js
var require_paths = __commonJS({
  "tests/_artifacts/_skill_build/lib/paths.js"(exports2, module2) {
    "use strict";
    var path2 = require("path");
    var fs2 = require("fs-extra");
    var cfg2 = require_config();
    var errors = require_errors();
    var { SHARED_LISTS_DIR: SHARED_LISTS_DIR2, ARCHIVE_DIR: ARCHIVE_DIR2, ARCHIVE_SNAPSHOT_DIR: ARCHIVE_SNAPSHOT_DIR2 } = cfg2;
    var LIST_ID_MAX_LEN = 32;
    var STAMP_MAX_LEN = 40;
    var LIST_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$/;
    var STAMP_RE = /^[0-9A-Za-z][0-9A-Za-z._:-]{0,39}$/;
    var validateListId = (raw) => {
      if (typeof raw !== "string") return { ok: false, reason: "not-string" };
      if (raw.length < 1 || raw.length > LIST_ID_MAX_LEN) return { ok: false, reason: "length" };
      if (!/^[\x21-\x7E]+$/.test(raw)) return { ok: false, reason: "non-ascii-or-control" };
      if (/[.\/%\\\s]/.test(raw)) return { ok: false, reason: "forbidden-char" };
      if (!LIST_ID_RE.test(raw)) return { ok: false, reason: "charset" };
      return { ok: true };
    };
    var validateStamp = (raw) => {
      if (typeof raw !== "string") return { ok: false, reason: "not-string" };
      if (raw.length < 1 || raw.length > STAMP_MAX_LEN) return { ok: false, reason: "length" };
      if (raw.includes("..")) return { ok: false, reason: "traversal" };
      if (/[\/\\%\s\x00]/.test(raw)) return { ok: false, reason: "separator" };
      if (!STAMP_RE.test(raw)) return { ok: false, reason: "charset" };
      return { ok: true };
    };
    var isInside = (rootAbs, candidateAbs) => {
      try {
        const rel = path2.relative(rootAbs, candidateAbs);
        return rel !== "" && rel !== ".." && !rel.startsWith(".." + path2.sep) && !path2.isAbsolute(rel);
      } catch (_err) {
        return false;
      }
    };
    var realpathNearest = async (p) => {
      let cur = path2.resolve(p);
      const missing = [];
      for (let i = 0; i < 64; i++) {
        try {
          const real = await fs2.realpath(cur);
          return missing.length ? path2.join(real, ...missing.slice().reverse()) : real;
        } catch (err) {
          if (err && err.code !== "ENOENT" && err.code !== "ENOTDIR") return null;
          const parent = path2.dirname(cur);
          if (parent === cur) return path2.resolve(p);
          missing.push(path2.basename(cur));
          cur = parent;
        }
      }
      return path2.resolve(p);
    };
    var belongsTo = async (rootAbs, fileAbs) => {
      try {
        const rootReal = await realpathNearest(rootAbs);
        const fileReal = await realpathNearest(fileAbs);
        if (!rootReal || !fileReal) return false;
        if (path2.resolve(fileReal) === path2.resolve(rootReal)) return true;
        return isInside(rootReal, fileReal);
      } catch (_err) {
        return false;
      }
    };
    var listFilePath = (listId) => {
      if (!validateListId(listId).ok) return null;
      return path2.join(SHARED_LISTS_DIR2, `${listId}.json`);
    };
    var archiveFilePath = (listId) => {
      if (!validateListId(listId).ok) return null;
      return path2.join(ARCHIVE_DIR2, `${listId}.json`);
    };
    var snapshotFilePrefix = (listId) => {
      if (!validateListId(listId).ok) return null;
      return `${listId}-`;
    };
    var snapshotFilePath = (listId, stamp) => {
      if (!validateListId(listId).ok || !validateStamp(stamp).ok) return null;
      const safeStamp = String(stamp).replace(/[:.]/g, "-");
      return path2.join(ARCHIVE_SNAPSHOT_DIR2, `${listId}-${safeStamp}.snapshot.json`);
    };
    var listIdParamGuard = (req, res, next) => {
      const raw = req.params && req.params.id;
      const v = validateListId(raw);
      if (!v.ok) return errors.sendError(res, 400, "INVALID_LIST_ID", "Invalid list identifier");
      req.listId = raw;
      return next();
    };
    var stampFieldGuard = (req, res, next) => {
      const raw = req.body && req.body.stamp;
      if (raw === void 0 || raw === null || raw === "") return next();
      const v = validateStamp(raw);
      if (!v.ok) return errors.sendError(res, 400, "INVALID_STAMP", "Invalid snapshot timestamp");
      req.stamp = raw;
      return next();
    };
    module2.exports = {
      LIST_ID_MAX_LEN,
      STAMP_MAX_LEN,
      LIST_ID_RE,
      STAMP_RE,
      validateListId,
      validateStamp,
      isInside,
      realpathNearest,
      belongsTo,
      listFilePath,
      archiveFilePath,
      snapshotFilePath,
      snapshotFilePrefix,
      listIdParamGuard,
      stampFieldGuard
    };
  }
});

// tests/_artifacts/_skill_build/lib/util.js
var require_util = __commonJS({
  "tests/_artifacts/_skill_build/lib/util.js"(exports2, module2) {
    "use strict";
    var crypto2 = require("crypto");
    var fs2 = require("fs-extra");
    var path2 = require("path");
    var { USERS_FILE: USERS_FILE2 } = require_config();
    var contentRev2 = (items) => crypto2.createHash("sha256").update(JSON.stringify(items || [])).digest("hex").slice(0, 16);
    var lockQueue = /* @__PURE__ */ new Map();
    var withLock2 = async (key, fn) => {
      const prev = lockQueue.get(key) || Promise.resolve();
      let release;
      const gate = new Promise((resolve) => {
        release = resolve;
      });
      lockQueue.set(key, prev.then(() => gate));
      try {
        await prev;
      } catch (_e) {
      }
      try {
        return await fn();
      } finally {
        release();
      }
    };
    var atomicWriteJson2 = async (filePath, data) => {
      const tmp = `${filePath}.tmp-${process.pid}-${Date.now()}`;
      await fs2.writeJson(tmp, data, { spaces: 2 });
      let lastErr = null;
      for (let attempt = 0; attempt < 6; attempt++) {
        try {
          await fs2.move(tmp, filePath, { overwrite: true });
          return true;
        } catch (err) {
          lastErr = err;
          await new Promise((r) => setTimeout(r, 150 * (attempt + 1)));
        }
      }
      await fs2.writeJson(filePath, data, { spaces: 2 });
      await fs2.remove(tmp).catch(() => {
      });
      if (lastErr) console.warn(`[LiteTask] Atomic write fell back for ${path2.basename(filePath)}: ${lastErr.code || lastErr.message}`);
      return true;
    };
    var DIFF_FIELD_LABELS2 = {
      title: "Title",
      status: "Status",
      isDone: "Done",
      priority: "Priority",
      dueDate: "Due Date",
      comment: "Comment",
      blockedReason: "Blocked Reason",
      localDirectory: "Primary Path",
      localDirectories: "Linked Paths",
      relatesTo: "Relations",
      createdByAgent: "Creator (Agent)",
      createdBy: "Creator",
      assignedTo: "Assigned To"
    };
    var DIFF_IGNORE_KEYS2 = /* @__PURE__ */ new Set([
      "rev",
      "updatedAt",
      "updatedBy",
      "statusHistory",
      "archivedAt",
      "archivedFrom",
      "createdAt",
      "createdById",
      "closedAt",
      "closedBy",
      "closedById",
      "itemId",
      "subTasks"
    ]);
    var normVal2 = (v) => {
      if (v === void 0) return null;
      if (Array.isArray(v)) return v.map(normVal2);
      if (v && typeof v === "object") {
        return Object.keys(v).sort().reduce((o, k) => {
          o[k] = normVal2(v[k]);
          return o;
        }, {});
      }
      return v;
    };
    var stableEqual2 = (a, b) => JSON.stringify(normVal2(a)) === JSON.stringify(normVal2(b));
    var flattenItems2 = (arr, out = /* @__PURE__ */ new Map(), parentId = null) => {
      for (const it of Array.isArray(arr) ? arr : []) {
        if (!it || typeof it !== "object" || !it.itemId) continue;
        const id = String(it.itemId);
        if (out.has(id)) continue;
        out.set(id, { item: it, parentId });
        if (Array.isArray(it.subTasks) && it.subTasks.length) flattenItems2(it.subTasks, out, id);
      }
      return out;
    };
    var diffItems2 = (mineArr, serverArr) => {
      const mine = flattenItems2(mineArr);
      const server2 = flattenItems2(serverArr);
      const added = [];
      const removed = [];
      const changed = [];
      for (const [id, m] of mine) {
        if (!server2.has(id)) added.push({ itemId: id, title: m.item.title || "", parentId: m.parentId });
      }
      for (const [id, s] of server2) {
        if (!mine.has(id)) removed.push({ itemId: id, title: s.item.title || "", parentId: s.parentId });
      }
      for (const [id, m] of mine) {
        const s = server2.get(id);
        if (!s) continue;
        const fields = [];
        const keys = /* @__PURE__ */ new Set([...Object.keys(m.item), ...Object.keys(s.item)]);
        for (const k of keys) {
          if (DIFF_IGNORE_KEYS2.has(k)) continue;
          if (stableEqual2(m.item[k], s.item[k])) continue;
          fields.push({
            field: k,
            label: DIFF_FIELD_LABELS2[k] || k,
            mine: m.item[k] === void 0 ? null : m.item[k],
            server: s.item[k] === void 0 ? null : s.item[k]
          });
        }
        if (fields.length) {
          changed.push({ itemId: id, title: m.item.title || s.item.title || "", fields });
        }
      }
      return {
        added,
        removed,
        changed,
        counts: {
          added: added.length,
          removed: removed.length,
          changed: changed.length,
          fields: changed.reduce((n, c) => n + c.fields.length, 0)
        }
      };
    };
    var stampNow2 = () => {
      const d = /* @__PURE__ */ new Date();
      const pad = (n) => String(n).padStart(2, "0");
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    };
    var isUserAdminOf = (user) => Boolean(user && (user.isAdmin || user.username === "admin" || user.userId === "user_admin"));
    var adminFlags = (users) => {
      const set = /* @__PURE__ */ new Set();
      for (const u of Array.isArray(users) ? users : []) {
        if (u && u.userId && isUserAdminOf(u)) set.add(String(u.userId));
      }
      return set;
    };
    var findUserById = async (userId) => {
      if (!userId) return null;
      try {
        const users = await fs2.readJson(USERS_FILE2);
        return users.find((x) => x.userId === userId) || null;
      } catch {
        return null;
      }
    };
    var isUserAdmin2 = async (userId) => isUserAdminOf(await findUserById(userId));
    var usernameOf2 = async (userId) => {
      if (!userId) return null;
      try {
        const users = await fs2.readJson(USERS_FILE2);
        const u = users.find((x) => x.userId === userId);
        return u ? u.username || null : null;
      } catch {
        return null;
      }
    };
    module2.exports = {
      contentRev: contentRev2,
      withLock: withLock2,
      atomicWriteJson: atomicWriteJson2,
      DIFF_FIELD_LABELS: DIFF_FIELD_LABELS2,
      DIFF_IGNORE_KEYS: DIFF_IGNORE_KEYS2,
      normVal: normVal2,
      stableEqual: stableEqual2,
      flattenItems: flattenItems2,
      diffItems: diffItems2,
      stampNow: stampNow2,
      isUserAdmin: isUserAdmin2,
      isUserAdminOf,
      adminFlags,
      findUserById,
      usernameOf: usernameOf2,
      lockQueue
    };
  }
});

// tests/_artifacts/_skill_build/lib/session.js
var require_session = __commonJS({
  "tests/_artifacts/_skill_build/lib/session.js"(exports2, module2) {
    "use strict";
    var crypto2 = require("crypto");
    var cfg2 = require_config();
    var SESSION_COOKIE = "lt_session";
    var SESSION_TTL_MS = cfg2.SESSION_TTL_MS;
    var rawSecret = process.env.LITETASK_SESSION_SECRET;
    var SECRET = typeof rawSecret === "string" && rawSecret.length >= 16 ? rawSecret : crypto2.randomBytes(32);
    var sessions = /* @__PURE__ */ new Map();
    var b64url = (buf) => buf.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
    var sign = (sid, exp) => b64url(
      crypto2.createHmac("sha256", SECRET).update(`${sid}.${exp}`).digest()
    );
    var safeEqual2 = (a, b) => {
      const ba = Buffer.from(String(a), "utf8");
      const bb = Buffer.from(String(b), "utf8");
      if (ba.length !== bb.length) return false;
      try {
        return crypto2.timingSafeEqual(ba, bb);
      } catch (_e) {
        return false;
      }
    };
    var parseCookies = (header) => {
      const out = {};
      if (typeof header !== "string" || !header) return out;
      for (const part of header.split(";")) {
        const i = part.indexOf("=");
        if (i < 0) continue;
        const k = part.slice(0, i).trim();
        const v = part.slice(i + 1).trim();
        if (k) out[k] = v;
      }
      return out;
    };
    var buildSetCookie = (value, opts) => {
      const o = opts || {};
      const maxAge = Number.isFinite(o.maxAgeSec) ? Math.max(0, Math.floor(o.maxAgeSec)) : Math.floor(SESSION_TTL_MS / 1e3);
      let cookie = `${SESSION_COOKIE}=${value}; HttpOnly; SameSite=Lax; Path=/; Max-Age=${maxAge}`;
      if (o.secure) cookie += "; Secure";
      return cookie;
    };
    var buildClearCookie = () => `${SESSION_COOKIE}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0`;
    var issueSession = (userId, opts) => {
      const o = opts || {};
      const now = Number.isFinite(o.now) ? o.now : Date.now();
      const ttlMs = Number.isFinite(o.ttlMs) && o.ttlMs > 0 ? o.ttlMs : SESSION_TTL_MS;
      const sid = b64url(crypto2.randomBytes(32));
      const exp = now + ttlMs;
      sessions.set(sid, { userId, exp });
      const value = `${sid}.${exp}.${sign(sid, exp)}`;
      return {
        sid,
        value,
        exp,
        expiresAt: exp,
        cookie: buildSetCookie(value, { maxAgeSec: Math.floor(ttlMs / 1e3), secure: o.secure })
      };
    };
    var verifySession = (cookieValue, opts) => {
      if (typeof cookieValue !== "string" || !cookieValue) return { ok: false, reason: "missing" };
      const parts = cookieValue.split(".");
      if (parts.length !== 3) return { ok: false, reason: "malformed" };
      const [sid, expStr, sig] = parts;
      const exp = Number(expStr);
      if (!sid || !Number.isFinite(exp)) return { ok: false, reason: "malformed" };
      if (!safeEqual2(sig, sign(sid, exp))) return { ok: false, reason: "bad-signature" };
      const rec = sessions.get(sid);
      if (!rec) return { ok: false, reason: "revoked" };
      if (rec.exp !== exp) return { ok: false, reason: "bad-signature" };
      const now = opts && Number.isFinite(opts.now) ? opts.now : Date.now();
      if (exp <= now) {
        sessions.delete(sid);
        return { ok: false, reason: "expired" };
      }
      return { ok: true, sid, userId: rec.userId, exp };
    };
    var destroySession = (sid) => {
      if (sid) sessions.delete(sid);
    };
    var destroySessionsForUser = (userId) => {
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
    var activeSessionCount = () => sessions.size;
    module2.exports = {
      SESSION_COOKIE,
      SESSION_TTL_MS,
      parseCookies,
      issueSession,
      verifySession,
      destroySession,
      destroySessionsForUser,
      activeSessionCount,
      buildSetCookie,
      buildClearCookie
    };
  }
});

// tests/_artifacts/_skill_build/lib/logrotate.js
var require_logrotate = __commonJS({
  "tests/_artifacts/_skill_build/lib/logrotate.js"(exports2, module2) {
    "use strict";
    var fs2 = require("fs-extra");
    var path2 = require("path");
    var os2 = require("os");
    var cfg2 = require_config();
    var LOG_DIR2 = process.env.LITETASK_LOG_DIR ? path2.resolve(process.env.LITETASK_LOG_DIR) : path2.join(os2.tmpdir(), "litetask-logs");
    var LOG_FILE2 = path2.join(LOG_DIR2, "access.log");
    var LOG_MAX_BYTES = Math.max(1, Number(process.env.LITETASK_LOG_MAX_BYTES || 1024 * 1024));
    var LOG_KEEP = Math.max(1, Number(process.env.LITETASK_LOG_KEEP || 3));
    fs2.ensureDirSync(LOG_DIR2);
    var rotateLogIfNeeded = async () => {
      try {
        const st = await fs2.stat(LOG_FILE2);
        if (st.size < LOG_MAX_BYTES) return;
      } catch (err) {
        return;
      }
      for (let i = LOG_KEEP; i >= 1; i--) {
        const from = i === 1 ? LOG_FILE2 : `${LOG_FILE2}.${i - 1}`;
        const to = `${LOG_FILE2}.${i}`;
        if (!await fs2.pathExists(from)) continue;
        if (i === LOG_KEEP) await fs2.remove(to);
        await fs2.move(from, to, { overwrite: true });
      }
    };
    var logChain = Promise.resolve();
    var writeLogLine = (line) => {
      logChain = logChain.then(async () => {
        try {
          await rotateLogIfNeeded();
          await fs2.appendFile(LOG_FILE2, line + "\n");
        } catch (err) {
          console.warn("[LiteTask] request log write failed:", err.message);
        }
      });
      return logChain;
    };
    module2.exports = { LOG_DIR: LOG_DIR2, LOG_FILE: LOG_FILE2, LOG_MAX_BYTES, LOG_KEEP, rotateLogIfNeeded, writeLogLine };
  }
});

// tests/_artifacts/_skill_build/lib/audit.js
var require_audit = __commonJS({
  "tests/_artifacts/_skill_build/lib/audit.js"(exports2, module2) {
    "use strict";
    var fs2 = require("fs-extra");
    var path2 = require("path");
    var cfg2 = require_config();
    var { LOG_DIR: LOG_DIR2 } = require_logrotate();
    var AUDIT_FILE2 = process.env.LITETASK_AUDIT_FILE ? path2.resolve(process.env.LITETASK_AUDIT_FILE) : path2.join(LOG_DIR2, "audit.log");
    var AUDIT_MAX_BYTES = Math.max(1, Number(process.env.LITETASK_AUDIT_MAX_BYTES || 1024 * 1024));
    var AUDIT_KEEP = Math.max(1, Number(process.env.LITETASK_AUDIT_KEEP || 3));
    var AUDIT_SECRET_KEYS = /* @__PURE__ */ new Set([
      "password",
      "newpassword",
      "oldpassword",
      "currentpassword",
      "confirmpassword",
      "pwd",
      "pass",
      "token",
      "accesstoken",
      "refreshtoken",
      "idtoken",
      "secret",
      "clientsecret",
      "cookie",
      "authorization",
      "apikey",
      "credential",
      "credentials",
      "sessionid"
    ]);
    var summarizeForAudit = (value, depth) => {
      depth = depth || 0;
      if (depth > 3) return "[deep]";
      if (Array.isArray(value)) return { len: value.length };
      if (value && typeof value === "object") {
        const out = {};
        for (const k of Object.keys(value)) {
          out[k] = AUDIT_SECRET_KEYS.has(k.toLowerCase()) ? "[redacted]" : summarizeForAudit(value[k], depth + 1);
        }
        return out;
      }
      if (typeof value === "string") {
        return value.length > 200 ? value.slice(0, 200) + "..." : value;
      }
      return value;
    };
    var auditChain = Promise.resolve();
    var writeAudit2 = (entry) => {
      const rec = {
        ts: (/* @__PURE__ */ new Date()).toISOString(),
        actor: entry.actor || null,
        action: entry.action,
        listId: entry.listId === void 0 ? null : entry.listId,
        outcome: entry.outcome === void 0 ? "ok" : entry.outcome,
        confirmed: entry.confirmed === void 0 ? null : entry.confirmed,
        params: summarizeForAudit(entry.params || {})
      };
      if (entry.note) rec.note = String(entry.note).slice(0, 300);
      auditChain = auditChain.then(async () => {
        try {
          await fs2.ensureDir(path2.dirname(AUDIT_FILE2));
          const st = await fs2.stat(AUDIT_FILE2).catch(() => null);
          if (st && st.size > AUDIT_MAX_BYTES) {
            for (let i = AUDIT_KEEP; i >= 1; i--) {
              const from = i === 1 ? AUDIT_FILE2 : `${AUDIT_FILE2}.${i - 1}`;
              const to = `${AUDIT_FILE2}.${i}`;
              if (await fs2.pathExists(from)) await fs2.move(from, to, { overwrite: true });
            }
          }
          await fs2.appendFile(AUDIT_FILE2, JSON.stringify(rec) + "\n");
        } catch (err) {
          console.warn("[LiteTask] audit write failed:", err.message);
        }
      });
      return auditChain;
    };
    module2.exports = { AUDIT_FILE: AUDIT_FILE2, AUDIT_MAX_BYTES, AUDIT_KEEP, summarizeForAudit, writeAudit: writeAudit2 };
  }
});

// tests/_artifacts/_skill_build/lib/guard.js
var require_guard = __commonJS({
  "tests/_artifacts/_skill_build/lib/guard.js"(exports2, module2) {
    "use strict";
    var cfg2 = require_config();
    var util2 = require_util();
    var errors = require_errors();
    var session = require_session();
    var { writeAudit: writeAudit2 } = require_audit();
    var { PASSWORDLESS_LOCAL: PASSWORDLESS_LOCAL2, REACHABILITY: REACHABILITY2, isLoopbackAddress } = cfg2;
    var PUBLIC_API_PATHS = Object.freeze({
      "/api/login": true,
      "/api/logout": true,
      "/api/config": true,
      "/api/health": true
    });
    var anonymousActor = (mode) => Object.freeze({
      mode,
      userId: null,
      username: null,
      isAdmin: false,
      authenticated: false,
      declared: false,
      anonymous: true,
      source: "none"
    });
    var declaredActor = (mode, user, source) => Object.freeze({
      mode,
      userId: user.userId,
      username: user.username,
      isAdmin: util2.isUserAdminOf(user),
      authenticated: source === "session",
      declared: source === "declared",
      anonymous: false,
      source
    });
    var loopbackGuard = (req, res, next) => {
      if (REACHABILITY2 === "loopback") {
        const addr = req.socket && req.socket.remoteAddress;
        if (!isLoopbackAddress(addr)) {
          return errors.sendError(res, 403, "NON_LOOPBACK_SOURCE", "Loopback access only");
        }
      }
      return next();
    };
    var declaredIdOf = (req) => {
      const q = req.query || {};
      const b = req.body && typeof req.body === "object" ? req.body : {};
      const raw = q.userId || b.userId || b.adminUserId || q.adminUserId;
      return raw === void 0 || raw === null || raw === "" ? null : String(raw);
    };
    var resolveActor = async (req, allowAnonymous) => {
      if (!PASSWORDLESS_LOCAL2) {
        const cookies = session.parseCookies(req.headers && req.headers.cookie);
        const v = session.verifySession(cookies[session.SESSION_COOKIE]);
        if (!v.ok) {
          if (allowAnonymous) return { ok: true, actor: anonymousActor("shared") };
          return { ok: false, status: 401, code: "AUTH_REQUIRED", message: "Authentication required" };
        }
        const user2 = await util2.findUserById(v.userId);
        if (!user2) {
          session.destroySession(v.sid);
          if (allowAnonymous) return { ok: true, actor: anonymousActor("shared") };
          return { ok: false, status: 401, code: "AUTH_REQUIRED", message: "Authentication required" };
        }
        return { ok: true, actor: declaredActor("shared", user2, "session") };
      }
      const raw = declaredIdOf(req);
      if (!raw) return { ok: true, actor: anonymousActor("local") };
      const user = await util2.findUserById(raw);
      if (!user) return { ok: false, status: 403, code: "UNKNOWN_ACTOR", message: "Untrusted identity" };
      return { ok: true, actor: declaredActor("local", user, "declared") };
    };
    var reject = async (res, status2, code, note) => {
      try {
        await writeAudit2({ actor: null, action: "reject", outcome: "rejected", note: note || code });
      } catch (_e) {
      }
      return errors.sendError(res, status2, code, void 0);
    };
    var createAuthGate = () => async (req, res, next) => {
      try {
        const pathOnly = String(req.originalUrl || req.url || "").split("?")[0];
        if (req.method === "OPTIONS") {
          req.actor = anonymousActor(PASSWORDLESS_LOCAL2 ? "local" : "shared");
          return next();
        }
        const isPublic = !!PUBLIC_API_PATHS[pathOnly];
        const r = await resolveActor(req, isPublic);
        if (!r.ok) return reject(res, r.status, r.code, r.code.toLowerCase());
        req.actor = r.actor;
        return next();
      } catch (_err) {
        return errors.sendError(res, 500, "INTERNAL", "Internal error");
      }
    };
    var requireAdmin = (actor) => Boolean(actor && actor.isAdmin === true);
    module2.exports = {
      isLoopbackAddress,
      loopbackGuard,
      createAuthGate,
      resolveActor,
      requireAdmin,
      PUBLIC_API_PATHS,
      anonymousActor
    };
  }
});

// tests/_artifacts/_skill_build/lib/open_folder.js
var require_open_folder = __commonJS({
  "tests/_artifacts/_skill_build/lib/open_folder.js"(exports2, module2) {
    "use strict";
    var fs2 = require("fs-extra");
    var path2 = require("path");
    var { spawn } = require("child_process");
    var paths2 = require_paths();
    var errors = require_errors();
    var MAX_PATH_LEN = 260;
    var resolveAllowedRoots = (siteRoot) => {
      const raw = process.env.LITETASK_OPEN_ROOT || process.env.LITETASK_PROJECT_ROOT || (typeof siteRoot === "string" ? siteRoot : "");
      if (!raw || !String(raw).trim()) return { configured: false, roots: [] };
      const seen = /* @__PURE__ */ new Set();
      const roots = [];
      for (const part of String(raw).split(path2.delimiter)) {
        const t = part.trim();
        if (!t) continue;
        const abs = path2.resolve(t);
        if (seen.has(abs)) continue;
        seen.add(abs);
        try {
          if (fs2.statSync(abs).isDirectory()) roots.push(abs);
        } catch (_err) {
        }
      }
      return { configured: roots.length > 0, roots };
    };
    var invalid = (code, status2, message) => ({ ok: false, code, status: status2, message });
    var validateFolderPath = async (raw, roots) => {
      if (typeof raw !== "string" || !raw || raw.length > MAX_PATH_LEN || raw.includes("\0")) {
        return invalid("INVALID_PATH", 400, "Path must be an absolute path");
      }
      if (/^[A-Za-z][A-Za-z0-9+.-]*:\/\//.test(raw)) {
        return invalid("INVALID_PATH", 400, "URL is not a local directory path");
      }
      if (!path2.isAbsolute(raw) || raw.startsWith("\\\\") || raw.startsWith("//")) {
        return invalid("INVALID_PATH", 400, "Path must be an absolute path");
      }
      if (!Array.isArray(roots) || roots.length === 0) {
        return invalid("OPEN_ROOT_NOT_CONFIGURED", 403, "Allowed root not configured, feature disabled");
      }
      const abs = path2.resolve(raw);
      let root = null;
      for (const r of roots) {
        const rAbs = path2.resolve(r);
        if (abs === rAbs || await paths2.belongsTo(rAbs, abs)) {
          root = rAbs;
          break;
        }
      }
      if (!root) return invalid("PATH_OUTSIDE_ALLOWED_ROOT", 403, "Path outside allowed root");
      let st = null;
      try {
        st = await fs2.stat(abs);
      } catch (_err) {
        st = null;
      }
      if (!st) return invalid("PATH_NOT_FOUND", 404, "Path does not exist");
      if (!st.isDirectory()) return invalid("NOT_A_DIRECTORY", 400, "Target is not a directory");
      try {
        await fs2.access(abs, fs2.constants.R_OK);
      } catch (_err) {
        return invalid("PATH_NOT_READABLE", 403, "Path is not readable");
      }
      return { ok: true, abs, rel: path2.relative(root, abs), root };
    };
    var launcherForPlatform = (platform, override) => {
      if (override) return { cmd: override, argsFor: (p) => [p] };
      if (platform === "win32") {
        const sysRoot = process.env.SystemRoot || "C:\\Windows";
        return { cmd: path2.join(sysRoot, "explorer.exe"), argsFor: (p) => [p] };
      }
      if (platform === "darwin") return { cmd: "open", argsFor: (p) => [p] };
      return { cmd: "xdg-open", argsFor: (p) => [p] };
    };
    var commandCache = { cmd: null, present: false, at: 0 };
    var commandExists = (cmd) => {
      if (!cmd) return false;
      const now = Date.now();
      if (commandCache.cmd === cmd && now - commandCache.at < 1e4) return commandCache.present;
      let present = false;
      if (path2.isAbsolute(cmd) || cmd.includes("/") || cmd.includes("\\")) {
        present = fs2.existsSync(cmd);
      } else {
        const ext = process.platform === "win32" ? (process.env.PATHEXT || ".EXE;.CMD;.BAT;.COM").split(";") : [""];
        for (const dir of String(process.env.PATH || "").split(path2.delimiter)) {
          if (!dir) continue;
          for (const e of ext) {
            if (fs2.existsSync(path2.join(dir, cmd + e))) {
              present = true;
              break;
            }
          }
          if (present) break;
        }
      }
      commandCache = { cmd, present, at: now };
      return present;
    };
    var spawnLauncher = (cmd, args) => {
      try {
        const child = spawn(cmd, args, {
          shell: false,
          detached: true,
          stdio: "ignore",
          windowsHide: true
        });
        child.on("error", (err) => {
          console.warn("[LiteTask] open-folder launcher failed:", err.code || err.message);
        });
        child.unref();
        return { ok: true, pid: child.pid };
      } catch (err) {
        return { ok: false, error: err && err.message };
      }
    };
    var rateBuckets = /* @__PURE__ */ new Map();
    var parseRate = (raw) => {
      const m = /^(\d+)\/(\d+)$/.exec(String(raw || "10/10").trim());
      if (!m) return { limit: 10, windowMs: 1e4 };
      return {
        limit: Math.max(1, Number(m[1])),
        windowMs: Math.max(1, Number(m[2])) * 1e3
      };
    };
    var allowRate = (key, rate) => {
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
    var register = (app2, deps) => {
      const roots = deps && deps.roots || [];
      const writeAudit2 = deps && deps.writeAudit;
      const rate = parseRate(process.env.LITETASK_OPEN_RATE);
      const launcherOverride = process.env.LITETASK_OPEN_LAUNCHER;
      app2.post("/api/open-folder", async (req, res) => {
        const actor = req.actor || {};
        const actorId = actor.userId || null;
        const deny = async (code, status2, message, extra) => {
          if (typeof writeAudit2 === "function") {
            try {
              await writeAudit2({
                actor: actorId,
                action: "open-folder",
                outcome: "rejected",
                params: {},
                note: code
              });
            } catch (_e) {
            }
          }
          return errors.sendError(res, status2, code, message, extra);
        };
        const raw = req.body && req.body.folderPath;
        const v = await validateFolderPath(raw, roots);
        if (!v.ok) return deny(v.code, v.status, v.message);
        const l = launcherForPlatform(process.platform, launcherOverride);
        if (!commandExists(l.cmd)) {
          return deny(
            "LAUNCHER_UNAVAILABLE",
            503,
            "System file manager unavailable",
            { launcher: path2.basename(l.cmd) }
          );
        }
        if (!allowRate(actorId || "anonymous", rate)) {
          return deny("TOO_MANY_REQUESTS", 429, "Too many requests");
        }
        const r = spawnLauncher(l.cmd, l.argsFor(v.abs));
        if (!r.ok) return deny("LAUNCHER_UNAVAILABLE", 503, "System file manager unavailable");
        res.json({ success: true, path: v.rel });
        if (typeof writeAudit2 === "function") {
          void writeAudit2({
            actor: actorId,
            action: "open-folder",
            outcome: "ok",
            params: { rootIndex: roots.indexOf(v.root), relPath: v.rel },
            note: "opened"
          });
        }
      });
    };
    module2.exports = {
      resolveAllowedRoots,
      validateFolderPath,
      launcherForPlatform,
      commandExists,
      spawnLauncher,
      register
    };
  }
});

// tests/_artifacts/_skill_build/lib/origin_policy.js
var require_origin_policy = __commonJS({
  "tests/_artifacts/_skill_build/lib/origin_policy.js"(exports2, module2) {
    "use strict";
    var wildcard = /[*]/;
    var normalizeOrigin = (value) => {
      if (typeof value !== "string" || !value.trim()) return { ok: false, reason: "not-string" };
      let u;
      try {
        u = new URL(value.trim());
      } catch (_err) {
        return { ok: false, reason: "parse" };
      }
      const scheme = u.protocol.replace(":", "").toLowerCase();
      if (scheme !== "http" && scheme !== "https") return { ok: false, reason: "scheme" };
      if (u.username || u.password) return { ok: false, reason: "credentials" };
      if (u.pathname !== "/" && u.pathname !== "") return { ok: false, reason: "path" };
      if (u.search || u.hash) return { ok: false, reason: "query" };
      if (wildcard.test(u.hostname)) return { ok: false, reason: "wildcard" };
      return {
        ok: true,
        origin: u.origin.toLowerCase(),
        scheme,
        host: u.hostname.toLowerCase(),
        port: u.port || ""
      };
    };
    var parseAllowList = (raw) => {
      if (raw === void 0 || raw === null || String(raw).trim() === "") {
        return { origins: [], invalid: [], empty: true };
      }
      const parts = String(raw).split(",").map((s) => s.trim());
      if (parts.length === 1 && parts[0] === "") {
        return { origins: [], invalid: [], empty: true };
      }
      const invalid = [];
      const origins = [];
      for (const part of parts) {
        if (!part || wildcard.test(part)) {
          invalid.push(part || "*");
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
    var isLoopbackHostname = (hostname) => {
      if (typeof hostname !== "string") return false;
      let h = hostname.trim().toLowerCase();
      if (h.startsWith("[") && h.endsWith("]")) h = h.slice(1, -1);
      if (h === "localhost" || h === "::1" || h === "0:0:0:0:0:0:0:1") return true;
      if (h.startsWith("::ffff:")) h = h.slice(7);
      const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(h);
      return Boolean(m) && Number(m[1]) === 127;
    };
    var splitHost = (header) => {
      const raw = String(header || "");
      if (raw.startsWith("[")) {
        const end = raw.indexOf("]");
        if (end > 0) return { host: raw.slice(1, end), port: raw.slice(end + 2) };
      }
      const i = raw.lastIndexOf(":");
      if (i > 0) return { host: raw.slice(0, i), port: raw.slice(i + 1) };
      return { host: raw, port: "" };
    };
    var classifyRequest = (req, allowOrigins) => {
      const headers = req && req.headers || {};
      const originRaw = headers.origin || headers.Origin;
      if (!originRaw) return "absent";
      const n = normalizeOrigin(String(originRaw));
      if (!n.ok) return "cross-origin";
      const host = splitHost(headers.host || headers.Host);
      const defaultPort = n.scheme === "http" ? "80" : "443";
      const originPort = n.port || defaultPort;
      const hostPort = host.port || defaultPort;
      const loopback = isLoopbackHostname(n.host) && isLoopbackHostname(host.host);
      if (n.scheme === "http" && loopback && String(originPort) === String(hostPort)) {
        return "same-origin";
      }
      const allow = allowOrigins && Array.isArray(allowOrigins.origins) ? allowOrigins.origins : [];
      if (allow.includes(n.origin)) return "allowlisted";
      return "cross-origin";
    };
    module2.exports = {
      normalizeOrigin,
      parseAllowList,
      isLoopbackHostname,
      classifyRequest
    };
  }
});

// tests/_artifacts/_skill_build/lib/socket_gate.js
var require_socket_gate = __commonJS({
  "tests/_artifacts/_skill_build/lib/socket_gate.js"(exports2, module2) {
    "use strict";
    var cfg2 = require_config();
    var session = require_session();
    var util2 = require_util();
    var audit = require_audit();
    var { parseAllowList, classifyRequest } = require_origin_policy();
    var rejectAudit = (note) => {
      try {
        void audit.writeAudit({
          actor: null,
          action: "reject",
          outcome: "rejected",
          params: {},
          note
        });
      } catch (_err) {
      }
    };
    var installSocketGate = (io2, options) => {
      const opts = options || {};
      const allowOrigins = opts.allowOrigins || parseAllowList(process.env.LITETASK_SOCKET_ALLOW_ORIGINS);
      io2.engine.use((req, res, next) => {
        let verdict;
        try {
          verdict = classifyRequest(req, allowOrigins);
        } catch (_err) {
          verdict = "cross-origin";
        }
        if (verdict === "cross-origin") {
          rejectAudit("ORIGIN_FORBIDDEN");
          try {
            res.writeHead(403, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ code: "ORIGIN_FORBIDDEN", message: "Origin not allowed" }));
          } catch (_err) {
          }
          return;
        }
        return next();
      });
      io2.use(async (socket, next) => {
        try {
          if (cfg2.PASSWORDLESS_LOCAL) {
            socket.data.actor = { mode: "local", userId: null, source: "anonymous" };
            return next();
          }
          const req = socket.request || {};
          const cookies = session.parseCookies((req.headers || {}).cookie);
          const v = session.verifySession(cookies[session.SESSION_COOKIE]);
          if (!v.ok) {
            rejectAudit("AUTH_REQUIRED");
            return next(new Error("AUTH_REQUIRED"));
          }
          const user = await util2.findUserById(v.userId);
          if (!user) {
            session.destroySession(v.sid);
            rejectAudit("AUTH_REQUIRED");
            return next(new Error("AUTH_REQUIRED"));
          }
          socket.data.actor = { mode: "shared", userId: user.userId, source: "session" };
          return next();
        } catch (_err) {
          rejectAudit("AUTH_REQUIRED");
          return next(new Error("AUTH_REQUIRED"));
        }
      });
      return allowOrigins;
    };
    module2.exports = { installSocketGate };
  }
});

// tests/_artifacts/_skill_build/lib/backup.js
var require_backup = __commonJS({
  "tests/_artifacts/_skill_build/lib/backup.js"(exports2, module2) {
    "use strict";
    var fs2 = require("fs-extra");
    var path2 = require("path");
    var os2 = require("os");
    var cfg2 = require_config();
    var { DATA_DIR: DATA_DIR2, BACKUP_DIR: BACKUP_DIR2 } = cfg2;
    var PROJECT_ROOT = __dirname;
    var OFF_VALUES = ["0", "off", "false", "none"];
    var realpathNearestSync = (p) => {
      let cur = path2.resolve(p);
      const missing = [];
      for (let i = 0; i < 64; i++) {
        try {
          const real = fs2.realpathSync(cur);
          return missing.length ? path2.join(real, ...missing.slice().reverse()) : real;
        } catch (err) {
          if (err && err.code !== "ENOENT" && err.code !== "ENOTDIR") return path2.resolve(p);
          const parent = path2.dirname(cur);
          if (parent === cur) return path2.resolve(p);
          missing.push(path2.basename(cur));
          cur = parent;
        }
      }
      return path2.resolve(p);
    };
    var insideOrEqual = (root, candidate) => {
      try {
        const rootReal = realpathNearestSync(root);
        const candidateReal = realpathNearestSync(candidate);
        const rel = path2.relative(rootReal, candidateReal);
        return rel === "" || rel !== ".." && !rel.startsWith(".." + path2.sep) && !path2.isAbsolute(rel);
      } catch (_err) {
        return false;
      }
    };
    var describeMirrorConfig = (raw) => {
      const value = raw === void 0 ? process.env.LITETASK_BACKUP_MIRROR : raw;
      if (value === void 0 || value === null || String(value).trim() === "") {
        return { enabled: false, dir: null, reason: "unset" };
      }
      const trimmed = String(value).trim();
      if (OFF_VALUES.includes(trimmed.toLowerCase())) {
        return { enabled: false, dir: null, reason: "explicit-off" };
      }
      if (!path2.isAbsolute(trimmed)) {
        return { enabled: false, dir: null, reason: "not-absolute" };
      }
      const candidate = path2.resolve(trimmed);
      if (insideOrEqual(PROJECT_ROOT, candidate) || insideOrEqual(DATA_DIR2, candidate) || insideOrEqual(BACKUP_DIR2, candidate)) {
        return { enabled: false, dir: null, reason: "inside-project" };
      }
      if (process.platform === "win32" && !insideOrEqual(os2.homedir(), candidate)) {
        return { enabled: false, dir: null, reason: "outside-profile" };
      }
      return { enabled: true, dir: candidate, reason: "explicit" };
    };
    var MIRROR_CONFIG = describeMirrorConfig();
    var MIRROR_DIR2 = MIRROR_CONFIG.enabled ? MIRROR_CONFIG.dir : null;
    var mirrorState = {
      enabled: false,
      dir: null,
      reason: MIRROR_CONFIG.reason,
      latestStamp: null,
      lastAttempt: null
    };
    var getMirrorStatus = () => ({
      enabled: mirrorState.enabled,
      dir: mirrorState.enabled ? mirrorState.dir : null,
      reason: mirrorState.reason,
      latestStamp: mirrorState.latestStamp,
      lastAttempt: mirrorState.lastAttempt
    });
    var BACKUP_STAMP_RE2 = /\.(\d{8}T\d{9}Z)\.json$/i;
    var BACKUP_KEEP2 = Math.max(1, Number(process.env.LITETASK_BACKUP_KEEP || 5));
    var latestBackupStamp = async (dir) => {
      let best = null;
      let entries;
      try {
        entries = await fs2.readdir(dir, { withFileTypes: true });
      } catch (err) {
        return null;
      }
      for (const entry of entries) {
        const full = path2.join(dir, entry.name);
        if (entry.isDirectory()) {
          const deeper = await latestBackupStamp(full);
          if (deeper && (!best || deeper > best)) best = deeper;
          continue;
        }
        const m = entry.name.match(BACKUP_STAMP_RE2);
        if (m && (!best || m[1] > best)) best = m[1];
      }
      return best;
    };
    var pruneStamps = async (dir, keep) => {
      const byStamp = /* @__PURE__ */ new Map();
      const walk = async (d) => {
        let entries;
        try {
          entries = await fs2.readdir(d, { withFileTypes: true });
        } catch (err) {
          return;
        }
        for (const entry of entries) {
          const full = path2.join(d, entry.name);
          if (entry.isDirectory()) {
            await walk(full);
            continue;
          }
          const m = entry.name.match(BACKUP_STAMP_RE2);
          if (!m) continue;
          const stamp = m[1];
          if (!byStamp.has(stamp)) byStamp.set(stamp, []);
          byStamp.get(stamp).push(full);
        }
      };
      await walk(dir);
      const stamps = Array.from(byStamp.keys()).sort().reverse();
      const doomed = stamps.slice(keep);
      let removed = 0;
      for (const s of doomed) {
        for (const f of byStamp.get(s)) {
          await fs2.remove(f);
          removed++;
        }
      }
      if (removed) {
        console.log(`[LiteTask] Backup rotation: removed ${removed} file(s) from ${doomed.length} old snapshot(s); keeping newest ${Math.min(keep, stamps.length)} of ${stamps.length} (${dir})`);
      }
      return { kept: Math.min(keep, stamps.length), removed };
    };
    var pruneOldBackups = async () => pruneStamps(BACKUP_DIR2, BACKUP_KEEP2);
    var prepareMirrorDir = async () => {
      if (!MIRROR_CONFIG.enabled) return { ok: false, code: MIRROR_CONFIG.reason };
      try {
        await fs2.ensureDir(MIRROR_CONFIG.dir);
        if (process.platform !== "win32") {
          await fs2.chmod(MIRROR_CONFIG.dir, 448);
        } else {
          console.warn("[LiteTask] Mirror root is under user profile; permissions depend on user directory ACL");
        }
        mirrorState.enabled = true;
        mirrorState.dir = MIRROR_CONFIG.dir;
        mirrorState.reason = "explicit";
        return { ok: true };
      } catch (err) {
        console.warn("[LiteTask] Mirror directory unavailable:", err.message);
        mirrorState.enabled = false;
        mirrorState.dir = null;
        mirrorState.reason = "not-writable";
        return { ok: false, code: "MIRROR_NOT_WRITABLE" };
      }
    };
    var backupAllJson2 = async () => {
      const stamp = (/* @__PURE__ */ new Date()).toISOString().replace(/[-:.]/g, "");
      const sources = [];
      const walk = async (dir) => {
        const entries = await fs2.readdir(dir, { withFileTypes: true });
        for (const entry of entries) {
          const full = path2.join(dir, entry.name);
          if (entry.isDirectory()) await walk(full);
          else if (entry.isFile() && entry.name.toLowerCase().endsWith(".json")) sources.push(full);
        }
      };
      await walk(DATA_DIR2);
      for (const src of sources) {
        const relative = path2.relative(DATA_DIR2, src);
        const parsed = path2.parse(relative);
        const target = path2.join(BACKUP_DIR2, parsed.dir, `${parsed.name}.${stamp}.json`);
        await fs2.ensureDir(path2.dirname(target));
        await fs2.copyFile(src, target);
      }
      console.log(`[LiteTask] Startup backup: ${sources.length} JSON file(s) -> ${BACKUP_DIR2} (stamp ${stamp})`);
      await pruneOldBackups();
      let mirrored = 0;
      let mirrorResult = { enabled: false, ok: null, code: null };
      if (MIRROR_CONFIG.enabled) {
        const prep = await prepareMirrorDir();
        if (!prep.ok) {
          mirrorState.lastAttempt = {
            stamp,
            ok: false,
            code: prep.code,
            at: (/* @__PURE__ */ new Date()).toISOString()
          };
          mirrorResult = { enabled: false, ok: false, code: prep.code };
        } else {
          const r = await mirrorBackups(stamp);
          mirrored = r.copied || 0;
          mirrorState.lastAttempt = {
            stamp,
            ok: r.ok,
            code: r.code || null,
            at: (/* @__PURE__ */ new Date()).toISOString()
          };
          if (r.ok) {
            mirrorState.latestStamp = stamp;
          } else {
            mirrorState.enabled = false;
            mirrorState.reason = "mirror-failed";
          }
          mirrorResult = { enabled: mirrorState.enabled, ok: r.ok, code: r.code || null };
        }
      }
      return { count: sources.length, stamp, mirrored, mirror: mirrorResult };
    };
    var mirrorBackups = async (stamp) => {
      if (!MIRROR_CONFIG.enabled) return { ok: false, copied: 0, code: MIRROR_CONFIG.reason };
      let copied = 0;
      try {
        const walk = async (dir) => {
          let entries;
          try {
            entries = await fs2.readdir(dir, { withFileTypes: true });
          } catch (err) {
            return;
          }
          for (const entry of entries) {
            const full = path2.join(dir, entry.name);
            if (entry.isDirectory()) {
              await walk(full);
              continue;
            }
            if (!BACKUP_STAMP_RE2.test(entry.name)) continue;
            if (stamp && entry.name.indexOf(`.${stamp}.`) === -1) continue;
            const rel = path2.relative(BACKUP_DIR2, full);
            const target = path2.join(MIRROR_CONFIG.dir, rel);
            await fs2.ensureDir(path2.dirname(target));
            await fs2.copyFile(full, target);
            copied++;
          }
        };
        await walk(BACKUP_DIR2);
        if (copied) await pruneStamps(MIRROR_CONFIG.dir, BACKUP_KEEP2);
        console.log(`[LiteTask] Backup mirror: ${copied} file(s) -> ${MIRROR_CONFIG.dir}`);
        return { ok: true, copied };
      } catch (err) {
        console.warn("[LiteTask] Backup mirror failed:", err.message);
        return { ok: false, copied, code: "MIRROR_COPY_FAILED" };
      }
    };
    module2.exports = {
      MIRROR_CONFIG,
      MIRROR_DIR: MIRROR_DIR2,
      BACKUP_STAMP_RE: BACKUP_STAMP_RE2,
      BACKUP_KEEP: BACKUP_KEEP2,
      describeMirrorConfig,
      prepareMirrorDir,
      getMirrorStatus,
      latestBackupStamp,
      pruneStamps,
      pruneOldBackups,
      backupAllJson: backupAllJson2,
      mirrorBackups
    };
  }
});

// tests/_artifacts/_skill_build/lib/shutdown.js
var require_shutdown = __commonJS({
  "tests/_artifacts/_skill_build/lib/shutdown.js"(exports2, module2) {
    "use strict";
    var installShutdown = (deps) => {
      const server2 = deps.server;
      const io2 = deps.io;
      const watcher2 = deps.watcher;
      const LP2 = deps.brand || "ADLM";
      const limitMs = Number.isFinite(deps.timeoutMs) ? deps.timeoutMs : Number(process.env.LITETASK_SHUTDOWN_TIMEOUT_MS || 5e3);
      let state = "running";
      const log = (stage, extra) => {
        console.log(`[${LP2}] shutdown: stage=${stage}${extra ? " " + extra : ""}`);
      };
      const finish = (code) => {
        try {
          process.exit(code);
        } catch (_err) {
        }
      };
      const run = async (signal) => {
        if (state !== "running") {
          log("ignored-duplicate-signal", `signal=${signal}`);
          return;
        }
        state = "stopping";
        const timer = setTimeout(() => {
          console.error(`[${LP2}] shutdown: stage=timeout`);
          finish(1);
        }, Math.max(1, limitMs));
        if (timer.unref) timer.unref();
        try {
          log("stop-accept");
          try {
            server2.close(() => {
            });
          } catch (_err) {
          }
          const stall = Number(process.env.LITETASK_SHUTDOWN_STALL_MS || 0);
          if (stall > 0) await new Promise((resolve) => setTimeout(resolve, stall));
          try {
            await watcher2.close();
          } catch (_err) {
          }
          log("watcher-closed");
          try {
            io2.close();
          } catch (err) {
            if (!err || err.code !== "ERR_SERVER_NOT_RUNNING") {
              console.warn(`[${LP2}] shutdown: socket close warning ${err && err.message}`);
            }
          }
          log("socket-closed");
          try {
            if (typeof server2.closeAllConnections === "function") server2.closeAllConnections();
          } catch (_err) {
          }
          log("http-closed");
          clearTimeout(timer);
          log("done");
          state = "stopped";
          finish(0);
        } catch (err) {
          clearTimeout(timer);
          console.error(`[${LP2}] shutdown: stage=error ${err && err.message}`);
          finish(1);
        }
      };
      process.on("SIGTERM", () => {
        void run("SIGTERM");
      });
      process.on("SIGINT", () => {
        void run("SIGINT");
      });
      return { run };
    };
    module2.exports = { installShutdown };
  }
});

// tests/_artifacts/_skill_build/lib/csp.js
var require_csp = __commonJS({
  "tests/_artifacts/_skill_build/lib/csp.js"(exports2, module2) {
    "use strict";
    var fs2 = require("fs");
    var path2 = require("path");
    var crypto2 = require("crypto");
    var DEFAULT_HTML = path2.join(__dirname, "public", "index.html");
    var cache = { key: null, hashes: [] };
    var inlineScriptHashes = (htmlText) => {
      const out = [];
      const re = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
      let m;
      while ((m = re.exec(htmlText)) !== null) {
        if (/\bsrc\s*=/i.test(m[1])) continue;
        const digest = crypto2.createHash("sha256").update(m[2], "utf8").digest("base64");
        out.push(`sha256-${digest}`);
      }
      return [...new Set(out)];
    };
    var currentHashes = (htmlPath) => {
      const p = htmlPath || DEFAULT_HTML;
      try {
        const st = fs2.statSync(p);
        const key = `${st.mtimeMs}:${st.size}`;
        if (cache.key === key) return cache.hashes;
        const html = fs2.readFileSync(p, "utf8");
        cache.key = key;
        cache.hashes = inlineScriptHashes(html);
        return cache.hashes;
      } catch (err) {
        console.warn("[LiteTask] CSP hash read failed; script hashes omitted:", err.message);
        return [];
      }
    };
    var buildPolicy = (htmlPath) => {
      const hashes = currentHashes(htmlPath);
      const script = ["'self'", "'unsafe-eval'", ...hashes.map((h) => `'${h}'`)].join(" ");
      return [
        "default-src 'self'",
        `script-src ${script}`,
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self' data:",
        "connect-src 'self' ws: wss:",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "form-action 'self'"
      ].join("; ");
    };
    var warned = false;
    var createCspMiddleware = (opts) => {
      const o = opts || {};
      const htmlPath = o.htmlPath || DEFAULT_HTML;
      const disabled = process.env.LITETASK_CSP_DISABLE === "1";
      if (disabled && !warned) {
        warned = true;
        console.warn("[LiteTask] WARNING: CSP is disabled by LITETASK_CSP_DISABLE=1 (degradation, not a fix)");
      }
      return (req, res, next) => {
        if (!disabled) res.setHeader("Content-Security-Policy", buildPolicy(htmlPath));
        res.setHeader("X-Content-Type-Options", "nosniff");
        res.setHeader("Referrer-Policy", "no-referrer");
        next();
      };
    };
    module2.exports = { inlineScriptHashes, currentHashes, buildPolicy, createCspMiddleware, DEFAULT_HTML };
  }
});

// tests/_artifacts/_skill_build/lib/logging.js
var require_logging = __commonJS({
  "tests/_artifacts/_skill_build/lib/logging.js"(exports2, module2) {
    "use strict";
    var fs2 = require("fs-extra");
    var path2 = require("path");
    var cfg2 = require_config();
    var paths2 = require_paths();
    var session = require_session();
    var {
      DATA_DIR: DATA_DIR2,
      CATEGORIES_FILE: CATEGORIES_FILE2,
      SHARED_LISTS_DIR: SHARED_LISTS_DIR2,
      BACKUP_DIR: BACKUP_DIR2,
      PASSWORDLESS_LOCAL: PASSWORDLESS_LOCAL2,
      BIND_HOST: BIND_HOST2,
      REACHABILITY: REACHABILITY2
    } = cfg2;
    var {
      LOG_DIR: LOG_DIR2,
      LOG_FILE: LOG_FILE2,
      LOG_MAX_BYTES,
      LOG_KEEP,
      rotateLogIfNeeded,
      writeLogLine
    } = require_logrotate();
    var {
      AUDIT_FILE: AUDIT_FILE2,
      AUDIT_MAX_BYTES,
      AUDIT_KEEP,
      summarizeForAudit,
      writeAudit: writeAudit2
    } = require_audit();
    var {
      MIRROR_DIR: MIRROR_DIR2,
      BACKUP_STAMP_RE: BACKUP_STAMP_RE2,
      BACKUP_KEEP: BACKUP_KEEP2,
      getMirrorStatus,
      latestBackupStamp,
      backupAllJson: backupAllJson2,
      mirrorBackups,
      pruneStamps,
      pruneOldBackups
    } = require_backup();
    var STARTED_AT2 = /* @__PURE__ */ new Date();
    var SECURITY_MODEL2 = PASSWORDLESS_LOCAL2 ? {
      mode: "local-passwordless",
      requiresPassword: false,
      label: "Local Passwordless Mode",
      hint: "Sign in with a username only (no password required). Intended for single-user local machine use. Binds to loopback by default."
    } : {
      mode: "shared-authenticated",
      requiresPassword: true,
      label: "Shared Authenticated Mode",
      hint: "Requires username + password login, issuing a signed server session. For team members in a trusted network."
    };
    var DEV_AUTO_LOGIN2 = PASSWORDLESS_LOCAL2;
    var stampToDate = (stamp) => {
      const m = String(stamp || "").match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(\d{3})Z$/);
      if (!m) return null;
      return /* @__PURE__ */ new Date(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}.${m[7]}Z`);
    };
    var register = (app2, io2, deps) => {
      const site = deps && deps.site || {};
      const openFolder2 = deps && deps.openFolder || { configured: false, rootCount: 0 };
      app2.use((req, res, next) => {
        const t0 = process.hrtime.bigint();
        res.on("finish", () => {
          const ms = Math.round(Number(process.hrtime.bigint() - t0) / 1e4) / 100;
          const safeUrl = String(req.originalUrl || "").replace(/([?&](?:token|session|cookie)=)[^&]*/gi, "$1***");
          writeLogLine(`${(/* @__PURE__ */ new Date()).toISOString()} ${req.method} ${safeUrl} ${res.statusCode} ${ms}ms`);
        });
        next();
      });
      app2.get("/api/config", (req, res) => {
        res.json({
          projectName: site.projectName || "Lite ADLM",
          subtitle: site.subtitle || "Shared Task Tree",
          loginSubtitle: site.loginSubtitle || "Team Shared Workspace",
          goal: typeof site.goal === "string" ? site.goal : "",
          devAutoLogin: DEV_AUTO_LOGIN2,
          passwordless: PASSWORDLESS_LOCAL2,
          securityModel: SECURITY_MODEL2,
          reachability: REACHABILITY2,
          bindHost: BIND_HOST2,
          openFolder: openFolder2
        });
      });
      app2.get("/api/audit", async (req, res) => {
        const actor = req.actor || {};
        if (!actor.isAdmin) {
          return res.status(403).json({
            error: "Forbidden: Only administrators can read the audit log",
            code: "ADMIN_REQUIRED"
          });
        }
        const asked = Number(req.query.limit || 200);
        const limit = Number.isFinite(asked) && asked > 0 ? Math.min(asked, 1e3) : 200;
        try {
          const raw = await fs2.readFile(AUDIT_FILE2, "utf8").catch(() => "");
          const lines = raw.split("\n").filter(Boolean).slice(-limit);
          const entries = [];
          for (const line of lines) {
            try {
              entries.push(JSON.parse(line));
            } catch (err) {
            }
          }
          res.json({ count: entries.length, file: AUDIT_FILE2, entries });
        } catch (err) {
          res.status(500).json({ error: "Failed to read audit log" });
        }
      });
      app2.get("/api/health", async (req, res) => {
        const report = {
          ok: true,
          startedAt: STARTED_AT2.toISOString(),
          // 2026-10-29 fix: elapsed ms / 1000 = seconds, then round to 2 decimals.
          // The previous code divided by 100 twice (=/10000), so uptimeSec read
          // 1/10 of the real value (e.g. 36 min reported as 218s).
          uptimeSec: Math.round((Date.now() - STARTED_AT2.getTime()) / 1e3 * 100) / 100,
          pid: process.pid,
          nodeVersion: process.version,
          dataDir: { path: DATA_DIR2, readable: false },
          lists: [],
          categories: { path: CATEGORIES_FILE2, readable: false, parsable: false },
          backup: { dir: BACKUP_DIR2, latestStamp: null, latestAt: null, ageSec: null },
          mirror: getMirrorStatus(),
          reachability: REACHABILITY2,
          bindHost: BIND_HOST2,
          openFolder: openFolder2,
          sessions: { active: session.activeSessionCount() },
          mode: {
            passwordless: PASSWORDLESS_LOCAL2,
            devAutoLogin: DEV_AUTO_LOGIN2,
            securityModel: SECURITY_MODEL2
          },
          log: { dir: LOG_DIR2, file: LOG_FILE2 },
          audit: { dir: LOG_DIR2, file: AUDIT_FILE2 }
        };
        const reasons = [];
        try {
          await fs2.access(DATA_DIR2, fs2.constants.R_OK);
          await fs2.readdir(DATA_DIR2);
          report.dataDir.readable = true;
        } catch (err) {
          reasons.push("dataDir not readable: " + err.message);
        }
        try {
          const raw = await fs2.readFile(CATEGORIES_FILE2, "utf8");
          JSON.parse(raw);
          report.categories.readable = true;
          report.categories.parsable = true;
        } catch (err) {
          try {
            await fs2.access(CATEGORIES_FILE2, fs2.constants.R_OK);
            report.categories.readable = true;
          } catch (err2) {
            report.categories.readable = false;
          }
          reasons.push("categories.json not usable: " + err.message);
        }
        try {
          const files = await fs2.readdir(SHARED_LISTS_DIR2);
          for (const f of files) {
            if (!f.toLowerCase().endsWith(".json")) continue;
            const listId = path2.parse(f).name;
            if (!paths2.validateListId(listId).ok) continue;
            const doc = await fs2.readJson(path2.join(SHARED_LISTS_DIR2, f));
            report.lists.push({
              listId,
              items: Array.isArray(doc.items) ? doc.items.length : 0,
              rev: doc.rev || null
            });
          }
        } catch (err) {
          reasons.push("shared lists unreadable: " + err.message);
        }
        try {
          const stamp = await latestBackupStamp(BACKUP_DIR2);
          report.backup.latestStamp = stamp || null;
          const at = stampToDate(stamp);
          if (at) {
            report.backup.latestAt = at.toISOString();
            report.backup.ageSec = Math.round((Date.now() - at.getTime()) / 1e3);
          }
          if (MIRROR_DIR2) {
          }
        } catch (err) {
          reasons.push("backup dir unreadable: " + err.message);
        }
        if (reasons.length) {
          report.ok = false;
          report.reason = reasons.join("; ");
          return res.status(503).json(report);
        }
        res.json(report);
      });
    };
    module2.exports = {
      LOG_DIR: LOG_DIR2,
      LOG_FILE: LOG_FILE2,
      LOG_MAX_BYTES,
      LOG_KEEP,
      STARTED_AT: STARTED_AT2,
      MIRROR_DIR: MIRROR_DIR2,
      AUDIT_FILE: AUDIT_FILE2,
      AUDIT_MAX_BYTES,
      AUDIT_KEEP,
      SECURITY_MODEL: SECURITY_MODEL2,
      DEV_AUTO_LOGIN: DEV_AUTO_LOGIN2,
      BACKUP_STAMP_RE: BACKUP_STAMP_RE2,
      BACKUP_KEEP: BACKUP_KEEP2,
      getMirrorStatus,
      rotateLogIfNeeded,
      writeLogLine,
      writeAudit: writeAudit2,
      summarizeForAudit,
      stampToDate,
      latestBackupStamp,
      backupAllJson: backupAllJson2,
      mirrorBackups,
      pruneStamps,
      pruneOldBackups,
      register
    };
  }
});

// tests/_artifacts/_skill_build/lib/archive_txn.js
var require_archive_txn = __commonJS({
  "tests/_artifacts/_skill_build/lib/archive_txn.js"(exports2, module2) {
    "use strict";
    var path2 = require("path");
    var fs2 = require("fs-extra");
    var cfg2 = require_config();
    var util2 = require_util();
    var paths2 = require_paths();
    var { ARCHIVE_DIR: ARCHIVE_DIR2, ARCHIVE_SNAPSHOT_DIR: ARCHIVE_SNAPSHOT_DIR2 } = cfg2;
    var { atomicWriteJson: atomicWriteJson2, withLock: withLock2 } = util2;
    var TXN_SUFFIX = ".txn.json";
    var createTxnSupport = (deps) => {
      const writeAudit2 = deps && deps.writeAudit;
      const drillFaults = () => String(process.env.LITETASK_DRILL_FAULT || "").split(",").map((s) => s.trim()).filter(Boolean);
      const drillOn = (name) => drillFaults().includes(name);
      const txnFilePath = (listId, txnId) => path2.join(ARCHIVE_SNAPSHOT_DIR2, `${listId}-${txnId}${TXN_SUFFIX}`);
      const listTxnFiles = async (listId) => {
        if (!await fs2.pathExists(ARCHIVE_SNAPSHOT_DIR2)) return [];
        const prefix = paths2.snapshotFilePrefix(listId);
        if (!prefix) return [];
        return (await fs2.readdir(ARCHIVE_SNAPSHOT_DIR2)).filter((f) => f.startsWith(prefix) && f.endsWith(TXN_SUFFIX)).sort();
      };
      const findPendingTxn = async (listId) => {
        const files = await listTxnFiles(listId);
        if (!files.length) return null;
        const fp = path2.join(ARCHIVE_SNAPSHOT_DIR2, files[0]);
        try {
          return await fs2.readJson(fp);
        } catch {
          return { phase: "unreadable", listId };
        }
      };
      const clone = (doc) => JSON.parse(JSON.stringify(doc));
      const txnFailure = (code, compensated, stamp, message) => ({
        ok: false,
        txnFailure: true,
        status: 500,
        code,
        compensated: Boolean(compensated),
        snapshotStamp: stamp || null,
        error: message || code
      });
      const auditTxnFailure = async (action, listId, code, stamp, actor) => {
        if (typeof writeAudit2 !== "function") return;
        try {
          await writeAudit2({
            actor: actor && actor.userId || null,
            action,
            listId,
            outcome: "failed",
            params: {},
            note: `code=${code}; stamp=${stamp || ""}`
          });
        } catch (_err) {
        }
      };
      const restoreFile = async (p, doc) => {
        if (drillOn("compensate")) throw new Error("DRILL_COMPENSATE");
        await atomicWriteJson2(p, clone(doc));
      };
      const restoreFileOrRemove = async (p, doc, existed) => {
        if (!existed) {
          await fs2.remove(p).catch(() => {
          });
          return;
        }
        await restoreFile(p, doc);
      };
      const recoverInterruptedTransactions = async () => {
        const out = { recovered: 0, committed: 0, failed: 0 };
        if (!await fs2.pathExists(ARCHIVE_SNAPSHOT_DIR2)) return out;
        const files = (await fs2.readdir(ARCHIVE_SNAPSHOT_DIR2)).filter((f) => f.endsWith(TXN_SUFFIX));
        for (const fn of files) {
          const fp = path2.join(ARCHIVE_SNAPSHOT_DIR2, fn);
          let rec = null;
          try {
            rec = await fs2.readJson(fp);
          } catch (_err) {
            console.warn(`[LiteTask] Transaction record unparseable, kept for manual review: ${fn}`);
            out.failed += 1;
            continue;
          }
          if (!rec || !paths2.validateListId(rec.listId || "").ok) {
            console.warn(`[LiteTask] Transaction record missing valid listId, kept for manual review: ${fn}`);
            out.failed += 1;
            continue;
          }
          await withLock2(`list:${rec.listId}`, async () => {
            if (rec.phase === "list-written") {
              await fs2.remove(fp).catch(() => {
              });
              out.committed += 1;
              return;
            }
            const snapPath = paths2.snapshotFilePath(rec.listId, rec.stamp);
            let snap = null;
            try {
              snap = snapPath ? await fs2.readJson(snapPath) : null;
            } catch (_err) {
              snap = null;
            }
            if (!snap || !snap.activeBefore || !snap.archiveBefore) {
              console.warn(`[LiteTask] Transaction record missing usable snapshot, kept for manual review: ${fn}`);
              out.failed += 1;
              return;
            }
            try {
              const listPath = paths2.listFilePath(rec.listId);
              if (!listPath) throw new Error("INVALID_LIST_ID");
              await atomicWriteJson2(listPath, clone(snap.activeBefore));
              await fs2.ensureDir(ARCHIVE_DIR2);
              const archivePath = paths2.archiveFilePath(rec.listId);
              if (!archivePath) throw new Error("INVALID_LIST_ID");
              const haveArchive = (snap.archiveBefore.items || []).length;
              if (haveArchive) {
                await atomicWriteJson2(archivePath, clone(snap.archiveBefore));
              } else if (await fs2.pathExists(archivePath)) {
                await fs2.remove(archivePath).catch(() => {
                });
              }
              await fs2.remove(fp).catch(() => {
              });
              out.recovered += 1;
            } catch (err) {
              console.warn(`[LiteTask] Startup recovery failed, kept record: ${fn} (${err.message})`);
              out.failed += 1;
            }
          });
        }
        if (out.failed > 0) {
          console.warn(`[LiteTask] ${out.failed} unfinished transaction(s) require manual recovery (see data/archive-snapshots/*.txn.json)`);
        }
        return out;
      };
      return {
        TXN_SUFFIX,
        drillOn,
        txnFilePath,
        listTxnFiles,
        findPendingTxn,
        clone,
        txnFailure,
        auditTxnFailure,
        restoreFile,
        restoreFileOrRemove,
        recoverInterruptedTransactions
      };
    };
    module2.exports = { createTxnSupport };
  }
});

// tests/_artifacts/_skill_build/lib/archive_snapshots.js
var require_archive_snapshots = __commonJS({
  "tests/_artifacts/_skill_build/lib/archive_snapshots.js"(exports2, module2) {
    "use strict";
    var path2 = require("path");
    var fs2 = require("fs-extra");
    var cfg2 = require_config();
    var util2 = require_util();
    var paths2 = require_paths();
    var { ARCHIVE_SNAPSHOT_DIR: ARCHIVE_SNAPSHOT_DIR2, MAX_ARCHIVE_SNAPSHOTS: MAX_ARCHIVE_SNAPSHOTS2 } = cfg2;
    var { atomicWriteJson: atomicWriteJson2 } = util2;
    var snapshotFileFor = (listId, stamp) => paths2.snapshotFilePath(listId, stamp);
    var pruneArchiveSnapshots = async (listId) => {
      try {
        if (!await fs2.pathExists(ARCHIVE_SNAPSHOT_DIR2)) return;
        const prefix = paths2.snapshotFilePrefix(listId);
        if (!prefix) return;
        const files = (await fs2.readdir(ARCHIVE_SNAPSHOT_DIR2)).filter((f) => f.startsWith(prefix) && f.endsWith(".snapshot.json")).sort();
        const excess = files.length - MAX_ARCHIVE_SNAPSHOTS2;
        for (let i = 0; i < excess; i++) {
          await fs2.remove(path2.join(ARCHIVE_SNAPSHOT_DIR2, files[i])).catch(() => {
          });
        }
      } catch (err) {
        console.warn("[LiteTask] snapshot prune skipped:", err.message);
      }
    };
    var writeArchiveSnapshot = async (listId, listName, activeBefore, archiveBefore) => {
      const stamp = (/* @__PURE__ */ new Date()).toISOString();
      const snap = { listId, listName, stamp, activeBefore, archiveBefore };
      await fs2.ensureDir(ARCHIVE_SNAPSHOT_DIR2);
      const f = snapshotFileFor(listId, stamp);
      if (!f) return null;
      await atomicWriteJson2(f, snap);
      await pruneArchiveSnapshots(listId);
      return { file: f, stamp };
    };
    var listArchiveSnapshots = async (listId) => {
      const prefix = paths2.snapshotFilePrefix(listId);
      if (!prefix) return [];
      if (!await fs2.pathExists(ARCHIVE_SNAPSHOT_DIR2)) return [];
      const files = (await fs2.readdir(ARCHIVE_SNAPSHOT_DIR2)).filter((f) => f.startsWith(prefix) && f.endsWith(".snapshot.json")).sort().reverse();
      const out = [];
      for (const fn of files) {
        try {
          const snap = await fs2.readJson(path2.join(ARCHIVE_SNAPSHOT_DIR2, fn));
          const activeIds = (snap.activeBefore && snap.activeBefore.items || []).map((i) => i.itemId);
          const archiveIds = (snap.archiveBefore && snap.archiveBefore.items || []).map((i) => i.itemId);
          out.push({
            file: fn,
            stamp: snap.stamp,
            listName: snap.listName,
            activeItemCount: activeIds.length,
            archiveItemCount: archiveIds.length,
            movedAway: activeIds.length
          });
        } catch (_err) {
        }
      }
      return out;
    };
    var createSnapshotSupport = () => ({
      snapshotFileFor,
      writeArchiveSnapshot,
      pruneArchiveSnapshots,
      listArchiveSnapshots
    });
    module2.exports = { createSnapshotSupport };
  }
});

// tests/_artifacts/_skill_build/lib/archive_core.js
var require_archive_core = __commonJS({
  "tests/_artifacts/_skill_build/lib/archive_core.js"(exports2, module2) {
    "use strict";
    var path2 = require("path");
    var fs2 = require("fs-extra");
    var cfg2 = require_config();
    var util2 = require_util();
    var paths2 = require_paths();
    var { createTxnSupport } = require_archive_txn();
    var { createSnapshotSupport } = require_archive_snapshots();
    var {
      ARCHIVE_DIR: ARCHIVE_DIR2,
      ARCHIVE_SNAPSHOT_DIR: ARCHIVE_SNAPSHOT_DIR2,
      SHARED_LISTS_DIR: SHARED_LISTS_DIR2,
      AUTO_ARCHIVE_ENABLED: AUTO_ARCHIVE_ENABLED2,
      AUTO_ARCHIVE_ENV_MIN: AUTO_ARCHIVE_ENV_MIN2,
      DEFAULT_AUTO_ARCHIVE_MIN_CLOSED: DEFAULT_AUTO_ARCHIVE_MIN_CLOSED2,
      DEFAULT_ARCHIVE_WARN_WITHIN: DEFAULT_ARCHIVE_WARN_WITHIN2,
      MAX_ARCHIVE_SNAPSHOTS: MAX_ARCHIVE_SNAPSHOTS2
    } = cfg2;
    var { contentRev: contentRev2, atomicWriteJson: atomicWriteJson2, withLock: withLock2 } = util2;
    var createArchiveCore = ({ getCategories: getCategories2, writeAudit: writeAudit2 }) => {
      const getArchivePolicy = async () => {
        const cfg3 = await getCategories2();
        const arch = cfg3 && cfg3.archive || {};
        let minClosed = Number(arch.minClosed);
        if (!Number.isFinite(minClosed) || minClosed <= 0) minClosed = DEFAULT_AUTO_ARCHIVE_MIN_CLOSED2;
        let minSource = "categories.json";
        if (typeof AUTO_ARCHIVE_ENV_MIN2 === "string" && AUTO_ARCHIVE_ENV_MIN2.trim() !== "") {
          const envMin = Number(AUTO_ARCHIVE_ENV_MIN2);
          if (Number.isFinite(envMin) && envMin > 0) {
            minClosed = envMin;
            minSource = "env";
          }
        }
        let warnWithin = Number(arch.warnWithin);
        if (!Number.isFinite(warnWithin) || warnWithin < 0) warnWithin = DEFAULT_ARCHIVE_WARN_WITHIN2;
        const protectedIds = Array.isArray(arch.protected) ? arch.protected.filter((x) => typeof x === "string" && x) : [];
        return {
          enabled: AUTO_ARCHIVE_ENABLED2,
          minClosed,
          warnWithin,
          protected: protectedIds,
          minSource
        };
      };
      const archivePathFor = (listId) => paths2.archiveFilePath(listId);
      const readArchive = async (listId) => {
        const p = archivePathFor(listId);
        if (!p) return { listId, items: [] };
        if (!await fs2.pathExists(p)) return { listId, items: [] };
        try {
          return await fs2.readJson(p);
        } catch {
          return { listId, items: [] };
        }
      };
      const {
        snapshotFileFor,
        writeArchiveSnapshot,
        pruneArchiveSnapshots,
        listArchiveSnapshots
      } = createSnapshotSupport();
      const txn = createTxnSupport({ writeAudit: writeAudit2 });
      const {
        TXN_SUFFIX,
        drillOn,
        txnFilePath,
        findPendingTxn,
        clone,
        txnFailure,
        auditTxnFailure,
        restoreFile,
        restoreFileOrRemove,
        recoverInterruptedTransactions
      } = txn;
      const restoreArchiveSnapshot = async (listId, stamp, actor = null) => {
        if (!paths2.validateListId(listId).ok || !paths2.validateStamp(String(stamp || "")).ok) {
          return { ok: false, error: "INVALID_LIST_ID", code: "INVALID_LIST_ID" };
        }
        const fp = paths2.snapshotFilePath(listId, stamp);
        if (!fp) return { ok: false, error: "INVALID_LIST_ID", code: "INVALID_LIST_ID" };
        return withLock2(`list:${listId}`, async () => {
          if (!await fs2.pathExists(ARCHIVE_SNAPSHOT_DIR2)) return { ok: false, error: "no snapshots" };
          const pending = await findPendingTxn(listId);
          if (pending) {
            return txnFailure(
              "ARCHIVE_TXN_PENDING",
              false,
              pending.stamp,
              "List has an unfinished transaction, manual recovery required."
            );
          }
          if (!await fs2.pathExists(fp)) return { ok: false, error: "snapshot not found" };
          const snap = await fs2.readJson(fp);
          if (!snap || !snap.activeBefore || !snap.archiveBefore) {
            return { ok: false, error: "snapshot malformed" };
          }
          const listPath = paths2.listFilePath(listId);
          if (!listPath || !await fs2.pathExists(listPath)) return { ok: false, error: "list missing" };
          const activeBefore = clone(await fs2.readJson(listPath));
          const archivePath = archivePathFor(listId);
          if (!archivePath) return { ok: false, error: "INVALID_LIST_ID", code: "INVALID_LIST_ID" };
          const archiveExisted = await fs2.pathExists(archivePath);
          const archiveBefore = archiveExisted ? clone(await fs2.readJson(archivePath)) : { listId, items: [] };
          const active = clone(snap.activeBefore);
          const archive2 = clone(snap.archiveBefore);
          active.updatedAt = (/* @__PURE__ */ new Date()).toISOString();
          archive2.lastArchivedAt = (/* @__PURE__ */ new Date()).toISOString();
          const txnId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
          const txnFile = txnFilePath(listId, txnId);
          const record = {
            listId,
            action: "archive-restore",
            phase: "prepared",
            snapshotFile: path2.basename(fp),
            stamp: snap.stamp,
            startedAt: (/* @__PURE__ */ new Date()).toISOString()
          };
          await atomicWriteJson2(txnFile, record);
          const update = (phase) => atomicWriteJson2(txnFile, { ...record, phase });
          let wroteList = false;
          let wroteArchive = false;
          try {
            await atomicWriteJson2(listPath, active);
            wroteList = true;
            await update("first-written");
            if (drillOn("crash-after-first-write")) process.exit(1);
            if (drillOn("restore-archive-write")) throw new Error("DRILL_RESTORE_ARCHIVE_WRITE");
            const haveArchive = archive2.items && archive2.items.length;
            if (haveArchive || archiveExisted) {
              await fs2.ensureDir(ARCHIVE_DIR2);
              await atomicWriteJson2(archivePath, archive2);
              wroteArchive = true;
            }
            await update("list-written");
            await fs2.remove(txnFile).catch(() => {
            });
            return {
              ok: true,
              restoredActive: (active.items || []).length,
              restoredArchive: (archive2.items || []).length,
              stamp: snap.stamp
            };
          } catch (err) {
            let rollbackOk = true;
            try {
              if (wroteArchive) await restoreFile(archivePath, archiveBefore);
              if (wroteList) await restoreFile(listPath, activeBefore);
            } catch (_rollbackErr) {
              rollbackOk = false;
            }
            if (rollbackOk) {
              await fs2.remove(txnFile).catch(() => {
              });
              await auditTxnFailure("archive-restore", listId, "ARCHIVE_TXN_FAILED", snap.stamp, actor);
              return txnFailure(
                "ARCHIVE_TXN_FAILED",
                true,
                snap.stamp,
                "Archive restore transaction failed, rolled back to prior state."
              );
            }
            await auditTxnFailure("archive-restore", listId, "ARCHIVE_TXN_MANUAL_RECOVERY", snap.stamp, actor);
            return txnFailure(
              "ARCHIVE_TXN_MANUAL_RECOVERY",
              false,
              snap.stamp,
              "Archive restore transaction failed and rollback incomplete, manual recovery required."
            );
          }
        });
      };
      const isFullyClosed = (it) => {
        if (!it || !it.isDone) return false;
        for (const sub of it.subTasks || []) {
          if (!isFullyClosed(sub)) return false;
        }
        return true;
      };
      const splitClosed = (items, listId, listName, onlyIds = null) => {
        const kept = [];
        const moved = [];
        const stamp = (/* @__PURE__ */ new Date()).toISOString();
        for (const it of items || []) {
          if (!it || typeof it !== "object") continue;
          if ((!onlyIds || onlyIds.has(it.itemId)) && isFullyClosed(it)) {
            moved.push({ ...it, archivedAt: stamp, archivedFrom: listId });
          } else {
            kept.push(it);
          }
        }
        return { kept, moved };
      };
      const archiveList = async (listId, onlyIds = null, actor = null) => withLock2(`list:${listId}`, async () => {
        const listPath = paths2.listFilePath(listId);
        if (!listPath) return { error: "INVALID_LIST_ID" };
        if (!await fs2.pathExists(listPath)) return null;
        const pending = await findPendingTxn(listId);
        if (pending) {
          return txnFailure(
            "ARCHIVE_TXN_PENDING",
            false,
            pending.stamp,
            "List has an unfinished transaction, manual recovery required."
          );
        }
        const data = await fs2.readJson(listPath);
        const archive2 = await readArchive(listId);
        const { kept, moved } = splitClosed(data.items, listId, data.listName, onlyIds);
        if (!moved.length) return { moved: 0, remaining: (data.items || []).length, archiveCount: (archive2.items || []).length };
        const activeBefore = clone(data);
        const archiveBefore = clone(archive2);
        const snap = await writeArchiveSnapshot(listId, data.listName, activeBefore, archiveBefore);
        if (!snap) return { error: "INVALID_LIST_ID" };
        const archiveAfter = clone(archive2);
        archiveAfter.listId = listId;
        archiveAfter.listName = data.listName;
        archiveAfter.category = data.category;
        archiveAfter.items = [...archiveAfter.items || [], ...moved];
        archiveAfter.lastArchivedAt = (/* @__PURE__ */ new Date()).toISOString();
        const activeAfter = clone(data);
        activeAfter.items = kept;
        activeAfter.rev = contentRev2(kept);
        activeAfter.updatedAt = (/* @__PURE__ */ new Date()).toISOString();
        const archivePath = archivePathFor(listId);
        if (!archivePath) return { error: "INVALID_LIST_ID" };
        const archiveExisted = await fs2.pathExists(archivePath);
        const txnId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const txnFile = txnFilePath(listId, txnId);
        const record = {
          listId,
          action: "archive",
          phase: "prepared",
          snapshotFile: path2.basename(snap.file),
          stamp: snap.stamp,
          startedAt: (/* @__PURE__ */ new Date()).toISOString()
        };
        await atomicWriteJson2(txnFile, record);
        const update = (phase) => atomicWriteJson2(txnFile, { ...record, phase });
        let wroteArchive = false;
        let wroteList = false;
        try {
          await fs2.ensureDir(ARCHIVE_DIR2);
          await atomicWriteJson2(archivePath, archiveAfter);
          wroteArchive = true;
          await update("first-written");
          if (drillOn("crash-after-first-write")) process.exit(1);
          if (drillOn("archive-list-write")) throw new Error("DRILL_ARCHIVE_LIST_WRITE");
          await atomicWriteJson2(listPath, activeAfter);
          wroteList = true;
          await update("list-written");
          await fs2.remove(txnFile).catch(() => {
          });
          return { moved: moved.length, remaining: kept.length, archiveCount: archiveAfter.items.length };
        } catch (err) {
          let rollbackOk = true;
          try {
            if (wroteList) await restoreFile(listPath, activeBefore);
            if (wroteArchive) await restoreFileOrRemove(archivePath, archiveBefore, archiveExisted);
          } catch (_rollbackErr) {
            rollbackOk = false;
          }
          if (rollbackOk) {
            await fs2.remove(snap.file).catch(() => {
            });
            await fs2.remove(txnFile).catch(() => {
            });
            await auditTxnFailure("archive", listId, "ARCHIVE_TXN_FAILED", snap.stamp, actor);
            return txnFailure(
              "ARCHIVE_TXN_FAILED",
              true,
              snap.stamp,
              "Archive transaction failed, rolled back to prior state."
            );
          }
          await auditTxnFailure("archive", listId, "ARCHIVE_TXN_MANUAL_RECOVERY", snap.stamp, actor);
          return txnFailure(
            "ARCHIVE_TXN_MANUAL_RECOVERY",
            false,
            snap.stamp,
            "Archive transaction failed and rollback incomplete, manual recovery required."
          );
        }
      });
      const autoArchiveSweep = async () => {
        const policy = await getArchivePolicy();
        if (!policy.enabled) {
          console.log("[LiteTask] Auto-archive disabled (LITETASK_AUTO_ARCHIVE=0).");
          return;
        }
        try {
          const files = (await fs2.readdir(SHARED_LISTS_DIR2)).filter((f) => f.toLowerCase().endsWith(".json")).filter((f) => paths2.validateListId(path2.basename(f, ".json")).ok);
          for (const file of files) {
            const listId = file.replace(/\.json$/, "");
            const data = await fs2.readJson(path2.join(SHARED_LISTS_DIR2, file));
            const closedTop = (data.items || []).filter((i) => i && i.isDone).length;
            if (policy.protected.indexOf(listId) !== -1) {
              if (closedTop >= policy.minClosed) {
                console.log(`[LiteTask] ${listId}: ${closedTop} closed item(s) at or over threshold ${policy.minClosed} \u2014 protected in categories.json, not auto-archived.`);
              }
              continue;
            }
            if (closedTop >= policy.minClosed) {
              const r = await archiveList(listId);
              if (r && r.moved) console.log(`[LiteTask] Auto-archived ${r.moved} closed item(s) from ${listId} (threshold ${policy.minClosed}).`);
            } else if (policy.warnWithin > 0 && closedTop >= policy.minClosed - policy.warnWithin) {
              console.warn(`[LiteTask] ${listId}: ${closedTop} closed item(s) \u2014 ${policy.minClosed - closedTop} more will trigger auto-archive on the next start.`);
            }
          }
        } catch (err) {
          console.warn("[LiteTask] Auto-archive sweep skipped:", err.message);
        }
      };
      const stripArchiveMarkers = (it) => {
        const { archivedAt, archivedFrom, parentItemId, parentTitle, ...rest } = it;
        return rest;
      };
      const indexById = (items) => {
        const map = /* @__PURE__ */ new Map();
        const walk = (arr) => (arr || []).forEach((it) => {
          if (!it || !it.itemId || map.has(it.itemId)) return;
          map.set(it.itemId, it);
          walk(it.subTasks);
        });
        walk(items);
        return map;
      };
      const unarchiveList = async (listId, itemIds) => withLock2(`list:${listId}`, async () => {
        const listPath = paths2.listFilePath(listId);
        if (!listPath) return { error: "INVALID_LIST_ID" };
        if (!await fs2.pathExists(listPath)) return null;
        const archive2 = await readArchive(listId);
        const archived = archive2.items || [];
        const emptyRun = { moved: 0, reattached: 0, orphaned: 0, archiveCount: archived.length };
        if (!archived.length) return { ...emptyRun, remaining: 0 };
        const wanted = new Set(Array.isArray(itemIds) && itemIds.length ? itemIds : archived.map((i) => i && i.itemId));
        const known = new Set(archived.map((i) => i && i.itemId));
        const unknown = [...wanted].filter((id) => !known.has(id));
        if (unknown.length) return { error: "UNKNOWN_ARCHIVED_ITEM", unknown };
        const chosen = archived.filter((i) => i && wanted.has(i.itemId));
        if (!chosen.length) {
          return { ...emptyRun, remaining: (await fs2.readJson(listPath)).items.length };
        }
        const data = await fs2.readJson(listPath);
        const items = Array.isArray(data.items) ? [...data.items] : [];
        const byId = indexById(items);
        const chosenIds = new Set(chosen.map((i) => i.itemId));
        let reattached = 0;
        let orphaned = 0;
        const queue = [...chosen];
        let guard = chosen.length * 4 + 20;
        while (queue.length && guard > 0) {
          guard -= 1;
          const it = queue.shift();
          const pid = it.parentItemId;
          const parent = pid ? byId.get(pid) : null;
          if (parent) {
            if (!Array.isArray(parent.subTasks)) parent.subTasks = [];
            const restored2 = stripArchiveMarkers(it);
            parent.subTasks.push(restored2);
            byId.set(restored2.itemId, restored2);
            reattached += 1;
            continue;
          }
          if (pid && chosenIds.has(pid) && guard > 1) {
            queue.push(it);
            continue;
          }
          const restored = stripArchiveMarkers(it);
          items.push(restored);
          byId.set(restored.itemId, restored);
          if (pid) orphaned += 1;
        }
        for (const it of queue) {
          items.push(stripArchiveMarkers(it));
          if (it.parentItemId) orphaned += 1;
        }
        const kept = archived.filter((i) => i && !wanted.has(i.itemId));
        archive2.items = kept;
        if (!kept.length) {
          await fs2.remove(archivePathFor(listId)).catch(() => {
          });
        } else {
          await atomicWriteJson2(archivePathFor(listId), archive2);
        }
        data.items = items;
        data.rev = contentRev2(items);
        data.updatedAt = (/* @__PURE__ */ new Date()).toISOString();
        await atomicWriteJson2(listPath, data);
        return { moved: chosen.length, reattached, orphaned, remaining: items.length, archiveCount: kept.length };
      });
      const flattenClosedSubtree = (it, level, acc) => {
        acc.push({ itemId: it.itemId, title: it.title, level, isTop: level === 0 });
        for (const sub of it.subTasks || []) flattenClosedSubtree(sub, level + 1, acc);
      };
      return {
        getArchivePolicy,
        archivePathFor,
        readArchive,
        snapshotFileFor,
        writeArchiveSnapshot,
        pruneArchiveSnapshots,
        listArchiveSnapshots,
        restoreArchiveSnapshot,
        isFullyClosed,
        splitClosed,
        archiveList,
        autoArchiveSweep,
        recoverInterruptedTransactions,
        stripArchiveMarkers,
        indexById,
        unarchiveList,
        flattenClosedSubtree
      };
    };
    module2.exports = { createArchiveCore };
  }
});

// tests/_artifacts/_skill_build/lib/archive_routes.js
var require_archive_routes = __commonJS({
  "tests/_artifacts/_skill_build/lib/archive_routes.js"(exports2, module2) {
    "use strict";
    var path2 = require("path");
    var fs2 = require("fs-extra");
    var cfg2 = require_config();
    var logging2 = require_logging();
    var paths2 = require_paths();
    var errors = require_errors();
    var { SHARED_LISTS_DIR: SHARED_LISTS_DIR2 } = cfg2;
    var { writeAudit: writeAudit2 } = logging2;
    var createArchiveRoutes = (app2, io2, deps) => {
      const requireConfirm2 = deps.requireConfirm;
      const core = deps.core;
      const {
        getArchivePolicy,
        readArchive,
        listArchiveSnapshots,
        restoreArchiveSnapshot,
        archiveList,
        unarchiveList,
        isFullyClosed,
        flattenClosedSubtree
      } = core;
      app2.post("/api/lists/:id/archive", async (req, res) => {
        const listId = req.listId || req.params.id;
        if (!paths2.validateListId(listId).ok) {
          return errors.sendError(res, 400, "INVALID_LIST_ID", "Invalid list identifier");
        }
        const actor = req.actor || {};
        if (!actor.isAdmin) {
          return res.status(403).json({
            error: "Forbidden: Only administrators can archive lists",
            code: "ADMIN_REQUIRED"
          });
        }
        const userId = actor.userId || null;
        const gate = requireConfirm2(req, "Archiving will move closed items out of the active list");
        if (gate) return res.status(400).json(gate);
        try {
          const rawIds = req.body.itemIds;
          const onlyIds = Array.isArray(rawIds) && rawIds.length ? new Set(rawIds.map(String)) : null;
          const r = await archiveList(listId, onlyIds, actor);
          if (r && r.txnFailure) {
            return res.status(500).json({
              error: r.error,
              code: r.code,
              compensated: r.compensated,
              snapshotStamp: r.snapshotStamp
            });
          }
          if (!r) return res.status(404).json({ error: "List not found" });
          await writeAudit2({
            actor: userId,
            action: "archive",
            listId,
            confirmed: "explicit",
            params: req.body || {},
            note: `${r.moved} item(s) moved to archive, ${r.remaining} remaining`
          });
          res.json({ success: true, ...r });
        } catch (err) {
          res.status(500).json({ error: "Failed to archive list" });
        }
      });
      app2.get("/api/lists/:id/archive-snapshots", async (req, res) => {
        const listId = req.listId || req.params.id;
        if (!paths2.validateListId(listId).ok) {
          return errors.sendError(res, 400, "INVALID_LIST_ID", "Invalid list identifier");
        }
        const actor = req.actor || {};
        if (!actor.isAdmin) {
          return res.status(403).json({
            error: "Forbidden: Only administrators can view archive snapshots",
            code: "ADMIN_REQUIRED"
          });
        }
        try {
          const snaps = await listArchiveSnapshots(listId);
          res.json({ listId, count: snaps.length, snapshots: snaps });
        } catch (err) {
          res.status(500).json({ error: "Failed to list archive snapshots" });
        }
      });
      app2.post("/api/lists/:id/archive-restore", async (req, res) => {
        const listId = req.listId || req.params.id;
        if (!paths2.validateListId(listId).ok) {
          return errors.sendError(res, 400, "INVALID_LIST_ID", "Invalid list identifier");
        }
        const actor = req.actor || {};
        if (!actor.isAdmin) {
          return res.status(403).json({
            error: "Forbidden: Only administrators can restore archive snapshots",
            code: "ADMIN_REQUIRED"
          });
        }
        const userId = actor.userId || null;
        const stamp = req.body && req.body.stamp;
        if (!stamp) return res.status(400).json({ error: "stamp is required", code: "INVALID_STAMP" });
        if (!paths2.validateStamp(stamp).ok) {
          return errors.sendError(res, 400, "INVALID_STAMP", "Invalid snapshot timestamp");
        }
        const gate = requireConfirm2(req, "Snapshot restore will overwrite the active list");
        if (gate) return res.status(400).json(gate);
        try {
          const r = await restoreArchiveSnapshot(listId, stamp, actor);
          if (r && r.txnFailure) {
            return res.status(500).json({
              error: r.error,
              code: r.code,
              compensated: r.compensated,
              snapshotStamp: r.snapshotStamp
            });
          }
          if (!r || !r.ok) return res.status(404).json({ error: r && r.error ? r.error : "restore failed" });
          await writeAudit2({
            actor: userId,
            action: "archive-restore",
            listId,
            confirmed: "explicit",
            params: req.body || {},
            note: `rolled back to snapshot ${stamp}`
          });
          res.json({ success: true, ...r });
        } catch (err) {
          res.status(500).json({ error: "Failed to restore archive snapshot" });
        }
      });
      app2.post("/api/lists/:id/unarchive", async (req, res) => {
        const listId = req.listId || req.params.id;
        const listPath = paths2.listFilePath(listId);
        if (!listPath) return errors.sendError(res, 400, "INVALID_LIST_ID", "Invalid list identifier");
        const actor = req.actor || {};
        if (!actor.isAdmin) {
          return res.status(403).json({
            error: "Forbidden: Only administrators can unarchive lists",
            code: "ADMIN_REQUIRED"
          });
        }
        const userId = actor.userId || null;
        try {
          if (req.body.baseRev) {
            const cur = await fs2.readJson(listPath).catch(() => null);
            if (cur && cur.rev && cur.rev !== req.body.baseRev) {
              return res.status(409).json({
                code: "REV_CONFLICT",
                error: "List changed since this request was built; reload and retry."
              });
            }
          }
          const itemIds = Array.isArray(req.body.itemIds) ? req.body.itemIds : null;
          const r = await unarchiveList(listId, itemIds);
          if (!r) return res.status(404).json({ error: "List not found" });
          if (r.error === "UNKNOWN_ARCHIVED_ITEM") {
            return res.status(400).json({
              code: r.error,
              error: "These ids are not in the archive: " + r.unknown.join(", "),
              unknown: r.unknown
            });
          }
          await writeAudit2({
            actor: userId,
            action: "unarchive",
            listId,
            params: {
              moved: r.moved,
              reattached: r.reattached,
              orphaned: r.orphaned,
              archiveCount: r.archiveCount
            },
            note: `moved ${r.moved} item(s) from the archive (reattached ${r.reattached}, orphaned ${r.orphaned})`
          });
          res.json({ success: true, ...r });
        } catch (err) {
          res.status(500).json({ error: "Failed to unarchive list" });
        }
      });
      app2.get("/api/lists/:id/archive-preview", async (req, res) => {
        const listId = req.listId || req.params.id;
        const listPath = paths2.listFilePath(listId);
        if (!listPath) return errors.sendError(res, 400, "INVALID_LIST_ID", "Invalid list identifier");
        if (!await fs2.pathExists(listPath)) {
          return res.status(404).json({ error: "List not found" });
        }
        try {
          const data = await fs2.readJson(listPath);
          const items = data.items || [];
          const candidates = [];
          const excluded = [];
          let hasPartial = false;
          for (const it of items) {
            if (isFullyClosed(it)) {
              flattenClosedSubtree(it, 0, candidates);
            } else {
              const reason = !it.isDone ? "Parent task unfinished (subtree preserved per keep-whole-tree rule)" : "Contains unfinished subtasks (subtree preserved per keep-whole-tree rule)";
              excluded.push({ itemId: it.itemId, title: it.title, reason });
              hasPartial = true;
            }
          }
          res.json({
            listId,
            listName: data.listName || "",
            candidates,
            excluded,
            hasPartialCompletion: hasPartial,
            totalMovable: candidates.length
          });
        } catch (err) {
          res.status(500).json({ error: "Failed to compute archive preview" });
        }
      });
      app2.get("/api/archive-status", async (req, res) => {
        try {
          const policy = await getArchivePolicy();
          const files = (await fs2.readdir(SHARED_LISTS_DIR2)).filter((f) => f.toLowerCase().endsWith(".json")).filter((f) => paths2.validateListId(path2.basename(f, ".json")).ok);
          const lists2 = [];
          for (const file of files) {
            const listId = file.replace(/\.json$/, "");
            const data = await fs2.readJson(path2.join(SHARED_LISTS_DIR2, file));
            const items = data.items || [];
            const closed = items.filter((i) => i && i.isDone).length;
            const isProtected = policy.protected.indexOf(listId) !== -1;
            const distance = policy.minClosed - closed;
            lists2.push({
              listId,
              listName: data.listName || "",
              category: data.category || "",
              total: items.length,
              closed,
              threshold: policy.minClosed,
              protected: isProtected,
              wouldArchive: policy.enabled && !isProtected && closed >= policy.minClosed,
              untilArchive: isProtected ? null : distance > 0 ? distance : 0,
              warning: policy.enabled && !isProtected && policy.warnWithin > 0 && closed >= policy.minClosed - policy.warnWithin && closed < policy.minClosed
            });
          }
          lists2.sort((a, b) => a.listId.localeCompare(b.listId));
          res.json({
            enabled: policy.enabled,
            minClosed: policy.minClosed,
            warnWithin: policy.warnWithin,
            thresholdSource: policy.minSource,
            protected: policy.protected,
            lists: lists2
          });
        } catch (err) {
          res.status(500).json({ error: "Failed to read archive status" });
        }
      });
      app2.get("/api/archive/:id", async (req, res) => {
        const listId = req.listId || req.params.id;
        if (!paths2.validateListId(listId).ok) {
          return errors.sendError(res, 400, "INVALID_LIST_ID", "Invalid list identifier");
        }
        try {
          const doc = await readArchive(listId);
          res.json({ listId: doc.listId, listName: doc.listName || "", items: doc.items || [], lastArchivedAt: doc.lastArchivedAt || null });
        } catch (err) {
          res.status(500).json({ error: "Failed to read archive" });
        }
      });
    };
    module2.exports = { createArchiveRoutes };
  }
});

// tests/_artifacts/_skill_build/lib/archive.js
var require_archive = __commonJS({
  "tests/_artifacts/_skill_build/lib/archive.js"(exports2, module2) {
    "use strict";
    var { createArchiveCore } = require_archive_core();
    var { createArchiveRoutes } = require_archive_routes();
    var _autoArchiveSweep = null;
    var _getArchivePolicy = null;
    var _recoverInterruptedTransactions = null;
    var register = (app2, io2, deps) => {
      const requireConfirm2 = deps.requireConfirm;
      const getCategories2 = deps.getCategories;
      const writeAudit2 = deps.writeAudit;
      const core = createArchiveCore({ getCategories: getCategories2, writeAudit: writeAudit2 });
      createArchiveRoutes(app2, io2, { requireConfirm: requireConfirm2, core });
      _autoArchiveSweep = core.autoArchiveSweep;
      _getArchivePolicy = core.getArchivePolicy;
      _recoverInterruptedTransactions = core.recoverInterruptedTransactions;
    };
    var autoArchiveSweep = (...args) => _autoArchiveSweep ? _autoArchiveSweep(...args) : Promise.resolve();
    var getArchivePolicy = async (...args) => {
      if (!_getArchivePolicy) {
        throw new Error("getArchivePolicy() called before archive.register()");
      }
      return _getArchivePolicy(...args);
    };
    var recoverInterruptedTransactions = (...args) => _recoverInterruptedTransactions ? _recoverInterruptedTransactions(...args) : Promise.resolve({ recovered: 0, committed: 0, failed: 0 });
    module2.exports = {
      register,
      autoArchiveSweep,
      getArchivePolicy,
      recoverInterruptedTransactions
    };
  }
});

// tests/_artifacts/_skill_build/lib/links.js
var require_links = __commonJS({
  "tests/_artifacts/_skill_build/lib/links.js"(exports2, module2) {
    "use strict";
    var path2 = require("path");
    var fs2 = require("fs-extra");
    var cfg2 = require_config();
    var { SHARED_LISTS_DIR: SHARED_LISTS_DIR2, ARCHIVE_DIR: ARCHIVE_DIR2 } = cfg2;
    var register = (app2, io2, deps) => {
      const getCategories2 = deps.getCategories;
      const getStatusConfig2 = deps.getStatusConfig;
      app2.get("/api/categories", async (req, res) => {
        try {
          const cfg3 = await getCategories2();
          const sc = await getStatusConfig2();
          res.json({
            categories: Array.isArray(cfg3.categories) ? cfg3.categories : [],
            relations: Array.isArray(cfg3.relations) ? cfg3.relations : [],
            statuses: sc.statuses,
            statusFlow: sc.flow,
            traceability: Array.isArray(cfg3.traceability) ? cfg3.traceability : []
          });
        } catch (err) {
          res.status(500).json({ error: "Failed to read categories" });
        }
      });
      const buildLinkGraph = async () => {
        await fs2.ensureDir(SHARED_LISTS_DIR2);
        const nodes = {};
        const edges = [];
        const visit = (listId, listName, it, archived) => {
          if (!it || !it.itemId) return;
          if (nodes[it.itemId]) return;
          nodes[it.itemId] = {
            itemId: it.itemId,
            listId,
            listName: listName || listId,
            title: it.title || "Untitled",
            isDone: Boolean(it.isDone),
            status: typeof it.status === "string" ? it.status : it.isDone ? "done" : "open",
            priority: it.priority || "Medium",
            archived: Boolean(archived)
          };
          if (Array.isArray(it.relatesTo)) {
            for (const r of it.relatesTo) {
              if (r && r.listId && r.itemId) {
                edges.push({
                  from: { listId, itemId: it.itemId },
                  to: { listId: r.listId, itemId: r.itemId },
                  relation: r.relation || "related"
                });
              }
            }
          }
          if (Array.isArray(it.subTasks)) {
            it.subTasks.forEach((s) => visit(listId, listName, s, archived));
          }
        };
        const visitDir = async (dir, archived) => {
          const files = await fs2.readdir(dir);
          for (const file of files) {
            if (!file.endsWith(".json")) continue;
            const data = await fs2.readJson(path2.join(dir, file));
            const listId = data.listId || file.replace(".json", "");
            const listName = data.listName || listId;
            const items = Array.isArray(data.items) ? data.items : [];
            items.forEach((it) => visit(listId, listName, it, archived));
          }
        };
        await visitDir(SHARED_LISTS_DIR2, false);
        await fs2.ensureDir(ARCHIVE_DIR2);
        await visitDir(ARCHIVE_DIR2, true);
        for (const e of edges) {
          const from = nodes[e.from.itemId];
          const to = nodes[e.to.itemId];
          e.archived = Boolean(from && from.archived || to && to.archived);
        }
        return { nodes: Object.values(nodes), edges };
      };
      app2.get("/api/links", async (req, res) => {
        try {
          const { nodes, edges } = await buildLinkGraph();
          res.json({ nodes, edges });
        } catch (err) {
          res.status(500).json({ error: "Failed to build links graph" });
        }
      });
      app2.get("/api/trace", async (req, res) => {
        try {
          const listId = String(req.query.listId || "");
          const itemId = String(req.query.itemId || "");
          const direction = ["back", "forward", "both"].includes(req.query.direction) ? req.query.direction : "back";
          const depth = Math.max(1, Math.min(6, Number(req.query.depth) || 3));
          if (!listId || !itemId) return res.status(400).json({ error: "listId and itemId are required" });
          const { nodes, edges } = await buildLinkGraph();
          const nodeMap = new Map(nodes.map((n) => [n.itemId, n]));
          const root = nodeMap.get(itemId);
          if (!root) return res.status(404).json({ error: "item not found: " + itemId });
          const back = direction !== "forward";
          const forward = direction !== "back";
          const visited = /* @__PURE__ */ new Set([itemId]);
          const items = [];
          let frontier = [{ id: itemId, path: [] }];
          for (let d = 1; d <= depth; d++) {
            const next = [];
            for (const cur of frontier) {
              const outgoing = forward ? edges.filter((e) => e.from.itemId === cur.id).map((e) => ({ id: e.to.itemId, relation: e.relation, dir: "forward" })) : [];
              const incoming = back ? edges.filter((e) => e.to.itemId === cur.id).map((e) => ({ id: e.from.itemId, relation: e.relation, dir: "back" })) : [];
              for (const step of outgoing.concat(incoming)) {
                if (visited.has(step.id)) continue;
                const n = nodeMap.get(step.id);
                if (!n) continue;
                visited.add(step.id);
                const path3 = cur.path.concat([{
                  itemId: step.id,
                  listId: n.listId,
                  title: n.title,
                  relation: step.relation,
                  direction: step.dir
                }]);
                items.push({
                  itemId: n.itemId,
                  listId: n.listId,
                  listName: n.listName,
                  title: n.title,
                  status: n.status,
                  isDone: n.isDone,
                  archived: Boolean(n.archived),
                  depth: d,
                  path: path3
                });
                next.push({ id: step.id, path: path3 });
              }
            }
            if (next.length === 0) break;
            frontier = next;
          }
          res.json({ root, direction, depth, count: items.length, items });
        } catch (err) {
          res.status(500).json({ error: "Failed to trace relations: " + err.message });
        }
      });
      app2.get("/api/gaps", async (req, res) => {
        try {
          const cfg3 = await getCategories2();
          const configured = Array.isArray(cfg3.traceability) ? cfg3.traceability : [];
          let rules;
          if (req.query.owner) {
            rules = [{
              value: "adhoc",
              label: `${req.query.owner} tasks not referenced by ${req.query.referrer || "any list"}`,
              owner: String(req.query.owner),
              referrer: req.query.referrer ? String(req.query.referrer) : null,
              relation: req.query.relation ? String(req.query.relation) : null
            }];
          } else if (req.query.rule) {
            rules = configured.filter((r) => r.value === req.query.rule);
            if (rules.length === 0) return res.status(400).json({ error: "unknown rule: " + req.query.rule });
          } else {
            rules = configured;
          }
          const { nodes, edges } = await buildLinkGraph();
          const out = rules.map((rule) => {
            if (!rule.owner || rule.owner === "*") {
              const linked = /* @__PURE__ */ new Set();
              edges.forEach((e) => {
                linked.add(e.from.itemId);
                linked.add(e.to.itemId);
              });
              const items2 = nodes.filter((n) => !linked.has(n.itemId) && !n.archived);
              return {
                value: rule.value,
                label: rule.label || "Orphan Tasks",
                owner: "*",
                referrer: null,
                relation: null,
                count: items2.length,
                items: items2
              };
            }
            const covered = /* @__PURE__ */ new Set();
            edges.forEach((e) => {
              if (rule.relation && e.relation !== rule.relation) return;
              if (rule.referrer && e.from.listId !== rule.referrer) return;
              covered.add(e.to.itemId);
            });
            const items = nodes.filter((n) => n.listId === rule.owner && !covered.has(n.itemId) && !n.archived);
            return {
              value: rule.value,
              label: rule.label || rule.value,
              owner: rule.owner,
              referrer: rule.referrer || null,
              relation: rule.relation || null,
              count: items.length,
              items
            };
          });
          res.json({ rules: out });
        } catch (err) {
          res.status(500).json({ error: "Failed to compute gaps: " + err.message });
        }
      });
    };
    module2.exports = { register };
  }
});

// tests/_artifacts/_skill_build/lib/actors.js
var require_actors = __commonJS({
  "tests/_artifacts/_skill_build/lib/actors.js"(exports2, module2) {
    "use strict";
    var fs2 = require("fs-extra");
    var path2 = require("path");
    var cfg2 = require_config();
    var util2 = require_util();
    var logging2 = require_logging();
    var session = require_session();
    var errors = require_errors();
    var {
      USERS_FILE: USERS_FILE2,
      DATA_DIR: DATA_DIR2,
      PASSWORDLESS_LOCAL: PASSWORDLESS_LOCAL2,
      SHARED_LISTS_DIR: SHARED_LISTS_DIR2,
      hashPassword: hashPassword2,
      verifyPassword: verifyPassword2,
      isHashedPassword: isHashedPassword2
    } = cfg2;
    var { isUserAdminOf, adminFlags } = util2;
    var { writeAudit: writeAudit2 } = logging2;
    var register = (app2, io2, deps) => {
      const saveUsers2 = deps.saveUsers;
      app2.post("/api/login", async (req, res) => {
        try {
          const { username, password } = req.body || {};
          const users = await fs2.readJson(USERS_FILE2);
          const user = users.find((u) => u.username === username && (PASSWORDLESS_LOCAL2 || verifyPassword2(password, u.password)));
          if (!user) {
            return res.status(401).json({
              error: "Invalid credentials",
              code: "INVALID_CREDENTIALS"
            });
          }
          if (!PASSWORDLESS_LOCAL2) {
            const issued = session.issueSession(user.userId);
            res.set("Set-Cookie", issued.cookie);
          }
          res.json({
            userId: user.userId,
            username: user.username,
            isAdmin: isUserAdminOf(user)
          });
        } catch (err) {
          res.status(500).json({ error: "Login failed", code: "INTERNAL" });
        }
      });
      app2.post("/api/logout", (req, res) => {
        const cookies = session.parseCookies(req.headers && req.headers.cookie);
        const v = session.verifySession(cookies[session.SESSION_COOKIE]);
        if (v.ok) session.destroySession(v.sid);
        res.set("Set-Cookie", session.buildClearCookie());
        res.json({ success: true });
      });
      const collectRefs = (items, refs) => {
        for (const it of items || []) {
          if (!it || typeof it !== "object") continue;
          for (const k of ["createdBy", "assignedTo", "closedBy"]) {
            if (typeof it[k] === "string" && it[k]) refs.names.add(it[k]);
          }
          for (const k of ["createdById", "closedById"]) {
            if (typeof it[k] === "string" && it[k]) refs.ids.add(it[k]);
          }
          collectRefs(it.subTasks, refs);
        }
      };
      const participates = (items, actor) => {
        for (const it of items || []) {
          if (!it || typeof it !== "object") continue;
          if (it.createdById && it.createdById === actor.userId || it.createdBy && it.createdBy === actor.username || it.assignedTo && it.assignedTo === actor.username || it.closedById && it.closedById === actor.userId || it.closedBy && it.closedBy === actor.username) return true;
          if (participates(it.subTasks, actor)) return true;
        }
        return false;
      };
      const visibleUsersFor = async (actor) => {
        const users = await fs2.readJson(USERS_FILE2);
        const a = actor || {};
        if (PASSWORDLESS_LOCAL2 || a.isAdmin) return users;
        const names = /* @__PURE__ */ new Set();
        const ids = /* @__PURE__ */ new Set();
        if (a.userId) ids.add(a.userId);
        if (a.username) names.add(a.username);
        let files = [];
        try {
          files = (await fs2.readdir(SHARED_LISTS_DIR2)).filter((f) => f.toLowerCase().endsWith(".json"));
        } catch (err) {
          console.warn("[LiteTask] visibility read failed; returning self only:", err.message);
          return users.filter((u) => a.userId && u.userId === a.userId || a.username && u.username === a.username);
        }
        for (const f of files) {
          try {
            const doc = await fs2.readJson(path2.join(SHARED_LISTS_DIR2, f));
            if (!participates(doc.items, a)) continue;
            const refs = { names: /* @__PURE__ */ new Set(), ids: /* @__PURE__ */ new Set() };
            collectRefs(doc.items, refs);
            for (const n of refs.names) names.add(n);
            for (const id of refs.ids) ids.add(id);
          } catch (_err) {
          }
        }
        return users.filter((u) => ids.has(u.userId) || names.has(u.username));
      };
      app2.get("/api/users", async (req, res) => {
        try {
          const users = await visibleUsersFor(req.actor || {});
          const list = users.map((u) => ({
            userId: u.userId,
            username: u.username
          }));
          res.json(list);
        } catch (err) {
          res.status(500).json({ error: "Failed to read users" });
        }
      });
      const adminOnly = (req, res) => {
        const actor = req.actor || {};
        if (!actor.isAdmin) {
          errors.sendError(res, 403, "ADMIN_REQUIRED", "Forbidden: Admin access required");
          return false;
        }
        return true;
      };
      app2.get("/api/admin/users", async (req, res) => {
        if (!adminOnly(req, res)) return;
        try {
          const users = await fs2.readJson(USERS_FILE2);
          const sharedFiles = await fs2.readdir(SHARED_LISTS_DIR2);
          const allItems = [];
          for (const file of sharedFiles) {
            if (file.endsWith(".json")) {
              const listData = await fs2.readJson(path2.join(SHARED_LISTS_DIR2, file));
              if (Array.isArray(listData.items)) {
                allItems.push(...listData.items);
              }
            }
          }
          const admins = adminFlags(users);
          const enriched = users.map((u) => {
            const tasksCreated = allItems.filter((it) => it.createdBy === u.username || it.createdById === u.userId).length;
            const tasksClosed = allItems.filter((it) => it.closedBy === u.username || it.closedById === u.userId).length;
            return {
              userId: u.userId,
              username: u.username,
              isAdmin: admins.has(String(u.userId)),
              tasksCreated,
              tasksClosed,
              passwordScheme: isHashedPassword2(u.password) ? "scrypt" : "legacy",
              passwordRecoverable: false
            };
          });
          res.json(enriched);
        } catch (err) {
          res.status(500).json({ error: "Failed to read users" });
        }
      });
      app2.post("/api/admin/reset-password", async (req, res) => {
        if (!adminOnly(req, res)) return;
        const { targetUserId, newPassword } = req.body || {};
        if (!newPassword || typeof newPassword !== "string" || newPassword.trim().length === 0) {
          return res.status(400).json({ error: "New password cannot be empty" });
        }
        try {
          const users = await fs2.readJson(USERS_FILE2);
          const targetIndex = users.findIndex((u) => u.userId === targetUserId);
          if (targetIndex === -1) {
            return res.status(404).json({ error: "Target user not found" });
          }
          users[targetIndex].password = hashPassword2(newPassword.trim());
          await saveUsers2(users);
          await writeAudit2({
            actor: req.actor && req.actor.userId || null,
            action: "reset-password",
            params: { targetUserId },
            note: `password reset for ${users[targetIndex].username}`
          });
          res.json({ success: true, message: `Password for ${users[targetIndex].username} reset successfully.` });
        } catch (err) {
          res.status(500).json({ error: "Failed to update password" });
        }
      });
      app2.post("/api/admin/users", async (req, res) => {
        if (!adminOnly(req, res)) return;
        const { username, password, isAdmin } = req.body || {};
        if (!username || !password || !username.trim() || !password.trim()) {
          return res.status(400).json({ error: "Username and password cannot be empty" });
        }
        const cleanUsername = username.trim();
        const cleanPassword = password.trim();
        if (cleanUsername.length < 2) {
          return res.status(400).json({ error: "Username must be at least 2 characters long" });
        }
        if (cleanPassword.length < 3) {
          return res.status(400).json({ error: "Password must be at least 3 characters long" });
        }
        try {
          const users = await fs2.readJson(USERS_FILE2);
          if (users.find((u) => u.username.toLowerCase() === cleanUsername.toLowerCase())) {
            return res.status(400).json({ error: `Username "${cleanUsername}" already exists` });
          }
          const userId = "user_" + Date.now();
          const newUser = {
            userId,
            username: cleanUsername,
            password: hashPassword2(cleanPassword),
            isAdmin: Boolean(isAdmin)
          };
          users.push(newUser);
          await saveUsers2(users);
          res.json({
            success: true,
            user: {
              userId: newUser.userId,
              username: newUser.username,
              isAdmin: newUser.isAdmin
            },
            message: `User "${cleanUsername}" created successfully.`
          });
        } catch (err) {
          res.status(500).json({ error: "Failed to create user" });
        }
      });
      app2.delete("/api/admin/users/:userId", async (req, res) => {
        if (!adminOnly(req, res)) return;
        const actor = req.actor || {};
        const targetUserId = req.params.userId;
        if (targetUserId === "user_admin" || targetUserId === actor.userId) {
          return res.status(400).json({ error: "Cannot delete primary admin account" });
        }
        try {
          let users = await fs2.readJson(USERS_FILE2);
          users = users.filter((u) => u.userId !== targetUserId);
          await saveUsers2(users);
          session.destroySessionsForUser(targetUserId);
          const legacyUserDir = path2.join(DATA_DIR2, "users", targetUserId);
          if (await fs2.pathExists(legacyUserDir)) {
            await fs2.remove(legacyUserDir);
          }
          await writeAudit2({
            actor: actor.userId || null,
            action: "delete-user",
            params: { targetUserId },
            note: "user account removed"
          });
          res.json({ success: true });
        } catch (err) {
          res.status(500).json({ error: "Failed to delete user" });
        }
      });
    };
    module2.exports = { register };
  }
});

// tests/_artifacts/_skill_build/lib/comment_sanitizer.js
var require_comment_sanitizer = __commonJS({
  "tests/_artifacts/_skill_build/lib/comment_sanitizer.js"(exports2, module2) {
    "use strict";
    var MAX_CHARS = (() => {
      const n = Number(process.env.LITETASK_COMMENT_MAX_CHARS || 2e4);
      return Number.isFinite(n) && n > 0 ? n : 2e4;
    })();
    var ALLOWED_TAGS = /* @__PURE__ */ new Set([
      "p",
      "br",
      "strong",
      "b",
      "em",
      "i",
      "u",
      "s",
      "ol",
      "ul",
      "li",
      "a",
      "span"
    ]);
    var DROP_WITH_CONTENT = [
      "script",
      "style",
      "iframe",
      "object",
      "embed",
      "svg",
      "math",
      "template",
      "noscript",
      "form"
    ];
    var ENTITY_RE = /^&(amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);/;
    var escapeText = (text) => {
      let out = "";
      for (let i = 0; i < text.length; i++) {
        const ch = text[i];
        if (ch === "<") out += "&lt;";
        else if (ch === ">") out += "&gt;";
        else if (ch === "&") {
          const tail = text.slice(i);
          const m = ENTITY_RE.exec(tail);
          if (m) {
            out += m[0];
            i += m[0].length - 1;
          } else {
            out += "&amp;";
          }
        } else out += ch;
      }
      return out;
    };
    var safeHref = (href) => {
      const v = String(href || "").trim();
      if (!v) return null;
      if (/^(https?:|mailto:)/i.test(v)) return v;
      if (/^[./#?]/.test(v)) return v;
      return null;
    };
    var attrMap = (raw) => {
      const out = {};
      const re = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*(?:=\s*("([^"]*)"|'([^']*)'|([^\s>]+)))?/g;
      let m;
      while ((m = re.exec(raw)) !== null) {
        out[m[1].toLowerCase()] = m[3] !== void 0 ? m[3] : m[4] !== void 0 ? m[4] : m[5] !== void 0 ? m[5] : "";
      }
      return out;
    };
    var classAllowed = (v) => /^ql-(align|size|font|indent|direction)-[a-z0-9-]+$/.test(v);
    var renderTag = (name, rawAttrs, closing) => {
      if (!ALLOWED_TAGS.has(name)) return "";
      if (name === "br") return "<br>";
      if (closing) return `</${name}>`;
      const a = attrMap(rawAttrs || "");
      const parts = [];
      if (name === "a") {
        const href = safeHref(a.href);
        if (!href) return "<a>";
        parts.push(`href="${href.replace(/"/g, "&quot;")}"`);
        if (a.target === "_blank") {
          parts.push('target="_blank"');
          parts.push('rel="noopener noreferrer"');
        }
      } else if (name === "p" || name === "span") {
        if (a.class && classAllowed(a.class)) parts.push(`class="${a.class}"`);
      } else if (name === "li") {
        if (a["data-list"] && /^(ordered|bullet|checked|unchecked)$/.test(a["data-list"])) {
          parts.push(`data-list="${a["data-list"]}"`);
        }
      }
      return parts.length ? `<${name} ${parts.join(" ")}>` : `<${name}>`;
    };
    var stripBlockedContainers = (html) => {
      let s = html;
      for (const tag of DROP_WITH_CONTENT) {
        const re = new RegExp(`<${tag}\\b[^>]*>[\\s\\S]*?<\\/${tag}\\s*>`, "gi");
        let prev;
        do {
          prev = s;
          s = s.replace(re, "");
        } while (s !== prev);
        s = s.replace(new RegExp(`<${tag}\\b[^>]*\\/?>`, "gi"), "");
      }
      return s.replace(/<!--[\s\S]*?-->/g, "");
    };
    var sanitizeCommentHtml = (html) => {
      if (typeof html !== "string") return { ok: true, html, violations: [] };
      if (html.length > MAX_CHARS) {
        return {
          ok: false,
          html,
          violations: ["COMMENT_TOO_LONG"],
          code: "COMMENT_TOO_LONG",
          limit: MAX_CHARS,
          actual: html.length
        };
      }
      const violations = [];
      let s = stripBlockedContainers(html);
      let out = "";
      let i = 0;
      while (i < s.length) {
        const lt = s.indexOf("<", i);
        if (lt < 0) {
          out += escapeText(s.slice(i));
          break;
        }
        out += escapeText(s.slice(i, lt));
        const gt = s.indexOf(">", lt + 1);
        if (gt < 0) {
          out += escapeText(s.slice(lt));
          break;
        }
        const raw = s.slice(lt + 1, gt);
        if (/^!|^\?/.test(raw)) {
          i = gt + 1;
          continue;
        }
        const closing = raw.startsWith("/");
        const body = closing ? raw.slice(1).trim() : raw.trim();
        const nameMatch = /^([a-zA-Z][a-zA-Z0-9]*)/.exec(body);
        if (!nameMatch) {
          out += escapeText(s.slice(lt, gt + 1));
          i = gt + 1;
          continue;
        }
        const name = nameMatch[1].toLowerCase();
        const attrs = body.slice(name.length);
        if (!ALLOWED_TAGS.has(name)) {
          violations.push(`unknown-tag:${name}`);
        } else {
          out += renderTag(name, attrs, closing);
        }
        i = gt + 1;
      }
      return { ok: true, html: out, violations };
    };
    var sanitizeCommentsInPlace = (items) => {
      const violations = [];
      const walk = (arr) => {
        for (const it of arr || []) {
          if (!it || typeof it !== "object") continue;
          if (typeof it.comment === "string" && it.comment) {
            const r2 = sanitizeCommentHtml(it.comment);
            if (!r2.ok) return {
              ok: false,
              code: r2.code,
              limit: r2.limit,
              actual: r2.actual,
              itemId: it.itemId || null,
              violations: r2.violations
            };
            it.comment = r2.html;
            violations.push(...r2.violations);
          }
          const sub = walk(it.subTasks);
          if (sub && !sub.ok) return sub;
        }
        return { ok: true };
      };
      const r = walk(items);
      return r && !r.ok ? r : { ok: true, violations };
    };
    module2.exports = {
      COMMENT_MAX_CHARS: MAX_CHARS,
      sanitizeCommentHtml,
      sanitizeCommentsInPlace
    };
  }
});

// tests/_artifacts/_skill_build/lib/schema.js
var require_schema = __commonJS({
  "tests/_artifacts/_skill_build/lib/schema.js"(exports2, module2) {
    "use strict";
    var sanitizeRelatesTo2 = (items) => {
      const walk = (arr) => {
        if (!Array.isArray(arr)) return;
        for (const it of arr) {
          if (!it || typeof it !== "object") continue;
          if (!Array.isArray(it.relatesTo)) {
            it.relatesTo = [];
          } else {
            it.relatesTo = it.relatesTo.filter((r) => r && typeof r === "object" && r.listId && r.itemId).map((r) => ({
              listId: String(r.listId),
              itemId: String(r.itemId),
              relation: typeof r.relation === "string" && r.relation ? r.relation : "related"
            }));
          }
          if (it.subTasks) walk(it.subTasks);
        }
      };
      walk(items);
      return items;
    };
    var sanitizeLocalDirectories2 = (items) => {
      const walk = (arr) => {
        if (!Array.isArray(arr)) return;
        for (const it of arr) {
          if (!it || typeof it !== "object") continue;
          const primary = typeof it.localDirectory === "string" && it.localDirectory.trim() ? it.localDirectory.trim() : "";
          const extra = (Array.isArray(it.localDirectories) ? it.localDirectories : []).filter((p) => typeof p === "string" && p.trim()).map((p) => p.trim()).slice(0, 20);
          const seen = /* @__PURE__ */ new Set();
          const merged = [primary, ...extra].filter((p) => {
            const k = p.replace(/[\\/]+$/, "").toLowerCase();
            if (!p || seen.has(k)) return false;
            seen.add(k);
            return true;
          });
          it.localDirectory = merged[0] || "";
          it.localDirectories = merged.slice(1);
          if (it.subTasks) walk(it.subTasks);
        }
      };
      walk(items);
      return items;
    };
    var ITEM_FIELD_TYPES = {
      itemId: "string",
      title: "string",
      isDone: "boolean",
      status: "string",
      statusHistory: "array",
      blockedReason: "string",
      dueDate: "string",
      priority: "string",
      assignedTo: "string",
      createdBy: "string",
      createdByAgent: "string",
      createdById: "string",
      createdAt: "string",
      // closed* accept null (set on close, cleared on reopen) or string
      closedBy: ["string", "null"],
      closedById: ["string", "null"],
      closedAt: ["string", "null"],
      localDirectory: "string",
      localDirectories: "array",
      comment: "string",
      subTasks: "array",
      relatesTo: "array"
    };
    var ITEM_ENUM_FIELDS = {
      status: ["open", "in-progress", "blocked", "verified", "done"],
      priority: ["High", "Medium", "Low"]
    };
    var ITEM_REQUIRED = ["itemId", "title"];
    var jsonTypeOf = (v) => {
      if (v === null) return "null";
      if (Array.isArray(v)) return "array";
      return typeof v;
    };
    var validateOneItem = (it, errors) => {
      for (const f of ITEM_REQUIRED) {
        const v = it[f];
        if (v === void 0 || v === null || v === "") {
          errors.push({
            itemId: it.itemId || null,
            field: f,
            message: `Required field missing or empty: ${f}`
          });
        }
      }
      for (const [f, expected] of Object.entries(ITEM_FIELD_TYPES)) {
        if (!(f in it)) continue;
        const v = it[f];
        const allowed = Array.isArray(expected) ? expected : [expected];
        const actual = jsonTypeOf(v);
        if (!allowed.includes(actual)) {
          errors.push({
            itemId: it.itemId || null,
            field: f,
            message: `Field type error: ${f} expected ${allowed.join("/")}, got ${actual}`
          });
        }
        if (ITEM_ENUM_FIELDS[f] && jsonTypeOf(v) === "string" && !ITEM_ENUM_FIELDS[f].includes(v)) {
          errors.push({
            itemId: it.itemId || null,
            field: f,
            message: `Enum out of range: ${f}=${v}, allowed ${ITEM_ENUM_FIELDS[f].join("/")}`
          });
        }
      }
    };
    var validateItems2 = (items) => {
      const errors = [];
      const walk = (arr, where) => {
        if (!Array.isArray(arr)) {
          errors.push({
            itemId: null,
            field: where || "items",
            message: "items must be an array"
          });
          return;
        }
        for (const it of arr) {
          if (!it || typeof it !== "object") {
            errors.push({
              itemId: null,
              field: where || "items",
              message: "Each item must be an object"
            });
            continue;
          }
          validateOneItem(it, errors);
          if (Array.isArray(it.subTasks)) walk(it.subTasks, (it.itemId || "?") + "/subTasks");
        }
      };
      walk(items);
      return { ok: errors.length === 0, errors };
    };
    var { sanitizeCommentsInPlace } = require_comment_sanitizer();
    var sanitizeItems = (items) => {
      const r = sanitizeCommentsInPlace(items);
      return r && r.ok === false ? r : { ok: true, violations: r && r.violations || [] };
    };
    module2.exports = { sanitizeRelatesTo: sanitizeRelatesTo2, sanitizeLocalDirectories: sanitizeLocalDirectories2, validateItems: validateItems2, sanitizeItems };
  }
});

// tests/_artifacts/_skill_build/lib/lists_routes.js
var require_lists_routes = __commonJS({
  "tests/_artifacts/_skill_build/lib/lists_routes.js"(exports2, module2) {
    "use strict";
    var path2 = require("path");
    var fs2 = require("fs-extra");
    var cfg2 = require_config();
    var util2 = require_util();
    var logging2 = require_logging();
    var paths2 = require_paths();
    var errors = require_errors();
    var { sanitizeItems } = require_schema();
    var { SHARED_LISTS_DIR: SHARED_LISTS_DIR2 } = cfg2;
    var { contentRev: contentRev2, atomicWriteJson: atomicWriteJson2, withLock: withLock2, diffItems: diffItems2 } = util2;
    var { writeAudit: writeAudit2 } = logging2;
    var createListRoutes = (app2, io2, deps) => {
      const core = deps.core;
      const {
        getStatusConfig: getStatusConfig2,
        collectStatuses: collectStatuses2,
        sanitizeStatus: sanitizeStatus2,
        validateItems: validateItems2,
        sanitizeRelatesTo: sanitizeRelatesTo2,
        sanitizeLocalDirectories: sanitizeLocalDirectories2
      } = deps;
      const {
        listsETag,
        answerWithETag,
        actorOf: actorOf2,
        changeEvent,
        requireConfirm: requireConfirm2,
        collectItemIds,
        indexAllItemIds
      } = core;
      app2.get("/api/lists", async (req, res) => {
        try {
          await fs2.ensureDir(SHARED_LISTS_DIR2);
          const files = await fs2.readdir(SHARED_LISTS_DIR2);
          const lists2 = [];
          for (const file of files) {
            if (!file.toLowerCase().endsWith(".json")) continue;
            if (!paths2.validateListId(path2.basename(file, ".json")).ok) continue;
            const data = await fs2.readJson(path2.join(SHARED_LISTS_DIR2, file));
            data.rev = contentRev2(data.items);
            lists2.push(data);
          }
          lists2.sort((a, b) => a.listId.localeCompare(b.listId));
          answerWithETag(req, res, listsETag(lists2), lists2);
        } catch (err) {
          res.status(500).json({ error: "Failed to read shared lists" });
        }
      });
      app2.get("/api/lists/:id", async (req, res) => {
        const listId = req.params.id;
        const listPath = paths2.listFilePath(listId);
        if (!listPath) return errors.sendError(res, 400, "INVALID_LIST_ID", "Invalid list identifier");
        try {
          const data = await fs2.readJson(listPath);
          data.rev = contentRev2(data.items);
          answerWithETag(req, res, `"${data.rev}"`, data);
        } catch (err) {
          if (err && (err.code === "ENOENT" || err.code === "ENOTDIR")) {
            return res.status(404).json({ error: "List not found", code: "LIST_NOT_FOUND" });
          }
          res.status(500).json({ error: "Failed to read list" });
        }
      });
      app2.post("/api/lists", async (req, res) => {
        try {
          const { listName } = req.body;
          if (!listName || !listName.trim()) {
            return res.status(400).json({ error: "List name is required" });
          }
          await fs2.ensureDir(SHARED_LISTS_DIR2);
          const files = await fs2.readdir(SHARED_LISTS_DIR2);
          let maxId = 0;
          files.forEach((f) => {
            const num = parseInt(f.split(".")[0]);
            if (!isNaN(num) && num > maxId) maxId = num;
          });
          const listId = String(maxId + 1).padStart(2, "0");
          const now = /* @__PURE__ */ new Date();
          const pad = (n) => String(n).padStart(2, "0");
          const createdAt = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
          const newList = {
            listId,
            listName: listName.trim(),
            owner: req.actor && (req.actor.username || req.actor.userId) || "Shared",
            createdAt,
            items: [],
            rev: contentRev2([])
          };
          const listPath = paths2.listFilePath(listId);
          if (!listPath) return errors.sendError(res, 400, "INVALID_LIST_ID", "Invalid list identifier");
          await withLock2("lists:create", async () => {
            await atomicWriteJson2(listPath, newList);
          });
          res.json(newList);
        } catch (err) {
          res.status(500).json({ error: "Failed to create list" });
        }
      });
      app2.put("/api/lists/:id", async (req, res) => {
        const listId = req.params.id;
        const listPath = paths2.listFilePath(listId);
        if (!listPath) return errors.sendError(res, 400, "INVALID_LIST_ID", "Invalid list identifier");
        try {
          const type = req.body && req.body.type;
          if (type === "RENAME") {
            const { listName } = req.body;
            return await withLock2(`list:${listId}`, async () => {
              const data = await fs2.readJson(listPath);
              data.listName = listName.trim();
              data.rev = contentRev2(data.items);
              await atomicWriteJson2(listPath, data);
              return res.json(data);
            });
          } else if (type === "UPDATE_ITEMS") {
            const { items, baseRev, force } = req.body;
            const actor = req.actor || {};
            const userId = actor.userId || null;
            sanitizeRelatesTo2(items);
            sanitizeLocalDirectories2(items);
            const sani = sanitizeItems(items);
            if (!sani.ok) {
              return res.status(400).json({
                error: "Comment content exceeds maximum length",
                code: sani.code || "COMMENT_TOO_LONG",
                limit: sani.limit,
                actual: sani.actual,
                itemId: sani.itemId
              });
            }
            const vchk = validateItems2(items);
            if (!vchk.ok) {
              return res.status(400).json({
                error: `Invalid item data: ${vchk.errors[0].message}` + (vchk.errors.length > 1 ? ` (${vchk.errors.length} errors total)` : ""),
                code: "INVALID_ITEM_SCHEMA",
                violations: vchk.errors.slice(0, 20)
              });
            }
            const forceOverwrite = force === true;
            return await withLock2(`list:${listId}`, async () => {
              const data = await fs2.readJson(listPath);
              const serverRev = contentRev2(data.items);
              if (baseRev && baseRev !== serverRev && !forceOverwrite) {
                return res.status(409).json({
                  error: "Conflict: this list was modified by someone else. Reload before saving.",
                  code: "REV_CONFLICT",
                  serverRev,
                  items: data.items,
                  // Field-level comparison the UI renders for side-by-side diffing
                  diff: diffItems2(items, data.items),
                  updatedAt: data.updatedAt || null,
                  updatedBy: data.updatedBy || null
                });
              }
              if (forceOverwrite && baseRev && baseRev !== serverRev) {
                const d = diffItems2(items, data.items).counts;
                console.log(`[B3] force overwrite list ${listId}: rev ${serverRev} -> (client ${baseRev}); +${d.added} / -${d.removed} / ~${d.changed} items, ${d.fields} fields`);
              }
              if (userId && !actor.isAdmin) {
                const existingIds = collectItemIds(data.items);
                const newIds = collectItemIds(items);
                for (const id of existingIds) {
                  if (!newIds.has(id)) {
                    return res.status(403).json({
                      error: "Forbidden: Regular users are not allowed to delete items from shared lists. Please close the task instead.",
                      code: "ADMIN_REQUIRED"
                    });
                  }
                }
              }
              const sc = await getStatusConfig2();
              const prevStatuses = collectStatuses2(data.items, sc);
              const actorName = actor.username || null;
              const chk = sanitizeStatus2(items, prevStatuses, sc, userId, actorName);
              if (!chk.ok) {
                const v = chk.violation;
                return res.status(400).json({
                  error: `Invalid status transition '${v.from} -> ${v.to}' (${v.title || v.itemId}). Allowed: ${v.allowed.join(" / ")}`,
                  code: "INVALID_TRANSITION",
                  violation: v
                });
              }
              const nextRev = contentRev2(items);
              const prevRev = contentRev2(data.items);
              if (nextRev === prevRev) {
                return res.json({ ...data, rev: nextRev });
              }
              const beforeIds = new Set((data.items || []).filter((i) => i && i.itemId).map((i) => i.itemId));
              const afterIds = new Set((Array.isArray(items) ? items : []).filter((i) => i && i.itemId).map((i) => i.itemId));
              let removedCount = 0;
              for (const id of beforeIds) {
                if (!afterIds.has(id)) removedCount++;
              }
              const destructive = !!forceOverwrite && removedCount > 0;
              if (destructive) {
                const gate = requireConfirm2(
                  req,
                  `Full list overwrite will delete ${removedCount} existing item(s)`,
                  { removed: removedCount }
                );
                if (gate) return res.status(400).json(gate);
              }
              data.items = items;
              data.rev = nextRev;
              data.updatedAt = (/* @__PURE__ */ new Date()).toISOString();
              data.updatedBy = userId || null;
              await atomicWriteJson2(listPath, data);
              await writeAudit2({
                actor: userId,
                action: destructive ? "overwrite" : "update-items",
                listId,
                // After the hard gate there is no "implicit" here: what passes the gate must be explicit confirmation.
                confirmed: destructive ? "explicit" : null,
                params: req.body || {},
                note: destructive ? `forced overwrite dropped ${removedCount} existing item(s)` : `${(items || []).length} item(s) written`
              });
              io2.emit("items-changed", changeEvent(listId, data.rev, {
                source: "api",
                actor: await actorOf2(userId),
                items: (items || []).length,
                summary: destructive ? `overwrite dropped ${removedCount} item(s)` : `${(items || []).length} item(s) written`
              }));
              return res.json(data);
            });
          }
          res.status(400).json({ error: "Unknown update type" });
        } catch (err) {
          if (err && (err.code === "ENOENT" || err.code === "ENOTDIR")) {
            return res.status(404).json({ error: "List not found", code: "LIST_NOT_FOUND" });
          }
          res.status(500).json({ error: "Failed to update list" });
        }
      });
      app2.delete("/api/lists/:id", async (req, res) => {
        const listId = req.params.id;
        const listPath = paths2.listFilePath(listId);
        if (!listPath) return errors.sendError(res, 400, "INVALID_LIST_ID", "Invalid list identifier");
        const actor = req.actor || {};
        if (!actor.isAdmin) {
          return res.status(403).json({
            error: "Forbidden: Only administrators can delete shared lists",
            code: "ADMIN_REQUIRED"
          });
        }
        const userId = actor.userId || null;
        let itemCount = 0;
        if (await fs2.pathExists(listPath)) {
          const doc = await fs2.readJson(listPath).catch(() => null);
          itemCount = doc && Array.isArray(doc.items) ? doc.items.length : 0;
        }
        const gate = requireConfirm2(req, `Deleting list will remove ${itemCount} item(s) together with it`);
        if (gate) return res.status(400).json(Object.assign(gate, { items: itemCount }));
        if (await fs2.pathExists(listPath)) {
          await fs2.remove(listPath);
        }
        await writeAudit2({
          actor: userId,
          action: "delete-list",
          listId,
          confirmed: "explicit",
          params: req.query || {},
          note: `list file removed (${itemCount} item(s) inside)`
        });
        res.json({ success: true });
      });
      app2.get("/api/integrity", async (req, res) => {
        try {
          const index = await indexAllItemIds();
          const seen = /* @__PURE__ */ new Map();
          const dangling = [];
          const listFiles = (await fs2.readdir(SHARED_LISTS_DIR2)).filter((f) => f.toLowerCase().endsWith(".json")).filter((f) => paths2.validateListId(path2.basename(f, ".json")).ok);
          let itemCount = 0;
          for (const f of listFiles) {
            const doc = await fs2.readJson(path2.join(SHARED_LISTS_DIR2, f)).catch(() => null);
            if (!doc) continue;
            const listId = doc.listId || path2.parse(f).name;
            const walk = (arr) => (arr || []).forEach((it) => {
              if (!it || typeof it !== "object") return;
              itemCount++;
              if (it.itemId) {
                const key = String(it.itemId);
                const occurrences = seen.get(key) || [];
                occurrences.push({ listId, title: it.title || "" });
                seen.set(key, occurrences);
              }
              for (const e of it.relatesTo || []) {
                if (!e || typeof e !== "object") continue;
                const targetList = String(e.listId || "");
                const targetItem = String(e.itemId || "");
                if (!targetList || !targetItem) continue;
                const set = index.get(targetList);
                if (!set) {
                  dangling.push({
                    listId,
                    itemId: it.itemId || null,
                    title: it.title || "",
                    relation: e.relation || "",
                    target: { listId: targetList, itemId: targetItem },
                    reason: "target-list-missing"
                  });
                } else if (!set.has(targetItem)) {
                  dangling.push({
                    listId,
                    itemId: it.itemId || null,
                    title: it.title || "",
                    relation: e.relation || "",
                    target: { listId: targetList, itemId: targetItem },
                    reason: "target-item-missing"
                  });
                }
              }
              walk(it.subTasks);
            });
            walk(doc.items);
          }
          const duplicates = [];
          for (const [itemId, occurrences] of seen.entries()) {
            if (occurrences.length < 2) continue;
            const lists2 = new Set(occurrences.map((o) => o.listId));
            duplicates.push({
              itemId,
              count: occurrences.length,
              crossList: lists2.size > 1,
              occurrences
            });
          }
          duplicates.sort((a, b) => b.count - a.count || a.itemId.localeCompare(b.itemId));
          res.json({
            ok: dangling.length === 0 && duplicates.length === 0,
            checkedAt: (/* @__PURE__ */ new Date()).toISOString(),
            lists: listFiles.length,
            items: itemCount,
            counts: { dangling: dangling.length, duplicates: duplicates.length },
            danglingEdges: dangling,
            duplicateItemIds: duplicates,
            note: "read-only report: archived items count as existing, nothing is rejected on write (see the endpoint comment in server.js)"
          });
        } catch (err) {
          res.status(500).json({ error: "Failed to build the integrity report" });
        }
      });
    };
    module2.exports = { createListRoutes };
  }
});

// tests/_artifacts/_skill_build/lib/items.js
var require_items = __commonJS({
  "tests/_artifacts/_skill_build/lib/items.js"(exports2, module2) {
    "use strict";
    var path2 = require("path");
    var fs2 = require("fs-extra");
    var cfg2 = require_config();
    var util2 = require_util();
    var logging2 = require_logging();
    var paths2 = require_paths();
    var errors = require_errors();
    var { sanitizeItems } = require_schema();
    var { SHARED_LISTS_DIR: SHARED_LISTS_DIR2 } = cfg2;
    var { contentRev: contentRev2, atomicWriteJson: atomicWriteJson2, withLock: withLock2 } = util2;
    var { writeAudit: writeAudit2 } = logging2;
    var createItemRoutes = (app2, io2, deps) => {
      const core = deps.core;
      const {
        getStatusConfig: getStatusConfig2,
        collectStatuses: collectStatuses2,
        sanitizeStatus: sanitizeStatus2,
        validateItems: validateItems2,
        sanitizeRelatesTo: sanitizeRelatesTo2,
        sanitizeLocalDirectories: sanitizeLocalDirectories2
      } = deps;
      const { findItemSlot, requireConfirm: requireConfirm2, changeEvent, actorOf: actorOf2 } = core;
      const itemWrite = async (req, res, op) => {
        const listId = req.params.id;
        const listPath = paths2.listFilePath(listId);
        if (!listPath) return errors.sendError(res, 400, "INVALID_LIST_ID", "Invalid list ID");
        const body = req.body && typeof req.body === "object" ? req.body : {};
        const actor = req.actor || {};
        const userId = actor.userId || null;
        const itemId = req.params.itemId || body.item && body.item.itemId || null;
        try {
          return await withLock2(`list:${listId}`, async () => {
            const data = await fs2.readJson(listPath);
            const serverRev = contentRev2(data.items);
            if (body.baseRev && body.baseRev !== serverRev) {
              return res.status(409).json({
                error: "Conflict: this list was modified by someone else. Reload before saving.",
                code: "REV_CONFLICT",
                serverRev
              });
            }
            const slot = itemId ? findItemSlot(data.items, itemId) : null;
            if (op === "create") {
              const vchk = validateItems2([body.item]);
              if (!vchk.ok) {
                return res.status(400).json({
                  error: `Invalid item data: ${vchk.errors[0].message}` + (vchk.errors.length > 1 ? ` (${vchk.errors.length} total)` : ""),
                  code: "INVALID_ITEM_SCHEMA",
                  violations: vchk.errors.slice(0, 20)
                });
              }
              if (slot) {
                return res.status(409).json({
                  error: `itemId already exists: ${itemId}`,
                  code: "ITEM_EXISTS",
                  itemId
                });
              }
            } else if (op === "delete") {
              if (userId && !actor.isAdmin) {
                return res.status(403).json({
                  error: "Forbidden: Regular users are not allowed to delete items from shared lists. Please close the task instead.",
                  code: "ADMIN_REQUIRED"
                });
              }
              const gate = requireConfirm2(req, `delete item ${itemId}`);
              if (gate) return res.status(400).json(gate);
              if (!slot) {
                return res.status(404).json({ error: "Item not found", code: "ITEM_NOT_FOUND", itemId });
              }
            } else {
              if (!slot) {
                return res.status(404).json({ error: "Item not found", code: "ITEM_NOT_FOUND", itemId });
              }
              const vchk = validateItems2([body.item]);
              if (!vchk.ok) {
                return res.status(400).json({
                  error: `Invalid item data: ${vchk.errors[0].message}` + (vchk.errors.length > 1 ? ` (${vchk.errors.length} total)` : ""),
                  code: "INVALID_ITEM_SCHEMA",
                  violations: vchk.errors.slice(0, 20)
                });
              }
              if (body.item && String(body.item.itemId) !== String(itemId)) {
                return res.status(400).json({
                  error: `itemId does not match path: ${itemId} != ${body.item.itemId}`,
                  code: "ITEM_ID_MISMATCH"
                });
              }
            }
            let prevStatuses = null;
            if (op !== "delete") {
              const sc0 = await getStatusConfig2();
              prevStatuses = collectStatuses2(data.items, sc0);
            }
            let touched = null;
            if (op === "delete") {
              touched = slot.item;
              slot.arr.splice(slot.index, 1);
            } else {
              touched = body.item;
              sanitizeRelatesTo2([touched]);
              sanitizeLocalDirectories2([touched]);
              const sani = sanitizeItems([touched]);
              if (!sani.ok) {
                return res.status(400).json({
                  error: "Comment too long",
                  code: sani.code || "COMMENT_TOO_LONG",
                  limit: sani.limit,
                  actual: sani.actual,
                  itemId: sani.itemId
                });
              }
              const sc = await getStatusConfig2();
              const actorName = actor.username || null;
              const chk = sanitizeStatus2([touched], prevStatuses, sc, userId || null, actorName);
              if (!chk.ok) {
                const v = chk.violation;
                return res.status(400).json({
                  error: `Invalid status transition '${v.from} -> ${v.to}' (${v.title || v.itemId}). Allowed: ${v.allowed.join(" / ")}`,
                  code: "INVALID_TRANSITION",
                  violation: v
                });
              }
              if (op === "create") data.items.push(touched);
              else slot.arr[slot.index] = touched;
            }
            const nextRev = contentRev2(data.items);
            if (nextRev === serverRev) {
              return res.json({
                ok: true,
                rev: nextRev,
                listId,
                item: op === "delete" ? null : touched,
                items: (data.items || []).length
              });
            }
            data.rev = nextRev;
            data.updatedAt = (/* @__PURE__ */ new Date()).toISOString();
            data.updatedBy = userId || null;
            await atomicWriteJson2(listPath, data);
            await writeAudit2({
              actor: userId,
              action: "item-" + op,
              listId,
              confirmed: op === "delete" ? "explicit" : null,
              params: { itemId, title: touched && touched.title },
              note: op === "delete" ? `removed item ${itemId}` : `${op} item ${itemId}`
            });
            io2.emit("items-changed", changeEvent(listId, data.rev, {
              source: "api",
              actor: await actorOf2(userId),
              items: (data.items || []).length,
              op: "item-" + op,
              itemId,
              summary: `${op === "delete" ? "removed" : op === "create" ? "added" : "updated"} item ${itemId}`
            }));
            return res.json({
              ok: true,
              rev: data.rev,
              listId,
              item: op === "delete" ? null : touched,
              items: (data.items || []).length
            });
          });
        } catch (err) {
          if (err && (err.code === "ENOENT" || err.code === "ENOTDIR")) {
            return res.status(404).json({ error: "List not found" });
          }
          console.error("[LiteTask] item write failed:", err);
          return res.status(500).json({ error: "Failed to write item" });
        }
      };
      app2.post("/api/lists/:id/items", async (req, res) => itemWrite(req, res, "create"));
      app2.put("/api/lists/:id/items/:itemId", async (req, res) => itemWrite(req, res, "update"));
      app2.delete("/api/lists/:id/items/:itemId", async (req, res) => itemWrite(req, res, "delete"));
      return { itemWrite };
    };
    module2.exports = { createItemRoutes };
  }
});

// tests/_artifacts/_skill_build/lib/lists_core.js
var require_lists_core = __commonJS({
  "tests/_artifacts/_skill_build/lib/lists_core.js"(exports2, module2) {
    "use strict";
    var path2 = require("path");
    var fs2 = require("fs-extra");
    var crypto2 = require("crypto");
    var cfg2 = require_config();
    var util2 = require_util();
    var paths2 = require_paths();
    var { SHARED_LISTS_DIR: SHARED_LISTS_DIR2, ARCHIVE_DIR: ARCHIVE_DIR2 } = cfg2;
    var { usernameOf: usernameOf2 } = util2;
    var listsETag = (lists2) => '"' + crypto2.createHash("sha256").update(JSON.stringify((lists2 || []).map((l) => [String(l.listId), String(l.rev)]))).digest("hex").slice(0, 16) + '"';
    var answerWithETag = (req, res, etag, body) => {
      res.set("ETag", etag);
      res.set("Cache-Control", "no-cache");
      if (req.headers["if-none-match"] && req.headers["if-none-match"] === etag) {
        return res.status(304).end();
      }
      return res.json(body);
    };
    var actorOf2 = async (userId) => ({
      userId: userId || null,
      username: await usernameOf2(userId) || null
    });
    var changeEvent = (listId, rev, extra) => Object.assign({
      listId,
      rev: rev || null,
      at: (/* @__PURE__ */ new Date()).toISOString()
    }, extra || {});
    var confirmFlag = (req) => {
      const b = req.body && typeof req.body === "object" ? req.body.confirm : void 0;
      const q = req.query ? req.query.confirm : void 0;
      return b === true || q === "true";
    };
    var requireConfirm2 = (req, what, extra) => {
      if (confirmFlag(req)) return null;
      return Object.assign({
        error: "CONFIRMATION_REQUIRED",
        code: "CONFIRMATION_REQUIRED",
        message: `${what}: This operation is irreversible. Please explicitly pass confirm=true (in body or query).`
      }, extra || {});
    };
    var findItemSlot = (items, itemId) => {
      const walk = (arr) => {
        if (!Array.isArray(arr)) return null;
        for (let i = 0; i < arr.length; i++) {
          const it = arr[i];
          if (!it || typeof it !== "object") continue;
          if (String(it.itemId) === String(itemId)) return { arr, index: i, item: it };
          if (Array.isArray(it.subTasks)) {
            const found = walk(it.subTasks);
            if (found) return found;
          }
        }
        return null;
      };
      return walk(items);
    };
    var collectItemIds = (arr, set = /* @__PURE__ */ new Set()) => {
      if (!Array.isArray(arr)) return set;
      for (const it of arr) {
        if (it && it.itemId) set.add(it.itemId);
        if (it && it.subTasks && it.subTasks.length > 0) {
          collectItemIds(it.subTasks, set);
        }
      }
      return set;
    };
    var indexAllItemIds = async () => {
      const index = /* @__PURE__ */ new Map();
      const addDoc = (listId, items) => {
        let set = index.get(listId);
        if (!set) {
          set = /* @__PURE__ */ new Map();
          index.set(listId, set);
        }
        const walk = (arr) => (arr || []).forEach((it) => {
          if (!it || typeof it !== "object") return;
          if (it.itemId) set.set(String(it.itemId), true);
          walk(it.subTasks);
        });
        walk(items);
      };
      const readDir = async (dir) => {
        if (!await fs2.pathExists(dir)) return;
        for (const f of await fs2.readdir(dir)) {
          if (!f.toLowerCase().endsWith(".json")) continue;
          if (!paths2.validateListId(path2.parse(f).name).ok) continue;
          const doc = await fs2.readJson(path2.join(dir, f)).catch(() => null);
          if (!doc) continue;
          addDoc(doc.listId || path2.parse(f).name, doc.items);
        }
      };
      await readDir(SHARED_LISTS_DIR2);
      await readDir(ARCHIVE_DIR2);
      return index;
    };
    module2.exports = {
      listsETag,
      answerWithETag,
      actorOf: actorOf2,
      changeEvent,
      confirmFlag,
      requireConfirm: requireConfirm2,
      findItemSlot,
      collectItemIds,
      indexAllItemIds
    };
  }
});

// tests/_artifacts/_skill_build/lib/lists.js
var require_lists = __commonJS({
  "tests/_artifacts/_skill_build/lib/lists.js"(exports2, module2) {
    "use strict";
    var { createListRoutes } = require_lists_routes();
    var { createItemRoutes } = require_items();
    var core = require_lists_core();
    var _requireConfirm = null;
    var _actorOf = null;
    var register = (app2, io2, deps) => {
      const {
        getStatusConfig: getStatusConfig2,
        collectStatuses: collectStatuses2,
        sanitizeStatus: sanitizeStatus2,
        validateItems: validateItems2,
        sanitizeRelatesTo: sanitizeRelatesTo2,
        sanitizeLocalDirectories: sanitizeLocalDirectories2
      } = deps;
      createListRoutes(app2, io2, {
        core,
        getStatusConfig: getStatusConfig2,
        collectStatuses: collectStatuses2,
        sanitizeStatus: sanitizeStatus2,
        validateItems: validateItems2,
        sanitizeRelatesTo: sanitizeRelatesTo2,
        sanitizeLocalDirectories: sanitizeLocalDirectories2
      });
      createItemRoutes(app2, io2, {
        core,
        getStatusConfig: getStatusConfig2,
        collectStatuses: collectStatuses2,
        sanitizeStatus: sanitizeStatus2,
        validateItems: validateItems2,
        sanitizeRelatesTo: sanitizeRelatesTo2,
        sanitizeLocalDirectories: sanitizeLocalDirectories2
      });
      _requireConfirm = core.requireConfirm;
      _actorOf = core.actorOf;
    };
    module2.exports = {
      register,
      requireConfirm: (...args) => _requireConfirm ? _requireConfirm(...args) : void 0,
      actorOf: (...args) => _actorOf ? _actorOf(...args) : Promise.resolve(void 0)
    };
  }
});

// tests/_artifacts/_skill_build/lib/categories.js
var require_categories = __commonJS({
  "tests/_artifacts/_skill_build/lib/categories.js"(exports2, module2) {
    "use strict";
    var fs2 = require("fs-extra");
    var { CATEGORIES_FILE: CATEGORIES_FILE2 } = require_config();
    var getCategories2 = async () => {
      try {
        if (await fs2.pathExists(CATEGORIES_FILE2)) {
          return await fs2.readJson(CATEGORIES_FILE2);
        }
      } catch (err) {
        console.error("Error reading categories.json:", err);
      }
      return { categories: [], relations: [] };
    };
    module2.exports = { getCategories: getCategories2 };
  }
});

// tests/_artifacts/_skill_build/lib/status.js
var require_status = __commonJS({
  "tests/_artifacts/_skill_build/lib/status.js"(exports2, module2) {
    "use strict";
    var { getCategories: getCategories2 } = require_categories();
    var { stampNow: stampNow2 } = require_util();
    var DEFAULT_STATUSES = [
      { value: "open", label: "Open", color: "#64748b", closed: false },
      { value: "in-progress", label: "In Progress", color: "#2563eb", closed: false },
      { value: "blocked", label: "Blocked", color: "#e11d48", closed: false },
      { value: "verified", label: "Verified", color: "#7c3aed", closed: false },
      { value: "done", label: "Done", color: "#059669", closed: true }
    ];
    var DEFAULT_STATUS_FLOW = {
      "open": ["in-progress", "blocked", "done"],
      "in-progress": ["open", "blocked", "verified", "done"],
      "blocked": ["open", "in-progress", "done"],
      "verified": ["in-progress", "blocked", "done"],
      "done": ["open", "in-progress", "blocked", "verified"]
    };
    var STATUS_HISTORY_LIMIT = 20;
    var getStatusConfig2 = async () => {
      const cfg2 = await getCategories2();
      const statuses = Array.isArray(cfg2.statuses) && cfg2.statuses.length ? cfg2.statuses : DEFAULT_STATUSES;
      const flow = cfg2.statusFlow && typeof cfg2.statusFlow === "object" && !Array.isArray(cfg2.statusFlow) ? cfg2.statusFlow : DEFAULT_STATUS_FLOW;
      const values = statuses.map((s) => String(s.value));
      const closedValues = statuses.filter((s) => s && s.closed).map((s) => String(s.value));
      const closedSet = new Set(closedValues.length ? closedValues : ["done"]);
      return { statuses, flow, values, closedSet };
    };
    var deriveStatus = (it, cfg2) => {
      const v = typeof it?.status === "string" ? it.status : null;
      if (v && cfg2.values.includes(v)) return v;
      return it?.isDone ? "done" : "open";
    };
    var collectStatuses2 = (items, cfg2, out = /* @__PURE__ */ new Map()) => {
      if (!Array.isArray(items)) return out;
      for (const it of items) {
        if (!it || typeof it !== "object") continue;
        if (it.itemId) out.set(String(it.itemId), deriveStatus(it, cfg2));
        if (Array.isArray(it.subTasks)) collectStatuses2(it.subTasks, cfg2, out);
      }
      return out;
    };
    var sanitizeStatus2 = (items, prevStatuses, cfg2, actorId, actorName) => {
      const walk = (arr) => {
        if (!Array.isArray(arr)) return null;
        for (const it of arr) {
          if (!it || typeof it !== "object") continue;
          const prev = it.itemId && prevStatuses.has(String(it.itemId)) ? prevStatuses.get(String(it.itemId)) : deriveStatus(it, cfg2);
          let next = typeof it.status === "string" ? it.status : prev;
          if (!cfg2.values.includes(next)) next = it.isDone ? "done" : "open";
          if (next !== prev) {
            const allowed = Array.isArray(cfg2.flow[prev]) ? cfg2.flow[prev] : null;
            if (allowed && !allowed.includes(next)) {
              return { itemId: it.itemId || null, title: it.title || "", from: prev, to: next, allowed };
            }
          }
          it.status = next;
          const isClosed = cfg2.closedSet.has(next);
          it.isDone = isClosed;
          if (isClosed) {
            if (!it.closedAt) it.closedAt = stampNow2();
            if (!it.closedBy && actorName) it.closedBy = actorName;
            if (!it.closedById && actorId) it.closedById = actorId;
          } else {
            it.closedBy = null;
            it.closedById = null;
            it.closedAt = null;
          }
          if (next !== prev) {
            const hist = Array.isArray(it.statusHistory) ? it.statusHistory.filter((h) => h && typeof h === "object") : [];
            hist.push({ from: prev, to: next, at: stampNow2(), by: actorId || null });
            it.statusHistory = hist.slice(-STATUS_HISTORY_LIMIT);
          } else if (!Array.isArray(it.statusHistory)) {
            it.statusHistory = [];
          }
          if (typeof it.blockedReason !== "string") it.blockedReason = it.blockedReason ? String(it.blockedReason) : "";
          const bad2 = walk(it.subTasks);
          if (bad2) return bad2;
        }
        return null;
      };
      const bad = walk(items);
      return bad ? { ok: false, violation: bad } : { ok: true };
    };
    module2.exports = { getStatusConfig: getStatusConfig2, deriveStatus, collectStatuses: collectStatuses2, sanitizeStatus: sanitizeStatus2 };
  }
});

// tests/_artifacts/_skill_build/lib/bootstrap.js
var require_bootstrap = __commonJS({
  "tests/_artifacts/_skill_build/lib/bootstrap.js"(exports2, module2) {
    "use strict";
    var fs2 = require("fs-extra");
    var path2 = require("path");
    var cfg2 = require_config();
    var { getCategories: getCategories2 } = require_categories();
    var { withLock: withLock2, atomicWriteJson: atomicWriteJson2 } = require_util();
    var { USERS_FILE: USERS_FILE2, SHARED_LISTS_DIR: SHARED_LISTS_DIR2, DATA_DIR: DATA_DIR2, HASH_SCHEME: HASH_SCHEME2, hashPassword: hashPassword2, isHashedPassword: isHashedPassword2 } = cfg2;
    var saveUsers2 = async (users) => withLock2("users", async () => {
      await atomicWriteJson2(USERS_FILE2, users);
    });
    var migrateUserPasswords2 = async () => {
      try {
        const users = await fs2.readJson(USERS_FILE2);
        let upgraded = 0;
        let repaired = 0;
        for (const u of users) {
          if (isHashedPassword2(u.password)) {
            const parts = String(u.password).split("$").filter((s) => s !== "");
            const canonical = parts.length === 6 && parts[0] === HASH_SCHEME2 ? parts.join("$") : null;
            if (canonical && canonical !== u.password) {
              u.password = canonical;
              repaired++;
            }
            continue;
          }
          {
            let plain = "";
            try {
              plain = Buffer.from(String(u.password || ""), "base64").toString("utf-8");
            } catch {
              plain = "";
            }
            if (!plain) continue;
            u.password = hashPassword2(plain);
            upgraded++;
          }
        }
        if (upgraded > 0 || repaired > 0) {
          await saveUsers2(users);
          console.log(`[LiteTask] Password store (B2): ${upgraded} upgraded to scrypt, ${repaired} repaired to canonical form.`);
        }
        return upgraded + repaired;
      } catch (err) {
        console.error("[LiteTask] Password migration failed:", err.message);
        return 0;
      }
    };
    var initSharedLists2 = async () => {
      try {
        const files = await fs2.readdir(SHARED_LISTS_DIR2);
        const jsonLists = files.filter((f) => f.endsWith(".json"));
        if (jsonLists.length === 0) {
          const adminDir = path2.join(DATA_DIR2, "users", "user_admin");
          if (await fs2.pathExists(adminDir)) {
            const adminFiles = await fs2.readdir(adminDir);
            for (const f of adminFiles) {
              if (f.endsWith(".json")) {
                const listData = await fs2.readJson(path2.join(adminDir, f));
                if (Array.isArray(listData.items)) {
                  listData.items.forEach((item) => {
                    if (!item.createdBy) item.createdBy = "admin";
                    if (!item.createdAt) item.createdAt = "2026-03-23 10:00";
                    if (item.isDone && !item.closedBy) {
                      item.closedBy = "admin";
                      item.closedAt = "2026-03-23 12:00";
                    }
                  });
                }
                await fs2.writeJson(path2.join(SHARED_LISTS_DIR2, f), listData, { spaces: 2 });
              }
            }
          }
        }
      } catch (err) {
        console.error("Error initializing shared lists:", err);
      }
    };
    var initCategories2 = async () => {
      try {
        const cfg3 = await getCategories2();
        const cats = Array.isArray(cfg3.categories) ? cfg3.categories : [];
        const now = /* @__PURE__ */ new Date();
        const pad = (n) => String(n).padStart(2, "0");
        const createdAt = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
        for (const cat of cats) {
          const listPath = path2.join(SHARED_LISTS_DIR2, `${cat.listId}.json`);
          if (await fs2.pathExists(listPath)) continue;
          const list = {
            listId: cat.listId,
            listName: cat.name || cat.type,
            category: cat.type,
            owner: "admin",
            createdAt,
            items: []
          };
          await fs2.writeJson(listPath, list, { spaces: 2 });
          console.log(`Provisioned category list: ${cat.listId} (${cat.name || cat.type})`);
        }
      } catch (err) {
        console.error("Error initializing category lists:", err);
      }
    };
    module2.exports = { saveUsers: saveUsers2, migrateUserPasswords: migrateUserPasswords2, initSharedLists: initSharedLists2, initCategories: initCategories2 };
  }
});

// tests/_artifacts/_skill_build/server.js
var express = require("express");
var http = require("http");
var os = require("os");
var crypto = require("crypto");
var fs = require("fs-extra");
var path = require("path");
var chokidar = require("chokidar");
var { Server } = require("socket.io");
var paths = require_paths();
var guards = require_guard();
var openFolder = require_open_folder();
var originPolicy = require_origin_policy();
var socketGate = require_socket_gate();
var backupModule = require_backup();
var shutdown = require_shutdown();
var csp = require_csp();
var app = express();
var server = http.createServer(app);
var io = new Server(server);
app.use(guards.loopbackGuard);
var cfg = require_config();
var util = require_util();
var logging = require_logging();
var archive = require_archive();
var links = require_links();
var actors = require_actors();
var lists = require_lists();
var categories = require_categories();
var status = require_status();
var schema = require_schema();
var bootstrap = require_bootstrap();
var { requireConfirm, actorOf } = lists;
var {
  getCategories
} = categories;
var {
  getStatusConfig,
  collectStatuses,
  sanitizeStatus
} = status;
var {
  sanitizeRelatesTo,
  sanitizeLocalDirectories,
  validateItems
} = schema;
var {
  saveUsers,
  initSharedLists,
  initCategories,
  migrateUserPasswords
} = bootstrap;
var {
  DATA_DIR,
  USERS_FILE,
  PASSWORDLESS_LOCAL,
  SHARED_LISTS_DIR,
  CATEGORIES_FILE,
  ARCHIVE_DIR,
  BACKUP_DIR,
  ARCHIVE_SNAPSHOT_DIR,
  MAX_ARCHIVE_SNAPSHOTS,
  AUTO_ARCHIVE_ENABLED,
  AUTO_ARCHIVE_ENV_MIN,
  DEFAULT_AUTO_ARCHIVE_MIN_CLOSED,
  DEFAULT_ARCHIVE_WARN_WITHIN,
  SCRYPT_N,
  SCRYPT_R,
  SCRYPT_P,
  KEY_LEN,
  HASH_SCHEME,
  HASH_PREFIX,
  isHashedPassword,
  hashPassword,
  verifyPassword,
  safeEqual,
  JSON_BODY_LIMIT,
  contentRev,
  withLock,
  atomicWriteJson,
  DIFF_FIELD_LABELS,
  DIFF_IGNORE_KEYS,
  normVal,
  stableEqual,
  flattenItems,
  diffItems,
  stampNow,
  isUserAdmin,
  usernameOf,
  writeAudit,
  LOG_DIR,
  LOG_FILE,
  AUDIT_FILE,
  STARTED_AT,
  SECURITY_MODEL,
  DEV_AUTO_LOGIN,
  MIRROR_DIR,
  BACKUP_STAMP_RE,
  BACKUP_KEEP,
  backupAllJson,
  BIND_HOST,
  REACHABILITY
} = Object.assign({}, cfg, util, logging);
var SITE = {};
var SITE_CFG = cfg.resolveSiteConfigPath();
try {
  SITE = fs.readJsonSync(SITE_CFG.path);
  if (typeof SITE !== "object" || SITE === null) SITE = {};
} catch (err) {
  SITE = {};
}
var BRAND = SITE.logPrefix && String(SITE.logPrefix).trim() || "ADLM";
var LP = BRAND;
var OPEN_ROOTS = openFolder.resolveAllowedRoots(SITE.project && SITE.project.root);
var ALLOW_ORIGINS = originPolicy.parseAllowList(process.env.LITETASK_SOCKET_ALLOW_ORIGINS);
app.use(express.json({ limit: JSON_BODY_LIMIT }));
app.use(csp.createCspMiddleware({ htmlPath: path.join(__dirname, "public", "index.html") }));
app.use(express.static(path.join(__dirname, "public")));
app.use("/api", guards.createAuthGate());
app.use("/api/lists/:id", paths.listIdParamGuard);
app.use("/api/archive/:id", paths.listIdParamGuard);
fs.ensureDirSync(DATA_DIR);
fs.ensureDirSync(SHARED_LISTS_DIR);
if (!fs.existsSync(USERS_FILE)) {
  const a = SITE.admin && typeof SITE.admin === "object" ? SITE.admin : {};
  const defaultUsers = [{
    userId: a.userId || "user_admin",
    username: a.username || "admin",
    password: hashPassword(a.password || "admin"),
    isAdmin: true
  }];
  fs.writeJsonSync(USERS_FILE, defaultUsers, { spaces: 2 });
}
initSharedLists();
initCategories();
migrateUserPasswords();
var watcher = chokidar.watch([SHARED_LISTS_DIR, USERS_FILE], {
  ignored: /(^|[\/\\])\../,
  persistent: true,
  ignoreInitial: true
});
watcher.on("all", async (event, filePath) => {
  if (!filePath.endsWith(".json")) return;
  const listId = path.basename(filePath, ".json");
  const payload = { listId, rev: null, source: "file", at: (/* @__PURE__ */ new Date()).toISOString() };
  try {
    const doc = await fs.readJson(filePath);
    if (doc && Array.isArray(doc.items)) payload.rev = contentRev(doc.items);
    payload.actor = await actorOf(doc && doc.updatedBy);
  } catch (err) {
  }
  io.emit("file-changed", payload);
});
io.on("connection", (socket) => {
  socket.emit("resync");
});
actors.register(app, io, { saveUsers });
links.register(app, io, { getCategories, getStatusConfig });
lists.register(app, io, { getStatusConfig, collectStatuses, sanitizeStatus, validateItems, sanitizeRelatesTo, sanitizeLocalDirectories });
archive.register(app, io, { requireConfirm, getCategories, writeAudit });
openFolder.register(app, { roots: OPEN_ROOTS.roots, writeAudit });
logging.register(app, io, {
  site: SITE,
  openFolder: { configured: OPEN_ROOTS.configured, rootCount: OPEN_ROOTS.roots.length }
});
socketGate.installSocketGate(io, { allowOrigins: ALLOW_ORIGINS });
shutdown.installShutdown({ server, io, watcher, brand: LP });
var PORT = process.env.PORT || (SITE.port && Number(SITE.port) > 0 ? Number(SITE.port) : 3e3);
server.on("error", (err) => {
  if (err.code === "EADDRINUSE") {
    console.error(
      `
[${LP}] ERROR: Port ${PORT} is already in use.
  Another ${BRAND} instance may already be running.
  Stop it first, or start on a different port:
    PORT=${Number(PORT) + 1} node server.js
`
    );
  } else {
    console.error(`[${LP}] ERROR: cannot bind to ${BIND_HOST}:${PORT} (${err.code || err.message})`);
  }
  process.exit(1);
});
server.listen(PORT, BIND_HOST, async () => {
  console.log(`Server running on http://localhost:${PORT}`);
  console.log(`[${LP}] bind=${BIND_HOST} reachability=${REACHABILITY} mode=${PASSWORDLESS_LOCAL ? "local-passwordless" : "shared-authenticated"}`);
  if (REACHABILITY === "non-loopback") {
    console.warn(`[${LP}] WARNING: listening on a non-loopback address (${BIND_HOST}); the service is reachable from the network.`);
  }
  if (SITE_CFG.redirected) {
    console.log(`[${LP}] site config redirected: ${SITE_CFG.path}`);
  }
  const legacyKeys = cfg.describeLegacySiteConfig(SITE);
  if (legacyKeys.length) {
    console.warn(`[${LP}] WARNING: Deprecated fields ${legacyKeys.join(",")} ignored; security mode is controlled exclusively by LITETASK_DEV_LOGIN (set to 0 for shared auth).`);
  }
  const mirrorCfg = backupModule.MIRROR_CONFIG;
  if (mirrorCfg.enabled) {
    console.log(`[${LP}] backup-mirror: enabled -> ${mirrorCfg.dir}`);
  } else if (mirrorCfg.reason === "unset") {
    console.log(`[${LP}] Mirror backup disabled by default (enable via LITETASK_BACKUP_MIRROR=<absolute-path>)`);
  } else if (mirrorCfg.reason === "explicit-off") {
    console.log(`[${LP}] Mirror backup explicitly disabled (${mirrorCfg.reason})`);
  } else {
    console.warn(`[${LP}] Invalid mirror backup config, treated as disabled (${mirrorCfg.reason})`);
  }
  if (ALLOW_ORIGINS.empty) {
    console.log(`[${LP}] Origin whitelist empty: cross-origin Sockets rejected`);
  } else if (ALLOW_ORIGINS.invalid.length) {
    console.warn(`[${LP}] Invalid origin whitelist, cleared: ${ALLOW_ORIGINS.invalid.join(",")}`);
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
    console.warn(`[${LP}] Startup backup failed:`, err.message);
  }
  archive.autoArchiveSweep();
});
