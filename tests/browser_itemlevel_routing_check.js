/**
 * Frontend item-level write routing verification (P3-B frontend adoption).
 *
 * Verification points:
 *   1. Single item modification uses PUT /api/lists/:id/items/:itemId,
 *      and whole-list PUT /api/lists/:id is NOT called.
 *   2. Multiple item modifications fallback to whole-list PUT /api/lists/:id.
 *   3. Single item changes persist to disk (server isDone/status updated).
 *
 * Uses disposable probe list, deleted on completion to avoid test leakage.
 * Note: blockRealtime aborts /socket.io/, causing client warnings.
 * This is a test fixture side-effect, not a defect.
 */
const lib = require('./browser_lib');

const LIST_NAME = 'itemlevel-probe-' + Date.now();
const ITEM_A = 'Routing-Probe-A-' + Date.now();
const ITEM_B = 'Routing-Probe-B-' + Date.now();
const ITEM_C = 'Routing-Probe-C-' + Date.now();

const isItemLevel = (c) => /\/api\/lists\/[^/]+\/items\/[^/]+$/.test(c.url) && c.method === 'PUT';
const isWholeList = (c) => /\/api\/lists\/[^/]+$/.test(c.url) && c.method === 'PUT' && !/\/items\//.test(c.url);

const clickToggleByTitle = (page, title) => page.evaluate((t) => {
    const wrappers = Array.from(document.querySelectorAll('.task-node-wrapper'));
    const w = wrappers.find((x) => (x.innerText || '').includes(t));
    if (!w) return 'wrapper-not-found:' + t;
    const btn = w.querySelector('button[title^="Mark as"]');
    if (!btn) return 'btn-not-found';
    btn.click();
    return 'clicked';
}, title);

const clearCapture = (page) => page.evaluate(() => { window.__cap = []; });

const installCapture = (page) => page.evaluate(() => {
    window.__cap = [];
    const orig = window.fetch.bind(window);
    window.fetch = async (...args) => {
        const [url, opts] = args;
        const method = (opts && opts.method) || 'GET';
        const u = String(url || '');
        if (/^\s*(PUT|POST|DELETE)\s*$/.test(method) && u.includes('/api/lists')) {
            let body = null;
            try { body = opts && opts.body ? JSON.parse(opts.body) : null; } catch (e) {}
            window.__cap.push({ method, url: u, body });
        }
        return orig(...args);
    };
});

const readCapture = (page) => page.evaluate(() => (window.__cap || []).map((c) => ({ method: c.method, url: c.url })));

const typeAndSubmit = async (page, title) => {
    const typed = await page.evaluate(() => !!document.querySelector('input[type="text"]'));
    if (!typed) return false;
    await page.focus('input[type="text"]');
    await page.keyboard.type(title);
    await page.keyboard.press('Enter');
    await lib.sleep(1200);
    return true;
};

(async () => {
    const { page, browser, consoleErrors } = await lib.openBrowser({ blockRealtime: true });
    const { check, finish } = lib.createChecker('itemlevel-routing');

    let tempListId = null;
    let uid = null;
    try {
        await lib.openBoard(page);

        // Probe user identity (used for cleanup)
        uid = await page.evaluate(() => {
            try { return JSON.parse(localStorage.getItem('lt_user') || '{}').userId; } catch (e) { return null; }
        });
        check('autologin user resolved for cleanup', !!uid, uid);

        // Create disposable probe list
        const created = await lib.api('POST', '/api/lists',
            { userId: uid, username: 'admin', listName: LIST_NAME });
        tempListId = created.body && created.body.listId;
        check('temp probe list created', !!tempListId, tempListId);

        // Reload so sidebar contains new list
        await page.reload({ waitUntil: 'networkidle2' });
        await lib.openBoard(page);

        // Switch to probe list
        const switched = await page.evaluate((name) => {
            const el = Array.from(document.querySelectorAll('div'))
                .filter((d) => (d.className || '').includes('cursor-pointer'))
                .find((d) => (d.textContent || '').includes(name));
            if (!el) return false;
            el.click();
            return true;
        }, LIST_NAME);
        check('switched to probe list', switched, switched);
        await lib.sleep(800);

        // Create three tasks in probe list
        check('item A created via UI', await typeAndSubmit(page, ITEM_A));
        check('item B created via UI', await typeAndSubmit(page, ITEM_B));
        check('item C created via UI', await typeAndSubmit(page, ITEM_C));

        const afterCreate = await lib.getList(tempListId);
        const aId = afterCreate.items.find((i) => i.title === ITEM_A).itemId;
        const bId = afterCreate.items.find((i) => i.title === ITEM_B).itemId;
        const cId = afterCreate.items.find((i) => i.title === ITEM_C).itemId;
        check('all three probe items present on server', !!aId && !!bId && !!cId, { aId, bId, cId });

        // ---- Scenario 1: Single item change -> item-level PUT ----
        await installCapture(page);
        const r1 = await clickToggleByTitle(page, ITEM_A);
        check('toggle A button clicked', r1 === 'clicked', r1);
        await lib.sleep(900); // Wait out 600ms debounce
        const cap1 = await readCapture(page);
        const lvl1 = cap1.filter(isItemLevel);
        const whole1 = cap1.filter(isWholeList);
        check('single edit routes to item-level PUT', lvl1.length === 1, cap1);
        check('single edit does NOT call whole-list PUT', whole1.length === 0, cap1);
        check('item-level URL targets the right item',
            lvl1.length === 1 && lvl1[0].url.endsWith('/items/' + aId), lvl1[0] && lvl1[0].url);

        const afterA = await lib.getList(tempListId);
        const aNow = afterA.items.find((i) => i.itemId === aId);
        check('single edit persisted (A isDone=true, status=done)',
            aNow && aNow.isDone === true && aNow.status === 'done', aNow && { isDone: aNow.isDone, status: aNow.status });

        // ---- Scenario 2: Consecutive open item changes -> fallback to full PUT ----
        // Both B and C are open and visible, toggle both.
        await clearCapture(page);
        const r2a = await clickToggleByTitle(page, ITEM_B);
        const r2b = await clickToggleByTitle(page, ITEM_C);
        check('toggle B button clicked', r2a === 'clicked', r2a);
        check('toggle C button clicked', r2b === 'clicked', r2b);
        await lib.sleep(900);
        const cap2 = await readCapture(page);
        const lvl2 = cap2.filter(isItemLevel);
        const whole2 = cap2.filter(isWholeList);
        check('multi-edit does NOT use item-level endpoint', lvl2.length === 0, cap2);
        check('multi-edit falls back to whole-list PUT', whole2.length === 1, cap2);

        const real = lib.realErrors(consoleErrors, ['io is not defined']);
        check('no unexpected console errors', real.length === 0, real);
    } catch (err) {
        check('script completed without throwing', false, String(err && err.message));
        try { await lib.shot(page, 'itemlevel_routing_error'); } catch (e) {}
    } finally {
        // Cleanup: delete disposable probe list
        if (tempListId) {
            const del = await lib.api('DELETE',
                '/api/lists/' + tempListId + '?userId=' + encodeURIComponent(uid || '') + '&confirm=true');
            check('probe list cleaned up', del.status === 200 || del.status === 404,
                { status: del.status, body: del.body });
        }
        await browser.close();
    }

    finish();
})();
