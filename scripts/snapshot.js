#!/usr/bin/env node
'use strict';

// Audit Trail Snapshot (docs/records/<STAMP>/)
//
// Dumps a point-in-time snapshot of the runtime task databases
// (data/shared_lists/*.json and data/archive/*.json) with SHA-256 hashes into
// docs/records/<YYYYMMDDTHHMMSSZ>/, records an index.json with host metadata,
// and updates docs/records/LATEST.json pointer.
//
// Intended to be run after major stages (init, closeout, release, milestone)
// so the repository retains an auditable record of the board state.
//
// Usage:
//   node scripts/snapshot.js
//   npm run snapshot

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = path.join(__dirname, '..');
const RECORDS = path.join(ROOT, 'docs', 'records');

function sha256(buf) {
    return crypto.createHash('sha256').update(buf).digest('hex');
}

function pad(n) { return String(n).padStart(2, '0'); }

function utcStamp(d) {
    return d.getUTCFullYear() +
        pad(d.getUTCMonth() + 1) +
        pad(d.getUTCDate()) + 'T' +
        pad(d.getUTCHours()) +
        pad(d.getUTCMinutes()) +
        pad(d.getUTCSeconds()) + 'Z';
}

function main() {
    const now = new Date();
    const stamp = utcStamp(now);
    const iso = now.toISOString();

    const sitePath = path.join(ROOT, 'config', 'site.json');
    let site = {};
    try { site = JSON.parse(fs.readFileSync(sitePath, 'utf8')); } catch (e) {}

    const sources = ['shared_lists', 'archive'];
    const files = [];

    for (const src of sources) {
        const dir = path.join(ROOT, 'data', src);
        if (!fs.existsSync(dir)) continue;
        const names = fs.readdirSync(dir).filter(n => n.endsWith('.json')).sort();
        for (const name of names) {
            const full = path.join(dir, name);
            const buf = fs.readFileSync(full);
            let meta = {};
            try {
                const doc = JSON.parse(buf.toString('utf8'));
                meta = {
                    listId: doc.listId || name.replace(/\.json$/, ''),
                    rev: doc.rev,
                    itemCount: Array.isArray(doc.items) ? doc.items.length : 0,
                    updatedAt: doc.updatedAt,
                    updatedBy: doc.updatedBy
                };
            } catch (e) { meta = { parseError: e.message }; }
            files.push(Object.assign({ source: src, name, sha256: sha256(buf), bytes: buf.length }, meta));
        }
    }

    if (!files.length) {
        console.error('FAIL snapshot: No JSON files under data/shared_lists/ or data/archive/.');
        console.error('      Start server once via npm start to generate lists, or verify LITETASK_DATA_DIR.');
        process.exit(1);
    }

    const outDir = path.join(RECORDS, stamp);
    const dataDir = path.join(outDir, 'data');
    fs.mkdirSync(dataDir, { recursive: true });
    for (const f of files) {
        const from = path.join(ROOT, 'data', f.source, f.name);
        const to = path.join(dataDir, f.source + '__' + f.name);
        fs.copyFileSync(from, to);
    }

    const index = {
        version: 1,
        generatedAt: iso,
        clock: 'system clock (Node Date), UTC ISO-8601',
        timezoneOffsetMinutes: now.getTimezoneOffset(),
        projectName: site.projectName || '(unset)',
        goal: site.goal || '',
        fileCount: files.length,
        note: 'Point-in-time snapshot of runtime task data; data/ is excluded by .gitignore, this directory is intentionally versioned for audit trail.',
        files
    };
    fs.writeFileSync(path.join(outDir, 'index.json'), JSON.stringify(index, null, 2) + '\n', 'utf8');
    fs.writeFileSync(path.join(RECORDS, 'LATEST.json'),
        JSON.stringify({ latest: stamp, generatedAt: iso, fileCount: files.length }, null, 2) + '\n', 'utf8');

    console.log('OK snapshot -> docs/records/' + stamp + '/');
    console.log('   generatedAt : ' + iso + ' (system clock, UTC offset ' + now.getTimezoneOffset() + ' min)');
    console.log('   projectName : ' + (site.projectName || '(unset)'));
    console.log('   files       : ' + files.length);
    for (const f of files) {
        console.log('     - ' + f.source + '/' + f.name + '  items=' + f.itemCount +
                    '  rev=' + f.rev + '  sha256=' + f.sha256.slice(0, 12) + '…');
    }
    console.log('   Updated docs/records/LATEST.json');
    console.log('   ⚠ Snapshot contains task data and will be committed; review before git add if sensitive.');
}

main();
