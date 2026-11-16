'use strict';
const fs = require('fs-extra');
const path = require('path');

const cfg = require('./config');
const util = require('./util');
const logging = require('./logging');
const session = require('./session');
const errors = require('./errors');

const {
    USERS_FILE, DATA_DIR, PASSWORDLESS_LOCAL, SHARED_LISTS_DIR,
    hashPassword, verifyPassword, isHashedPassword
} = cfg;
const { isUserAdminOf, adminFlags } = util;
const { writeAudit } = logging;

const register = (app, io, deps) => {
    const saveUsers = deps.saveUsers;

    // Auth API. Local mode ignores the password; shared mode enforces it and,
    // on success, issues an HTTP-only server-side session.
    app.post('/api/login', async (req, res) => {
        try {
            const { username, password } = req.body || {};
            const users = await fs.readJson(USERS_FILE);
            const user = users.find(u => u.username === username
                && (PASSWORDLESS_LOCAL || verifyPassword(password, u.password)));
            if (!user) {
                return res.status(401).json({
                    error: 'Invalid credentials', code: 'INVALID_CREDENTIALS',
                });
            }
            if (!PASSWORDLESS_LOCAL) {
                const issued = session.issueSession(user.userId);
                res.set('Set-Cookie', issued.cookie);
            }
            res.json({
                userId: user.userId,
                username: user.username,
                isAdmin: isUserAdminOf(user),
            });
        } catch (err) {
            res.status(500).json({ error: 'Login failed', code: 'INTERNAL' });
        }
    });

    // Idempotent logout: destroy the session if one is present, clear the cookie.
    app.post('/api/logout', (req, res) => {
        const cookies = session.parseCookies(req.headers && req.headers.cookie);
        const v = session.verifySession(cookies[session.SESSION_COOKIE]);
        if (v.ok) session.destroySession(v.sid);
        res.set('Set-Cookie', session.buildClearCookie());
        res.json({ success: true });
    });

    // P2-7: shared mode may not enumerate the whole user store. A regular
    // member sees themself plus people who share a list they participate in.
    // Local mode and administrators keep the full list (P0 red line: local
    // GET /api/users stays 200 without a session).
    const collectRefs = (items, refs) => {
        for (const it of (items || [])) {
            if (!it || typeof it !== 'object') continue;
            for (const k of ['createdBy', 'assignedTo', 'closedBy']) {
                if (typeof it[k] === 'string' && it[k]) refs.names.add(it[k]);
            }
            for (const k of ['createdById', 'closedById']) {
                if (typeof it[k] === 'string' && it[k]) refs.ids.add(it[k]);
            }
            collectRefs(it.subTasks, refs);
        }
    };

    const participates = (items, actor) => {
        for (const it of (items || [])) {
            if (!it || typeof it !== 'object') continue;
            if ((it.createdById && it.createdById === actor.userId)
                || (it.createdBy && it.createdBy === actor.username)
                || (it.assignedTo && it.assignedTo === actor.username)
                || (it.closedById && it.closedById === actor.userId)
                || (it.closedBy && it.closedBy === actor.username)) return true;
            if (participates(it.subTasks, actor)) return true;
        }
        return false;
    };

    const visibleUsersFor = async (actor) => {
        const users = await fs.readJson(USERS_FILE);
        const a = actor || {};
        if (PASSWORDLESS_LOCAL || a.isAdmin) return users;

        const names = new Set();
        const ids = new Set();
        if (a.userId) ids.add(a.userId);
        if (a.username) names.add(a.username);

        let files = [];
        try {
            files = (await fs.readdir(SHARED_LISTS_DIR))
                .filter(f => f.toLowerCase().endsWith('.json'));
        } catch (err) {
            console.warn('[LiteTask] visibility read failed; returning self only:', err.message);
            return users.filter(u => (a.userId && u.userId === a.userId)
                || (a.username && u.username === a.username));
        }

        for (const f of files) {
            try {
                const doc = await fs.readJson(path.join(SHARED_LISTS_DIR, f));
                if (!participates(doc.items, a)) continue;
                const refs = { names: new Set(), ids: new Set() };
                collectRefs(doc.items, refs);
                for (const n of refs.names) names.add(n);
                for (const id of refs.ids) ids.add(id);
            } catch (_err) { /* one unreadable list must not widen the result */ }
        }
        return users.filter(u => ids.has(u.userId) || names.has(u.username));
    };

    // Team users list for task assignments (username and userId only)
    app.get('/api/users', async (req, res) => {
        try {
            const users = await visibleUsersFor(req.actor || {});
            const list = users.map(u => ({
                userId: u.userId,
                username: u.username
            }));
            res.json(list);
        } catch (err) {
            res.status(500).json({ error: 'Failed to read users' });
        }
    });

    // Admin gate: identity and role come from req.actor (session or a stored,
    // declared identity), never from a request-supplied adminUserId.
    const adminOnly = (req, res) => {
        const actor = req.actor || {};
        if (!actor.isAdmin) {
            errors.sendError(res, 403, 'ADMIN_REQUIRED', 'Forbidden: Admin access required');
            return false;
        }
        return true;
    };

    app.get('/api/admin/users', async (req, res) => {
        if (!adminOnly(req, res)) return;
        try {
            const users = await fs.readJson(USERS_FILE);
            const sharedFiles = await fs.readdir(SHARED_LISTS_DIR);
            const allItems = [];
            for (const file of sharedFiles) {
                if (file.endsWith('.json')) {
                    const listData = await fs.readJson(path.join(SHARED_LISTS_DIR, file));
                    if (Array.isArray(listData.items)) {
                        allItems.push(...listData.items);
                    }
                }
            }
            const admins = adminFlags(users);
            const enriched = users.map(u => {
                const tasksCreated = allItems.filter(it => it.createdBy === u.username || it.createdById === u.userId).length;
                const tasksClosed = allItems.filter(it => it.closedBy === u.username || it.closedById === u.userId).length;
                // B2: never return the stored credential. Only expose which scheme is in use.
                return {
                    userId: u.userId,
                    username: u.username,
                    isAdmin: admins.has(String(u.userId)),
                    tasksCreated,
                    tasksClosed,
                    passwordScheme: isHashedPassword(u.password) ? 'scrypt' : 'legacy',
                    passwordRecoverable: false
                };
            });
            res.json(enriched);
        } catch (err) {
            res.status(500).json({ error: 'Failed to read users' });
        }
    });

    app.post('/api/admin/reset-password', async (req, res) => {
        if (!adminOnly(req, res)) return;
        const { targetUserId, newPassword } = req.body || {};
        if (!newPassword || typeof newPassword !== 'string' || newPassword.trim().length === 0) {
            return res.status(400).json({ error: 'New password cannot be empty' });
        }
        try {
            const users = await fs.readJson(USERS_FILE);
            const targetIndex = users.findIndex(u => u.userId === targetUserId);
            if (targetIndex === -1) {
                return res.status(404).json({ error: 'Target user not found' });
            }
            users[targetIndex].password = hashPassword(newPassword.trim());
            await saveUsers(users);
            // Security Boundary P2-A: record that a password was reset — never what it was
            // reset to. Params are an explicit allowlist, not the request body.
            await writeAudit({
                actor: (req.actor && req.actor.userId) || null,
                action: 'reset-password',
                params: { targetUserId },
                note: `password reset for ${users[targetIndex].username}`,
            });
            res.json({ success: true, message: `Password for ${users[targetIndex].username} reset successfully.` });
        } catch (err) {
            res.status(500).json({ error: 'Failed to update password' });
        }
    });

    app.post('/api/admin/users', async (req, res) => {
        if (!adminOnly(req, res)) return;
        const { username, password, isAdmin } = req.body || {};
        if (!username || !password || !username.trim() || !password.trim()) {
            return res.status(400).json({ error: 'Username and password cannot be empty' });
        }
        const cleanUsername = username.trim();
        const cleanPassword = password.trim();
        if (cleanUsername.length < 2) {
            return res.status(400).json({ error: 'Username must be at least 2 characters long' });
        }
        if (cleanPassword.length < 3) {
            return res.status(400).json({ error: 'Password must be at least 3 characters long' });
        }
        try {
            const users = await fs.readJson(USERS_FILE);
            if (users.find(u => u.username.toLowerCase() === cleanUsername.toLowerCase())) {
                return res.status(400).json({ error: `Username "${cleanUsername}" already exists` });
            }
            const userId = 'user_' + Date.now();
            const newUser = {
                userId,
                username: cleanUsername,
                password: hashPassword(cleanPassword),
                isAdmin: Boolean(isAdmin)
            };
            users.push(newUser);
            await saveUsers(users);
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
            res.status(500).json({ error: 'Failed to create user' });
        }
    });

    app.delete('/api/admin/users/:userId', async (req, res) => {
        if (!adminOnly(req, res)) return;
        const actor = req.actor || {};
        const targetUserId = req.params.userId;
        if (targetUserId === 'user_admin' || targetUserId === actor.userId) {
            return res.status(400).json({ error: 'Cannot delete primary admin account' });
        }
        try {
            let users = await fs.readJson(USERS_FILE);
            users = users.filter(u => u.userId !== targetUserId);
            await saveUsers(users);
            session.destroySessionsForUser(targetUserId);
            const legacyUserDir = path.join(DATA_DIR, 'users', targetUserId);
            if (await fs.pathExists(legacyUserDir)) {
                await fs.remove(legacyUserDir);
            }
            await writeAudit({
                actor: actor.userId || null, action: 'delete-user',
                params: { targetUserId },
                note: 'user account removed',
            });
            res.json({ success: true });
        } catch (err) {
            res.status(500).json({ error: 'Failed to delete user' });
        }
    });

};

module.exports = { register };