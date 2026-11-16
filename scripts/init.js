#!/usr/bin/env node
'use strict';

// Interactive first-run initialization for the ADLM system.
//
// Two layers:
//   1) Brand / runtime settings  -> config/site.json (unchanged behaviour).
//   2) Project knowledge pack    -> config/taxonomy.json (L1/L2/L3 whitelist),
//                                  config/task-notes.json (note spec + truth policy),
//                                  config/file-anchors.json (file anchors + SHA-256).
//
// Layer 2 files ship with the repository as annotated seeds. init.js UPDATES
// them from your answers; it never silently rebuilds or overwrites a customized
// dictionary. Re-running init is idempotent.
//
// Usage:
//   npm run init                     # prompts each field (TTY)
//   node scripts/init.js --defaults # non-interactive: fill missing site fields
//
// Note: the admin password set here only takes effect on the FIRST `npm start`
// (when data/users.json does not yet exist). To change it afterwards, use the
// running app's user settings or edit data/users.json directly.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const readline = require('readline');

const ROOT = path.join(__dirname, '..');
const SITE_PATH = path.join(ROOT, 'config', 'site.json');
const TAXONOMY_PATH = path.join(ROOT, 'config', 'taxonomy.json');
const NOTES_PATH = path.join(ROOT, 'config', 'task-notes.json');
const ANCHORS_PATH = path.join(ROOT, 'config', 'file-anchors.json');
const FIXED_L1 = ['arch', 'func', 'test', 'exam', 'bug'];

const DEFAULTS = {
  projectName: 'Lite ADLM',
  subtitle: 'Shared Task Tree',
  loginSubtitle: 'Team Shared Workspace',
  logPrefix: 'ADLM',
  goal: 'An AI-assisted project management system: solidifying development progress and unexpected tasks into structured memory during project evolution, displayed clearly on the frontend with naturally traceable audit history.',
  'admin.username': 'admin',
  'admin.password': 'admin',
  port: 3000,

  'project.domain': '',
  'project.root': '',
  'project.truthPolicy': 'Official specifications + deliverable SHA-256'
};

function loadJson(p) {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return null; }
}
function saveJson(p, obj) {
  fs.writeFileSync(p, JSON.stringify(obj, null, 2) + '\n', 'utf8');
}

function get(obj, key) {
  return key.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
}
function set(obj, key, val) {
  const parts = key.split('.');
  const last = parts.pop();
  let cur = obj;
  for (const p of parts) {
    if (cur[p] == null || typeof cur[p] !== 'object') cur[p] = {};
    cur = cur[p];
  }
  cur[last] = val;
  return obj;
}

const PROMPTS = [
  ['projectName', 'Project Name (projectName)'],
  ['subtitle', 'Main Subtitle (subtitle)'],
  ['loginSubtitle', 'Login Subtitle (loginSubtitle)'],
  ['logPrefix', 'Log Prefix (logPrefix)'],
  ['goal', 'Project Goal (one sentence)'],
  ['admin.username', 'Admin Username (admin.username)'],
  ['admin.password', 'Admin Initial Password (admin.password)  ⚠ Effective only before first start'],
  ['port', 'Server Port (port)'],

  ['project.domain', 'Project Domain (one sentence, for taxonomy generation)'],
  ['project.root', 'Project Root (for file anchor scan; leave empty to skip)'],
  ['project.truthPolicy', 'Exam Truth Policy (immutable ground-truth policy)']
];

// Non-interactive / CI switches. These make the knowledge-pack generation
// scriptable (and testable) without a TTY:
//   node scripts/init.js --defaults --l2="arch:core=Core Architecture,func:api=API" \
//        --root=/path/to/project --anchors="src/main.js,tests/" --domain="..." \
//        --truth-policy="Official specifications + deliverable SHA-256"
function argValue(name) {
  const prefix = '--' + name + '=';
  const inline = process.argv.find(a => a.startsWith(prefix));
  if (inline) return inline.slice(prefix.length);
  const i = process.argv.indexOf('--' + name);
  if (i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--')) {
    return process.argv[i + 1];
  }
  return '';
}

function ask(rl, label, def) {
  return new Promise((resolve) => {
    rl.question(`${label}${def !== undefined && def !== '' ? ' [' + def + '] ' : ''}: `, (ans) => {
      const v = (ans || '').trim();
      resolve(v === '' ? def : v);
    });
  });
}

// "arch:core-arch=Core Architecture,func:pde-solver=PDE Solver,test:unit=Unit Tests"
function parseL2(input) {
  const out = [];
  const seen = new Set();
  for (const raw of String(input || '').split(',').map(s => s.trim()).filter(Boolean)) {
    const m = /^([A-Za-z]+):([A-Za-z0-9_-]+)(?:=([^=]+))?$/.exec(raw);
    if (!m) { console.log('   ⚠ Skipped unparseable subdomain: ' + raw); continue; }
    const [, listId, id, name] = m;
    if (!FIXED_L1.includes(listId)) { console.log('   ⚠ Skipped unknown L1: ' + raw); continue; }
    if (seen.has(id)) { console.log('   ⚠ Skipped duplicate subdomain id: ' + id); continue; }
    seen.add(id);
    out.push({ id, name: (name || id).trim(), listId, pathPrefix: '', placeholder: false });
  }
  return out;
}

function scanAnchors(projectRoot, input, exclude, max) {
  const rootAbs = path.resolve(ROOT, projectRoot);
  if (!fs.existsSync(rootAbs)) {
    console.log('   ⚠ Project root does not exist, skipping anchor scan: ' + rootAbs);
    return [];
  }
  const targets = String(input || '').split(',').map(s => s.trim()).filter(Boolean);
  const out = [];
  const seen = new Set();
  const visit = (abs) => {
    if (out.length >= max) return;
    let st;
    try { st = fs.statSync(abs); } catch (e) { return; }
    if (st.isDirectory()) {
      for (const name of fs.readdirSync(abs).sort()) {
        if (out.length >= max) return;
        if ((exclude || []).includes(name)) continue;
        visit(path.join(abs, name));
      }
      return;
    }
    if (!st.isFile()) return;
    const rel = path.relative(rootAbs, abs).split(path.sep).join('/');
    if (seen.has(rel)) return;
    if ((exclude || []).some(e => rel.split('/').includes(e))) return;
    seen.add(rel);
    const buf = fs.readFileSync(abs);
    out.push({
      path: rel,
      sha256: crypto.createHash('sha256').update(buf).digest('hex'),
      bytes: buf.length,
      mtime: st.mtime.toISOString(),
      l2: ''
    });
  };
  for (const t of targets) {
    const abs = path.resolve(rootAbs, t);
    if (!fs.existsSync(abs)) { console.log('   ⚠ Anchor path does not exist: ' + t); continue; }
    visit(abs);
  }
  return out;
}

function syncKnowledge(site, l2Input, anchorInput) {
  const missing = [TAXONOMY_PATH, NOTES_PATH, ANCHORS_PATH].filter(p => !fs.existsSync(p));
  if (missing.length) {
    console.error('\n❌ Project knowledge assets missing, initialization aborted:');
    for (const p of missing) console.error('   ' + path.relative(ROOT, p));
    console.error('   These files are provided with the repo. Restore from git (git checkout -- config/) and rerun.');
    process.exit(1);
  }

  // 1) taxonomy: only replace l2 when the operator explicitly supplied a list.
  const tax = loadJson(TAXONOMY_PATH);
  const parsed = parseL2(l2Input);
  if (parsed.length) {
    tax.l2 = parsed;
    tax.initialized = true;
    saveJson(TAXONOMY_PATH, tax);
    console.log('   ✅ Taxonomy dictionary updated: ' + parsed.length + ' L2 subdomains, initialized=true');
  } else {
    console.log('   · Taxonomy dictionary unchanged (' + (tax.initialized ? 'initialized' : 'generic placeholder') +
                '); see docs/templates/init_agent_prompt.md to generate project dictionary');
  }

  // 2) task-notes: site.json is the single source for the truth policy.
  const notes = loadJson(NOTES_PATH);
  const policy = (site.project && site.project.truthPolicy) || DEFAULTS['project.truthPolicy'];
  if (notes.examTruth && notes.examTruth.truthPolicy !== policy) {
    notes.examTruth.truthPolicy = policy;
    saveJson(NOTES_PATH, notes);
    console.log('   ✅ Task notes synced truth policy: ' + policy);
  } else {
    console.log('   · Task notes unchanged (truth policy consistent)');
  }

  // 3) file-anchors: only scan when both root and paths were supplied.
  const anchors = loadJson(ANCHORS_PATH);
  let changed = false;
  if (site.project && site.project.root && anchors.projectRoot !== site.project.root) {
    anchors.projectRoot = site.project.root;
    changed = true;
  }
  if (anchorInput && site.project && site.project.root) {
    const scanned = scanAnchors(site.project.root, anchorInput, anchors.exclude, anchors.maxAnchors || 200);
    if (scanned.length) {
      anchors.anchors = scanned;
      anchors.initialized = true;
      anchors.generatedAt = new Date().toISOString();
      changed = true;
      console.log('   ✅ File anchors registered: ' + scanned.length + ' files (SHA-256 + mtime)');
    } else {
      console.log('   ⚠ No valid anchors scanned, registry kept as-is');
    }
  } else {
    console.log('   · File anchors unchanged (no root/path provided, or kept existing)');
  }
  if (changed) saveJson(ANCHORS_PATH, anchors);
}

async function main() {
  const useDefaults = process.argv.includes('--defaults') || process.argv.includes('-y') || !process.stdin.isTTY;
  const cur = loadJson(SITE_PATH) || {};
  const out = Object.assign({}, cur);
  let l2Input = '';
  let anchorInput = '';

  if (useDefaults) {
    for (const [k] of PROMPTS) {
      if (get(out, k) === undefined) set(out, k, DEFAULTS[k]);
    }
    const cliDomain = argValue('domain');
    const cliRoot = argValue('root');
    const cliPolicy = argValue('truth-policy');
    if (cliDomain) set(out, 'project.domain', cliDomain);
    if (cliRoot) set(out, 'project.root', cliRoot);
    if (cliPolicy) set(out, 'project.truthPolicy', cliPolicy);
    l2Input = argValue('l2');
    anchorInput = argValue('anchors');
  } else {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    for (const [k, label] of PROMPTS) {
      const def = get(out, k) !== undefined ? get(out, k) : DEFAULTS[k];
      set(out, k, await ask(rl, label, def));
    }
    console.log('\n--- Project Knowledge Initialization (Enter to skip, can be generated by Agent later) ---');
    l2Input = await ask(rl,
      'Project-specific L2 subdomains (format arch:id=Name,func:id=Name,…)', '');
    anchorInput = await ask(rl,
      'Key file anchors (relative to project root, comma-separated; directories allowed)', '');
    rl.close();
  }

  // P1-2: the mode is controlled only by LITETASK_DEV_LOGIN. Drop the legacy
  // site field on every save so a second run cannot resurrect it.
  delete out.securityModel;
  saveJson(SITE_PATH, out);
  console.log('\n✅ Initial configuration written to config/site.json');
  console.log('   Project Name     = ' + out.projectName);
  console.log('   Admin Username   = ' + (out.admin && out.admin.username));
  console.log('   Server Port      = ' + out.port);

  console.log('\n--- Project Knowledge Assets ---');
  syncKnowledge(out, l2Input, anchorInput);

  console.log('\nNext steps:');
  console.log('   npm run validate    # Validate taxonomy / notes / anchors (placeholder taxonomy gives WARN)');
  console.log('   npm run snapshot    # Generate docs/records/ snapshot (optional, recommended)');
  console.log('   npm start           # Bootstrap database on first start');
}

main().catch((e) => {
  console.error('init failed:', e && e.message ? e.message : e);
  process.exit(1);
});
