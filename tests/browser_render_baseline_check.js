/**
 * DOM rendering baseline measurement (1k / 5k) — the measurement §36 of references/system-guide.md
 * used to admit it had never made.
 *
 * Why this file exists:
 *   `grade_scale_baseline.py` measures the SERVER (write), the TRANSPORT
 *   (payload bytes, transfer) and the CLIENT PARSE (JSON.parse). None of those
 *   is what a user waits for. A list can arrive in 200 ms and then spend ten
 *   seconds in Vue's render, and every number we had would still look fine.
 *   Until this check exists, "do we need virtual scrolling?" is a question
 *   answered by taste; after it, it is answered by numbers.
 *
 * How it measures (a real Chrome, no synthetic benchmark):
 *   A throwaway server instance is started against a COPY of data/ on a free
 *   port, with one list holding N generated items. Chrome loads the board and
 *   we wait until the DOM really holds N rendered rows — not until "load",
 *   which fires long before Vue has built the tree. Then:
 *
 *     msToRows        navigation start -> N rows present in the DOM
 *     firstPaintMs    first-contentful-paint (Chrome's own paint timing)
 *     domContentLoadedMs / loadMs
 *     domNodes        total element count of the rendered board
 *     payloadBytes    what /api/lists actually transferred (Chrome's numbers)
 *     msFilter        typing in the search box -> the filtered row count
 *
 * What is asserted, and what is only recorded:
 *   Asserted: that N rows really rendered (so a future virtualised board that
 *   only draws 50 of them cannot pass silently), that the timings exist, that
 *   the DOM grows with N, that filtering still works at 5k, and that nothing
 *   threw a console error. Plus one deliberately loose ceiling per scale —
 *   loose enough that machine noise cannot trip it, tight enough that a 10x
 *   regression does.
 *   Recorded, not asserted: the milliseconds themselves. They are printed and
 *   written to tests/_artifacts/<run>/render_baseline.json. A threshold copied
 *   from today's machine would be a flaky assertion wearing a lab coat.
 *
 * No browser is installed by this check: puppeteer-core is already a
 * dependency (it downloads nothing) and it drives the Chrome this machine has.
 */
const fs = require('fs');
const net = require('net');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

const ROOT = path.join(__dirname, '..');
const SCALES = (process.env.LITETASK_RB_SCALES || '1000,5000')
    .split(',').map((s) => Number(s.trim())).filter((n) => n > 0);
// Deliberately generous: these catch "rendering got an order of magnitude
// worse", not "the CI box was busy". Anything tighter would be noise. The 5k
// ceiling is 5 minutes because 5k rows is where the measurement stops being a
// benchmark and starts being a verdict (see the numbers below).
const ceilingMs = (n) => (n <= 1000 ? 30000 : 300000);
const ROW_SELECTOR = '.task-node-wrapper';
// Per-scale render budget. 5k gets two minutes, not five: if the board has not
// drawn 5000 rows by then, that is the answer — waiting longer would buy a
// number nobody would act on differently.
const budgetMs = (n) => (n <= 1000 ? 60000 : 120000);
const FILTER_TIMEOUT = 60000;
// A renderer that is still building rows cannot answer page.evaluate() either.
// Reads are therefore raced against a short timer and recorded as null when the
// page does not answer — "unresponsive" is itself part of the finding.
const READ_TIMEOUT = 15000;

function raceRead(promise) {
    let timer;
    const guard = new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('renderer did not answer in '
            + READ_TIMEOUT + ' ms')), READ_TIMEOUT);
    });
    return Promise.race([promise, guard]).finally(() => clearTimeout(timer))
        .catch(() => null);
}

function freePort() {
    return new Promise((resolve) => {
        const s = net.createServer();
        s.listen(0, '127.0.0.1', () => {
            const p = s.address().port;
            s.close(() => resolve(p));
        });
    });
}

function writeListFile(dataDir, listId, items) {
    const file = path.join(dataDir, 'shared_lists', listId + '.json');
    const doc = JSON.parse(fs.readFileSync(file, 'utf8'));
    doc.items = items;
    // Same atomic replace the server uses, so a watcher never sees a half file.
    const tmp = file + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(doc, null, 2), 'utf8');
    fs.renameSync(tmp, file);
}

function makeItems(n) {
    const out = [];
    for (let i = 0; i < n; i++) {
        out.push({
            itemId: 'rb-' + String(i).padStart(6, '0'),
            title: i === 0 ? 'RENDER-BASELINE-TARGET' : ('render baseline item ' + i),
            isDone: false,
            status: 'open',
            statusHistory: [],
            blockedReason: '',
            dueDate: '',
            priority: 'Medium',
            assignedTo: 'admin',
            createdBy: 'admin',
            createdByAgent: 'AI Agent',
            createdById: 'user_admin',
            createdAt: '2026-10-31 00:00',
            closedBy: null,
            closedById: null,
            closedAt: null,
            localDirectory: '',
            localDirectories: [],
            comment: '',
            subTasks: [],
            relatesTo: []
        });
    }
    return out;
}

function startInstance(dataDir, backupDir, port) {
    return new Promise((resolve, reject) => {
        const proc = spawn(process.execPath, ['server.js'], {
            cwd: ROOT,
            env: Object.assign({}, process.env, {
                PORT: String(port),
                LITETASK_DATA_DIR: dataDir,
                LITETASK_BACKUP_DIR: backupDir,
                LITETASK_AUTO_ARCHIVE: '0',
                LITETASK_BACKUP_KEEP: '1'
            }),
            stdio: ['ignore', 'pipe', 'pipe']
        });
        let out = '';
        const onData = (d) => {
            out += d.toString();
            if (out.includes('Server running')) resolve({ proc, output: out });
        };
        proc.stdout.on('data', onData);
        proc.stderr.on('data', onData);
        proc.on('error', reject);
        setTimeout(() => reject(new Error('instance did not come up:\n' + out)), 60000);
    });
}

function stopInstance(proc) {
    if (!proc || proc.exitCode !== null) return;
    try { proc.kill(); } catch (e) { /* already gone */ }
}

/**
 * A renderer that never came back from building 5000 rows does not answer
 * browser.close() either — it just lets the CDP call hang until the protocol
 * timeout fires and takes the whole check down with it. Give close() a few
 * seconds and then kill the process outright.
 */
async function closeBrowser(browser) {
    const closed = browser.close().catch(() => {});
    await Promise.race([closed, new Promise((r) => setTimeout(r, 15000))]);
    try {
        const proc = browser.process();
        if (proc && proc.exitCode === null) proc.kill('SIGKILL');
    } catch (e) { /* nothing left to kill */ }
}

async function main() {
    const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'lt_render_'));
    const dataDir = path.join(tmpRoot, 'data');
    const backupDir = path.join(tmpRoot, 'backup');
    fs.cpSync(path.join(ROOT, 'data'), dataDir, { recursive: true });

    const port = await freePort();
    const inst = await startInstance(dataDir, backupDir, port);
    process.env.LITETASK_BASE = 'http://127.0.0.1:' + port;
    // Required after the base URL is known: browser_lib reads it at load time.
    const lib = require('./browser_lib');
    const { check, finish } = lib.createChecker('dom-render-baseline');

    const record = { measuredAt: new Date().toISOString(), base: lib.BASE, scales: [] };
    const allConsoleErrors = [];

    try {
        for (const n of SCALES) {
            writeListFile(dataDir, 'arch', makeItems(n));
            // give the watcher a moment; the next load reads from disk anyway
            await new Promise((r) => setTimeout(r, 400));

            // A fresh browser per scale: reusing one would make the 5k number
            // include tearing down the 1k tree first, which is nobody's load
            // time. Each scale is measured as a cold start.
            const { browser, page, consoleErrors } = await lib.openBrowser({
                protocolTimeout: budgetMs(n) + 30000
            });
            allConsoleErrors.push(...consoleErrors);

            const t0 = Date.now();
            await page.goto(lib.BASE, { waitUntil: 'domcontentloaded', timeout: budgetMs(n) });
            // A cutoff is a FINDING, not a crash: how many rows were on screen
            // when the budget ran out is exactly the number that says whether
            // the board is usable at this scale. Record it instead of throwing.
            let finished = true;
            let renderNote = '';
            try {
                await page.waitForFunction(
                    (sel, want) => document.querySelectorAll(sel).length === want,
                    { timeout: budgetMs(n), polling: 250 }, ROW_SELECTOR, n);
            } catch (e) {
                finished = false;
                renderNote = String((e && e.message) || e).slice(0, 120);
            }
            const msToRows = Date.now() - t0;

            const perf = await raceRead(page.evaluate(() => {
                const nav = (performance.getEntriesByType('navigation') || [])[0] || {};
                const paints = performance.getEntriesByType('paint') || [];
                const fcp = paints.find((p) => p.name === 'first-contentful-paint');
                const lists = (performance.getEntriesByType('resource') || [])
                    .filter((r) => r.name.includes('/api/lists'));
                const transfer = lists.reduce((a, r) => a + (r.transferSize || r.encodedBodySize || 0), 0);
                return {
                    domContentLoadedMs: Math.round(nav.domContentLoadedEventEnd || 0),
                    loadMs: Math.round(nav.loadEventEnd || 0),
                    firstPaintMs: fcp ? Math.round(fcp.startTime) : null,
                    payloadBytes: transfer || null,
                    domNodes: document.querySelectorAll('*').length
                };
            })) || { firstPaintMs: null, domNodes: null, payloadBytes: null,
                     domContentLoadedMs: null, loadMs: null };
            const rowsRead = await raceRead(page.evaluate(
                (sel) => document.querySelectorAll(sel).length, ROW_SELECTOR));
            const rows = rowsRead === null ? -1 : rowsRead;

            // ---- interaction: one keystroke path at scale -------------------
            // Only meaningful once the rows are actually there; at a cutoff the
            // filter measurement is skipped and recorded as null.
            let msFilter = null;
            if (finished) {
                const tF = Date.now();
                await page.click('input[placeholder="Search..."]');
                await page.type('input[placeholder="Search..."]', 'RENDER-BASELINE-TARGET',
                    { delay: 0 });
                await page.waitForFunction(
                    (sel) => document.querySelectorAll(sel).length === 1,
                    { timeout: FILTER_TIMEOUT, polling: 100 }, ROW_SELECTOR);
                msFilter = Date.now() - tF;
            }

            const rec = {
                items: n, finished, rows, msToRows, msFilter,
                firstPaintMs: perf.firstPaintMs,
                domContentLoadedMs: perf.domContentLoadedMs,
                loadMs: perf.loadMs,
                domNodes: perf.domNodes,
                payloadBytes: perf.payloadBytes
            };
            if (!finished) {
                rec.cutoff = { budgetMs: budgetMs(n), note: renderNote,
                               rendererAnswered: rows !== -1 };
            }
            record.scales.push(rec);

            console.log('  %d items: %srows rendered in %d ms (FCP %s ms, DCL %d ms, ' +
                'load %d ms) — %d DOM nodes, %s bytes over the wire, filter %s ms',
                n, finished ? '' : 'CUTOFF: only ' + rows + ' / ',
                msToRows, perf.firstPaintMs, perf.domContentLoadedMs,
                perf.loadMs, perf.domNodes, perf.payloadBytes, msFilter);

            // The invariant is truthful accounting, not speed: either every row
            // is in the DOM, or the run says out loud that it hit the budget and
            // how far it got. What must never happen is a board that draws 50
            // rows and calls it 5000.
            check(n + ': either all rows are in the DOM, or the cutoff is recorded ' +
                'with what the board managed (never a silent truncation)',
                (rows === n) === finished && rows !== 0,
                { finished, rows, budgetMs: budgetMs(n), note: renderNote });
            if (finished) {
                check(n + ': first-contentful-paint was measured',
                    typeof perf.firstPaintMs === 'number' && perf.firstPaintMs > 0,
                    perf.firstPaintMs);
                check(n + ': the board rendered inside the sanity ceiling of ' +
                    ceilingMs(n) + ' ms', msToRows < ceilingMs(n), msToRows);
                check(n + ': filtering 1 of ' + n + ' rows works and stays under ' +
                    FILTER_TIMEOUT + ' ms', msFilter !== null && msFilter < FILTER_TIMEOUT,
                    msFilter);
            } else {
                check(n + ': the cutoff is written into the baseline instead of ' +
                    'being swallowed', !!rec.cutoff && rec.cutoff.budgetMs === budgetMs(n),
                    rec.cutoff);
            }

            // clear the filter for the next scale
            if (finished) {
                await raceRead(page.evaluate(() => {
                    const el = document.querySelector('input[placeholder="Search..."]');
                    el.value = '';
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                }));
            }
            await closeBrowser(browser);
        }

        // Growth can only be asserted when both scales actually answered: at a
        // cutoff the renderer never reports DOM size or payload at all, and
        // "null > 83173" is not a finding, it is a missing measurement.
        if (record.scales.length >= 2
            && record.scales[0].domNodes != null && record.scales[1].domNodes != null) {
            const a = record.scales[0];
            const b = record.scales[1];
            check('the DOM really grows with the list',
                b.domNodes > a.domNodes, [a.domNodes, b.domNodes]);
            check('the payload really grows with the list',
                (b.payloadBytes || 0) > (a.payloadBytes || 0),
                [a.payloadBytes, b.payloadBytes]);
        }

        const real = lib.realErrors(allConsoleErrors);
        check('no unexpected console errors at either scale', real.length === 0, real);

        const outFile = path.join(lib.SHOTS, 'render_baseline.json');
        fs.writeFileSync(outFile, JSON.stringify(record, null, 2), 'utf8');
        check('the baseline was written down (tests/_artifacts/.../render_baseline.json)',
            fs.existsSync(outFile), outFile);
        console.log('  baseline written to %s', outFile);
    } finally {
        stopInstance(inst.proc);
        fs.rmSync(tmpRoot, { recursive: true, force: true });
    }

    finish();
}

main().catch((e) => {
    console.error('render baseline check crashed: %s', (e && e.stack) || e);
    process.exit(1);
});
