'use strict';

const fs = require('fs-extra');
const path = require('path');

const cfg = require('./config');
const { getCategories } = require('./categories');
const { withLock, atomicWriteJson } = require('./util');

const { USERS_FILE, SHARED_LISTS_DIR, DATA_DIR, HASH_SCHEME, hashPassword, isHashedPassword } = cfg;

// Single guarded entry point for every users.json write (B3)
const saveUsers = async (users) => withLock('users', async () => {
    await atomicWriteJson(USERS_FILE, users);
});

// One-time startup migration: rewrite legacy base64 passwords as scrypt hashes
const migrateUserPasswords = async () => {
    try {
        const users = await fs.readJson(USERS_FILE);
        let upgraded = 0;
        let repaired = 0;
        for (const u of users) {
            if (isHashedPassword(u.password)) {
                // Rewrite non-canonical hash records (e.g. "scrypt$$N$r$p$…")
                const parts = String(u.password).split('$').filter(s => s !== '');
                const canonical = (parts.length === 6 && parts[0] === HASH_SCHEME) ? parts.join('$') : null;
                if (canonical && canonical !== u.password) {
                    u.password = canonical;
                    repaired++;
                }
                continue;
            }
            {
                let plain = '';
                try { plain = Buffer.from(String(u.password || ''), 'base64').toString('utf-8'); } catch { plain = ''; }
                if (!plain) continue;
                u.password = hashPassword(plain);
                upgraded++;
            }
        }
        if (upgraded > 0 || repaired > 0) {
            await saveUsers(users);
            console.log(`[LiteTask] Password store (B2): ${upgraded} upgraded to scrypt, ${repaired} repaired to canonical form.`);
        }
        return upgraded + repaired;
    } catch (err) {
        console.error('[LiteTask] Password migration failed:', err.message);
        return 0;
    }
};

// Migrate legacy admin/user lists to shared lists if shared lists are empty
const initSharedLists = async () => {
    try {
        const files = await fs.readdir(SHARED_LISTS_DIR);
        const jsonLists = files.filter(f => f.endsWith('.json'));
        if (jsonLists.length === 0) {
            // Check legacy admin folder
            const adminDir = path.join(DATA_DIR, 'users', 'user_admin');
            if (await fs.pathExists(adminDir)) {
                const adminFiles = await fs.readdir(adminDir);
                for (const f of adminFiles) {
                    if (f.endsWith('.json')) {
                        const listData = await fs.readJson(path.join(adminDir, f));
                        if (Array.isArray(listData.items)) {
                            listData.items.forEach(item => {
                                if (!item.createdBy) item.createdBy = 'admin';
                                if (!item.createdAt) item.createdAt = '2026-03-23 10:00';
                                if (item.isDone && !item.closedBy) {
                                    item.closedBy = 'admin';
                                    item.closedAt = '2026-03-23 12:00';
                                }
                            });
                        }
                        await fs.writeJson(path.join(SHARED_LISTS_DIR, f), listData, { spaces: 2 });
                    }
                }
            }
            // A fresh install is seeded ONLY from categories.json (see initCategories
            // below) — no hardcoded welcome/default list, so the first-run data
            // stays clean and fully category-driven. Legacy admin-folder migration
            // above is preserved for existing deployments upgrading their data dir.
        }
    } catch (err) {
        console.error("Error initializing shared lists:", err);
    }
};

// Provision the category lists defined in categories.json — only when missing,
// so existing lists (e.g. 01-04.json) are never overwritten.
const initCategories = async () => {
    try {
        const cfg = await getCategories();
        const cats = Array.isArray(cfg.categories) ? cfg.categories : [];
        const now = new Date();
        const pad = (n) => String(n).padStart(2, '0');
        const createdAt = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
        for (const cat of cats) {
            const listPath = path.join(SHARED_LISTS_DIR, `${cat.listId}.json`);
            if (await fs.pathExists(listPath)) continue; // never overwrite
            const list = {
                listId: cat.listId,
                listName: cat.name || cat.type,
                category: cat.type,
                owner: 'admin',
                createdAt,
                items: []
            };
            await fs.writeJson(listPath, list, { spaces: 2 });
            console.log(`Provisioned category list: ${cat.listId} (${cat.name || cat.type})`);
        }
    } catch (err) {
        console.error("Error initializing category lists:", err);
    }
};

module.exports = { saveUsers, migrateUserPasswords, initSharedLists, initCategories };
