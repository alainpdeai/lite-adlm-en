'use strict';
const path = require('path');
const fs = require('fs-extra');
const crypto = require('crypto');

const cfg = require('./config');
const util = require('./util');
const paths = require('./paths');

const { SHARED_LISTS_DIR, ARCHIVE_DIR } = cfg;
const { usernameOf } = util;

// Lists/Items helpers (route ①, Round 9). Pure or near-pure building blocks shared
// by the list routes and the item routes: ETag handling, the actor/change-event
// shape, the confirmation gate, tree lookups and the integrity index.
//
// ARCHIVE_DIR is imported here on purpose: indexAllItemIds() scans both the live
// lists and the archive, and the Round-5 extraction carried the call over without
// the constant, which made GET /api/integrity answer 500 on every call.

// Incremental sync P3-A: a hash of the revisions a payload carries, so a client that
// already holds it can be answered with 304 — no payload, no parse, no render.
const listsETag = (lists) => '"' + crypto.createHash('sha256')
    .update(JSON.stringify((lists || []).map(l => [String(l.listId), String(l.rev)])))
    .digest('hex').slice(0, 16) + '"';

const answerWithETag = (req, res, etag, body) => {
    res.set('ETag', etag);
    // no-cache, not no-store: always revalidate, never serve a stale board.
    res.set('Cache-Control', 'no-cache');
    // Express would answer the conditional GET on its own (res.json checks
    // freshness and sets a weak body-derived ETag when none was set). The
    // explicit branch is still worth having: by then Express has already
    // serialised the whole payload to compute that tag, and skipping the
    // serialisation of ~500 kB per poll per tab is the point of the exercise.
    // The tag is ours (content-derived) either way — mutation-tested in
    // grade_assertion_quality.py.
    if (req.headers['if-none-match'] && req.headers['if-none-match'] === etag) {
        return res.status(304).end();
    }
    return res.json(body);
};

const actorOf = async (userId) => ({
    userId: userId || null,
    username: (await usernameOf(userId)) || null,
});

const changeEvent = (listId, rev, extra) => Object.assign({
    listId,
    rev: rev || null,
    at: new Date().toISOString(),
}, extra || {});

/* ---------------------------------------------------------------------------
 * Security Boundary P2-C Hard Gate (2026-10-31): confirmation is REQUIRED, not optional.
 *
 * Until now the rule was "an explicit `confirm: false` is refused; an omitted
 * field means the UI already asked". That cannot tell apart the two callers
 * that matter: the UI, which did ask, and a script that never saw a dialog and
 * simply left the field out. Both send the same request — and the second one is
 * exactly the shape of the 2026-10-29 `arch` loss.
 *
 * The gate is therefore inverted: a destructive operation needs an affirmative
 * `confirm: true`. Omitted, false, null, "yes" — all of them are a refusal.
 * The price is that every caller must say so out loud. Every caller lives in
 * this repository (one CLI, one UI, the graders) and all of them were updated
 * in the same change, which is what makes "nothing can destroy data by
 * accident" a verifiable claim instead of an aspiration.
 *
 * `confirm` is read from the body *or* the query string: the UI's delete-list
 * call carries no body, and a gate that reads only one of the two is a gate a
 * caller can walk around without meaning to.
 * ------------------------------------------------------------------------- */
const confirmFlag = (req) => {
    const b = req.body && typeof req.body === 'object' ? req.body.confirm : undefined;
    const q = req.query ? req.query.confirm : undefined;
    return b === true || q === 'true';
};

// Returns null when the caller confirmed, otherwise the 400 body to answer with.
const requireConfirm = (req, what, extra) => {
    if (confirmFlag(req)) return null;
    return Object.assign({
        error: 'CONFIRMATION_REQUIRED',
        code: 'CONFIRMATION_REQUIRED',
        message: `${what}: This operation is irreversible. Please explicitly pass confirm=true (in body or query).`,
    }, extra || {});
};

// Walks the item tree (top level + subTasks) and returns the { arr, index, item }
// slot holding `itemId`, or null. `arr` is the live array the item sits in, so a
// caller can splice or replace in place.
const findItemSlot = (items, itemId) => {
    const walk = (arr) => {
        if (!Array.isArray(arr)) return null;
        for (let i = 0; i < arr.length; i++) {
            const it = arr[i];
            if (!it || typeof it !== 'object') continue;
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

// Every itemId reachable from `arr`, subtasks included.
const collectItemIds = (arr, set = new Set()) => {
    if (!Array.isArray(arr)) return set;
    for (const it of arr) {
        if (it && it.itemId) set.add(it.itemId);
        if (it && it.subTasks && it.subTasks.length > 0) {
            collectItemIds(it.subTasks, set);
        }
    }
    return set;
};

// Integrity Report P3-D + P3-E: listId -> Map(itemId -> true) across the live lists AND
// the archive. Archived items still exist, so F3 can keep counting them as
// coverage evidence; leaving them out would report those edges as dangling.
const indexAllItemIds = async () => {
    const index = new Map();          // listId -> Map(itemId -> true)
    const addDoc = (listId, items) => {
        let set = index.get(listId);
        if (!set) { set = new Map(); index.set(listId, set); }
        const walk = (arr) => (arr || []).forEach(it => {
            if (!it || typeof it !== 'object') return;
            if (it.itemId) set.set(String(it.itemId), true);
            walk(it.subTasks);
        });
        walk(items);
    };
    const readDir = async (dir) => {
        if (!(await fs.pathExists(dir))) return;
        for (const f of await fs.readdir(dir)) {
            if (!f.toLowerCase().endsWith('.json')) continue;
            if (!paths.validateListId(path.parse(f).name).ok) continue;
            const doc = await fs.readJson(path.join(dir, f)).catch(() => null);
            if (!doc) continue;
            addDoc(doc.listId || path.parse(f).name, doc.items);
        }
    };
    await readDir(SHARED_LISTS_DIR);
    await readDir(ARCHIVE_DIR);       // archived items still EXIST
    return index;
};

module.exports = {
    listsETag,
    answerWithETag,
    actorOf,
    changeEvent,
    confirmFlag,
    requireConfirm,
    findItemSlot,
    collectItemIds,
    indexAllItemIds,
};
