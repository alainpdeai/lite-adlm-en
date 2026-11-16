/**
 * Shared plumbing for every LiteTask browser check (M1 — the forced
 * "verify it in a real browser" procedure, made reusable).
 *
 * The three things each check used to duplicate:
 *   1. launching the same Chrome with the same viewport and the same guards
 *   2. collecting console/page errors and deciding which ones are noise
 *   3. accumulating assertions and turning them into an exit code
 *
 * Usage:
 *   const lib = require('./browser_lib');
 *   const { check, finish } = lib.createChecker('my check');
 *   const { browser, page, consoleErrors } = await lib.openBrowser({ blockRealtime: true });
 *   await lib.openBoard(page);
 *   ...
 *   const real = lib.realErrors(consoleErrors);
 *   check('no unexpected console errors', real.length === 0, real);
 *   await browser.close();
 *   finish();
 */
const puppeteer = require('puppeteer-core');
const http = require('http');
const path = require('path');
const fs = require('fs');

const CHROME = process.env.LITETASK_CHROME
    || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const BASE = process.env.LITETASK_BASE || 'http://localhost:3000';
const VIEWPORT = { width: 1440, height: 1000 };

// Screenshots land in tests/_artifacts/<run_id>/ instead of tests/ itself, so
// test runs stop littering the source tree. One run id per run: the aggregate
// runner (run_browser_checks.js) exports LITETASK_RUN_ID so every check it
// spawns shares a single run directory; standalone invocations mint their own.
// pruneArtifacts() keeps only the newest ARTIFACT_KEEP_RUNS run directories, so
// accumulation is bounded while the last few runs stay debuggable.
const ARTIFACT_KEEP_RUNS = 3;
const ARTIFACTS_DIR = path.join(__dirname, '_artifacts');
const RUN_ID = process.env.LITETASK_RUN_ID
    || (new Date().toISOString().replace(/[-:.]/g, '') + '_pid' + process.pid);
const SHOTS = path.join(ARTIFACTS_DIR, RUN_ID);

function pruneArtifacts() {
    let entries;
    try {
        entries = fs.readdirSync(ARTIFACTS_DIR, { withFileTypes: true });
    } catch (e) {
        return; // artifacts dir does not exist yet — nothing to prune
    }
    const runs = entries
        .filter((e) => e.isDirectory() && /^\d{8}T\d{9}Z_pid\d+$/.test(e.name))
        .map((e) => e.name)
        .sort();
    const doomed = runs.slice(0, Math.max(0, runs.length - ARTIFACT_KEEP_RUNS));
    for (const d of doomed) {
        try {
            fs.rmSync(path.join(ARTIFACTS_DIR, d), { recursive: true, force: true });
        } catch (e) { /* best effort; a stale dir is harmless */ }
    }
    if (doomed.length) {
        console.log('[browser_lib] pruned %d old artifact run(s); kept newest %d of %d',
            doomed.length, Math.min(ARTIFACT_KEEP_RUNS, runs.length), runs.length);
    }
}

fs.mkdirSync(SHOTS, { recursive: true });
pruneArtifacts();

/**
 * Console noise that is not a defect: the app has no favicon, and aborting the
 * socket.io request (see openBrowser) makes Chrome log a failed fetch.
 */
const IGNORED_ERRORS = ['favicon.ico', 'ERR_FAILED'];

function createChecker(name) {
    const results = [];
    const check = (label, ok, detail) => {
        results.push({ label, ok: !!ok });
        const suffix = detail !== undefined ? '  -> ' + JSON.stringify(detail) : '';
        console.log((ok ? '  PASS  ' : '  FAIL  ') + label + suffix);
    };
    const finish = () => {
        const failed = results.filter((r) => !r.ok);
        console.log('\nRESULT[%s]: %d/%d passed', name,
            results.length - failed.length, results.length);
        failed.forEach((f) => console.log('  FAILED: ' + f.label));
        if (failed.length) process.exitCode = 1;
        return failed.length === 0;
    };
    return { results, check, finish, failed: () => results.filter((r) => !r.ok) };
}

function api(method, urlPath, body) {
    const payload = body ? JSON.stringify(body) : null;
    return new Promise((resolve, reject) => {
        const req = http.request(BASE + urlPath, {
            method,
            headers: payload
                ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) }
                : {}
        }, (res) => {
            let data = '';
            res.on('data', (c) => (data += c));
            res.on('end', () => {
                let parsed = null;
                try { parsed = JSON.parse(data || 'null'); } catch (e) { parsed = { raw: data }; }
                resolve({ status: res.statusCode, body: parsed });
            });
        });
        req.on('error', reject);
        if (payload) req.write(payload);
        req.end();
    });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function getList(id) {
    const { body } = await api('GET', '/api/lists');
    return (body || []).find((l) => l.listId === id);
}

/** The server only exposes the collection route; there is no single-list GET. */
async function getLists() {
    const { body } = await api('GET', '/api/lists');
    return body || [];
}

/**
 * @param {string} id        list id
 * @param {Array}  items     full replacement item array
 * @param {string} baseRev   concurrency token, or null to skip the check
 * @param {object} opts      { force: true } skips the rev check (restore path)
 *                           { userId }      attribute the write
 */
async function putList(id, items, baseRev, opts = {}) {
    const body = { type: 'UPDATE_ITEMS', items, baseRev };
    if (opts.force) {
        body.force = true;
        // Security boundary P2-C hard gate: a forced write needs an affirmative confirm.
        body.confirm = true;
    }
    if (opts.userId) body.userId = opts.userId;
    return api('PUT', '/api/lists/' + id, body);
}

async function waitForText(page, text, timeout = 20000) {
    await page.waitForFunction(
        (t) => document.body && document.body.innerText.includes(t),
        { timeout }, text);
}

async function clickByText(page, text, tag = 'button') {
    const ok = await page.evaluate((t, g) => {
        const el = Array.from(document.querySelectorAll(g))
            .find((e) => (e.textContent || '').includes(t));
        if (!el) return false;
        el.click();
        return true;
    }, text, tag);
    if (!ok) throw new Error('element not found: ' + text);
}

/** Icon-only buttons (e.g. the modal close X) have no text to match on. */
async function clickByIcon(page, iconClass, { last = true } = {}) {
    const ok = await page.evaluate((ic, pickLast) => {
        const hits = Array.from(document.querySelectorAll('button'))
            .filter((b) => b.querySelector('i.' + ic));
        if (!hits.length) return false;
        (pickLast ? hits[hits.length - 1] : hits[0]).click();
        return true;
    }, iconClass, last);
    if (!ok) throw new Error('icon button not found: ' + iconClass);
}

/**
 * @param {object}  opts
 * @param {boolean} opts.blockRealtime  abort /socket.io/ so the board cannot
 *        silently refresh to a newer rev. Required for race tests; the board
 *        works fine without it (file changes are still pushed on load).
 */
/**
 * @param {object}  opts
 * @param {boolean} opts.blockRealtime  abort /socket.io/ so the board cannot
 *        silently refresh to a newer rev. Required for race tests; the board
 *        works fine without it (file changes are still pushed on load).
 * @param {number}  opts.protocolTimeout  the CDP deadline, separate from any
 *        waitForFunction timeout (see the comment at the launch call).
 * @returns {{browser, page, consoleErrors, dialogs}} `dialogs` collects every
 *        native dialog the page opened: `{type, message}`, in order.
 */
async function openBrowser({ blockRealtime = false, protocolTimeout = 180000 } = {}) {
    const browser = await puppeteer.launch({
        executablePath: CHROME,
        headless: 'new',
        // CDP calls have their own timeout, separate from any waitForFunction
        // timeout: a renderer that is busy for minutes kills the *connection*,
        // not just the wait. Large-scale measurements need to raise it.
        protocolTimeout,
        args: ['--no-sandbox', '--disable-dev-shm-usage', '--window-size=1440,1000']
    });
    const page = await browser.newPage();
    await page.setViewport(VIEWPORT);

    const consoleErrors = [];
    page.on('console', (m) => {
        if (m.type() !== 'error') return;
        const url = (m.location() && m.location().url) || '';
        consoleErrors.push(m.text() + ' @ ' + url);
    });
    page.on('pageerror', (e) => consoleErrors.push('pageerror: ' + e.message));

    // A native confirm()/alert() blocks the renderer until somebody answers it,
    // and puppeteer does not answer dialogs by default. Left alone, every later
    // page.evaluate hangs until protocolTimeout and the failure surfaces as
    // "Runtime.callFunctionOn timed out" — which reads like a rendering problem
    // and is actually a modal nobody dismissed. (The destructive-confirmation
    // gate added on 2026-10-31 hit exactly this: the conflict check passed all
    // seven of its real assertions and then died on a confirm() it never saw.)
    // Capture the messages, accept the dialog, and hand them back so a check can
    // assert that the confirmation was asked for at all.
    const dialogs = [];
    page.on('dialog', async (d) => {
        dialogs.push({ type: d.type(), message: d.message() });
        try { await d.accept(); } catch (e) { /* page already gone */ }
    });

    if (blockRealtime) {
        await page.setRequestInterception(true);
        page.on('request', (r) => {
            if (r.url().includes('/socket.io/')) r.abort().catch(() => {});
            else r.continue().catch(() => {});
        });
    }
    return { browser, page, consoleErrors, dialogs };
}

async function openBoard(page) {
    await page.goto(BASE, { waitUntil: 'networkidle2', timeout: 30000 });
    await waitForText(page, 'Relations', 25000);
}

/**
 * @param {string[]} extra  per-check noise, e.g. the 409 the conflict check
 *        provokes on purpose. Keep this list short: adding to it hides bugs.
 */
function realErrors(consoleErrors, extra = []) {
    const skip = IGNORED_ERRORS.concat(extra);
    return (consoleErrors || []).filter((e) => !skip.some((n) => e.includes(n)));
}

async function shot(page, name) {
    const file = path.join(SHOTS, 'shot_' + name + '.png');
    await page.screenshot({ path: file });
    return file;
}

/**
 * Click the Notes toggle of the row whose title is `title`.
 *
 * Not `document.querySelector('button[title="Notes"]')`: with more than one
 * entry on the board that grabs the first row's button, so a check for case 02
 * silently expanded case 01's note and passed on the wrong text. Walk up from
 * the title element to the nearest ancestor that owns a Notes button — that
 * ancestor is the row itself, level 5 up would be the whole list.
 */
async function clickNotesInRow(page, title) {
    return page.evaluate((t) => {
        const cands = Array.from(document.querySelectorAll('span,div,td,a,p'))
            .filter((e) => (e.innerText || '').includes(t));
        const target = cands[cands.length - 1];
        if (!target) return 'title-not-found';
        let n = target;
        for (let i = 0; i < 6 && n; i++) {
            const b = n.querySelector && n.querySelector('button[title="Notes"]');
            if (b) { b.click(); return 'clicked'; }
            n = n.parentElement;
        }
        return 'notes-button-not-found';
    }, title);
}

module.exports = {
    CHROME, BASE, SHOTS, VIEWPORT, IGNORED_ERRORS,
    createChecker, api, sleep, getList, getLists, putList,
    waitForText, clickByText, clickByIcon,
    openBrowser, openBoard, realErrors, shot, clickNotesInRow
};
