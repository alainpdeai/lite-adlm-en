#!/usr/bin/env node
'use strict';

// Validator for the initialization knowledge pack + (if present) live task data.
// This is what turns the taxonomy / note / anchor specs into a code-level gate.
//
//   npm run validate            # WARN tolerated, FAIL => exit 1
//   npm run validate -- --strict # WARN also fails
//
// Reads only config/*.json and data/shared_lists/*.json. Never writes anything.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = path.join(__dirname, '..');
const STRICT = process.argv.includes('--strict');
const FIXED_L1 = ['arch', 'func', 'test', 'exam', 'bug'];
const issues = [];
const add = (level, where, msg) => issues.push({ level, where, msg });

function readJson(rel, label) {
    const p = path.join(ROOT, rel);
    if (!fs.existsSync(p)) { add('FAIL', label, 'File not found: ' + rel); return null; }
    try { return JSON.parse(fs.readFileSync(p, 'utf8')); }
    catch (e) { add('FAIL', label, 'JSON parse error: ' + e.message); return null; }
}

function finish() {
    const fail = issues.filter(i => i.level === 'FAIL');
    const warn = issues.filter(i => i.level === 'WARN');
    console.log('\n=== Validation Details ===');
    if (!issues.length) console.log('  (No issues)');
    for (const i of issues) console.log('  [' + i.level + '] ' + i.where + ': ' + i.msg);
    console.log('\nSummary: FAIL=' + fail.length + '  WARN=' + warn.length +
                (STRICT ? '  (strict: WARN counted as failure)' : ''));
    const bad = fail.length > 0 || (STRICT && warn.length > 0);
    console.log('RESULT: ' + (bad ? 'FAIL' : 'PASS'));
    process.exit(bad ? 1 : 0);
}

function main() {
    const tax = readJson('config/taxonomy.json', 'config/taxonomy.json');
    const notes = readJson('config/task-notes.json', 'config/task-notes.json');
    const anchors = readJson('config/file-anchors.json', 'config/file-anchors.json');
    if (!tax || !notes || !anchors) return finish();

    // ---- 1. taxonomy: the single whitelist source ----
    const l1ids = (Array.isArray(tax.l1) ? tax.l1 : []).map(x => x && x.id);
    if (JSON.stringify(l1ids.slice().sort()) !== JSON.stringify(FIXED_L1.slice().sort())) {
        add('FAIL', 'taxonomy.l1', 'L1 categories must be exactly ' + FIXED_L1.join('/') + ', actual: ' + JSON.stringify(l1ids));
    }
    const l2 = Array.isArray(tax.l2) ? tax.l2 : [];
    const l2ids = new Set();
    for (const d of l2) {
        if (!d || !d.id) { add('FAIL', 'taxonomy.l2', 'Subdomain missing id'); continue; }
        if (l2ids.has(d.id)) add('FAIL', 'taxonomy.l2', 'Duplicate L2 id: ' + d.id);
        l2ids.add(d.id);
        if (!l1ids.includes(d.listId)) add('FAIL', 'taxonomy.l2', d.id + ' listId not in L1: ' + d.listId);
    }
    for (const c of (Array.isArray(tax.l3) ? tax.l3 : [])) {
        if (c && c.parent && !l2ids.has(c.parent)) add('FAIL', 'taxonomy.l3', (c.id || '?') + ' parent not in L2: ' + c.parent);
    }
    if (!tax.initialized) {
        add('WARN', 'taxonomy', 'Still generic placeholder taxonomy (initialized=false); generate project-specific L2 subdomains per docs/templates/init_agent_prompt.md');
    } else {
        const placeholders = l2.filter(d => d && d.placeholder).length;
        if (placeholders) add('WARN', 'taxonomy', 'initialized=true but still has ' + placeholders + ' placeholder subdomains');
    }

    // ---- 2. task-notes: required segments + exam truth triple ----
    const required = ((notes.segments || {}).required) || [];
    if (!required.length) add('FAIL', 'task-notes', 'segments.required is empty');
    for (const s of required) {
        if (!s || !s.tag || !s.purpose) add('FAIL', 'task-notes', 'required segment missing tag / purpose: ' + JSON.stringify(s));
    }
    const truthKeys = ((notes.examTruth || {}).requiredKeys) || [];
    for (const k of ['truth_source', 'tolerance', 'truth_hash']) {
        if (!truthKeys.includes(k)) add('FAIL', 'task-notes', 'exam truth triple missing ' + k);
    }
    const sitePath = path.join(ROOT, 'config', 'site.json');
    if (fs.existsSync(sitePath)) {
        try {
            const site = JSON.parse(fs.readFileSync(sitePath, 'utf8'));
            const policy = site.project && site.project.truthPolicy;
            if (policy && notes.examTruth && notes.examTruth.truthPolicy !== policy) {
                add('WARN', 'task-notes',
                    'examTruth.truthPolicy does not match config/site.json project.truthPolicy; rerun npm run init to sync');
            }
        } catch (e) { add('WARN', 'config/site.json', 'JSON parse error: ' + e.message); }
    }

    // ---- 3. file-anchors: hash drift ----
    const reg = Array.isArray(anchors.anchors) ? anchors.anchors : [];
    if (!anchors.initialized) add('WARN', 'file-anchors', 'File anchors not yet registered (initialized=false)');
    const anchorRoot = anchors.projectRoot || ROOT;
    for (const a of reg) {
        if (!a || !a.path) { add('FAIL', 'file-anchors', 'Anchor missing path'); continue; }
        if (!/^[a-f0-9]{64}$/i.test(String(a.sha256 || ''))) {
            add('FAIL', 'file-anchors', a.path + ' sha256 invalid (needs 64-char hex)');
        }
        if (a.l2 && !l2ids.has(a.l2)) add('FAIL', 'file-anchors', a.path + ' l2 not in taxonomy: ' + a.l2);
        const p = path.isAbsolute(a.path) ? a.path : path.join(anchorRoot, a.path);
        if (!fs.existsSync(p)) { add('WARN', 'file-anchors', 'Anchor file does not exist: ' + a.path); continue; }
        const actual = crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
        if (actual !== String(a.sha256).toLowerCase()) {
            add('FAIL', 'file-anchors', 'Anchor drift: ' + a.path + ' registered ' + String(a.sha256).slice(0, 12) +
                '… != actual ' + actual.slice(0, 12) + '…');
        }
    }

    // ---- 4. live task data (skipped on a fresh install) ----
    const listsDir = path.join(ROOT, 'data', 'shared_lists');
    if (!fs.existsSync(listsDir)) {
        console.log('  info  data/shared_lists/ does not exist (fresh install), skipping task data validation');
        return finish();
    }
    const names = fs.readdirSync(listsDir).filter(n => n.endsWith('.json')).sort();
    const lists = [];
    const index = new Map();
    for (const name of names) {
        const d = readJson('data/shared_lists/' + name, 'data/shared_lists/' + name);
        if (!d) continue;
        lists.push(d);
        const lid = d.listId || name.replace(/\.json$/, '');
        const collect = (arr) => {
            for (const it of (Array.isArray(arr) ? arr : [])) {
                if (!it || typeof it !== 'object') continue;
                if (it.itemId) index.set(lid + '::' + it.itemId, it);
                if (Array.isArray(it.subTasks)) collect(it.subTasks);
            }
        };
        collect(d.items);
    }
    console.log('  info  Loaded ' + lists.length + ' lists, ' + index.size + ' tasks (including subTasks)');

    const nsRe = /\[([A-Za-z]+):([A-Za-z0-9_-]+)(?::([A-Za-z0-9_-]+))?\]\s*$/;
    const checkItem = (it, where) => {
        if (!it || typeof it !== 'object') return;
        const title = String(it.title || '');
        const m = nsRe.exec(title);
        if (!m) {
            add('WARN', where, 'Title has no [Kind:Domain(:Component)] namespace: ' + title.slice(0, 60));
        } else {
            if (!l1ids.includes(m[1])) add('FAIL', where, 'Namespace Kind not in L1: ' + m[1]);
            if (tax.initialized && !l2ids.has(m[2])) add('FAIL', where, 'L2 subdomain not in whitelist: ' + m[2]);
        }
        const c = String(it.comment || '').replace(/<[^>]*>/g, ' ');
        for (const s of required) {
            if (s && s.tag && !c.includes(s.tag)) add('WARN', where, 'Comment missing required section ' + s.tag);
        }
        const lid = where.split('/')[0];
        if (lid === 'exam') {
            for (const k of truthKeys) if (!c.includes(k)) add('FAIL', where, 'exam missing truth key ' + k);
        }
        const paths = [it.localDirectory]
            .concat(Array.isArray(it.localDirectories) ? it.localDirectories : [])
            .filter(p => typeof p === 'string' && p.trim());
        if (!paths.length) add('WARN', where, 'No file anchor (both localDirectory and localDirectories are empty)');
        for (const r of (Array.isArray(it.relatesTo) ? it.relatesTo : [])) {
            const target = r && (r.itemId || r.targetItemId);
            if (!target) { add('WARN', where, 'relatesTo missing itemId'); continue; }
            if (!index.has(String(r.listId) + '::' + String(target))) {
                add('WARN', where, 'Dangling relation -> ' + r.listId + '::' + target);
            }
        }
        if (Array.isArray(it.subTasks)) {
            it.subTasks.forEach((s, i) => checkItem(s, where + '/sub' + i));
        }
    };
    for (const d of lists) {
        const lid = d.listId || '?';
        (Array.isArray(d.items) ? d.items : []).forEach((it, i) =>
            checkItem(it, lid + '/' + String((it && it.itemId) || i).slice(0, 28)));
    }
    finish();
}

main();
