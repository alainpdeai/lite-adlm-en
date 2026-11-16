/**
 * Fourth category Benchmarks & Acceptance (exam) — rendered in a real browser.
 *
 * Proves the category is usable, not just present in the API: it appears in
 * the sidebar with its own colour dot, can be selected, and renders entries.
 *
 * Usage: node tests/browser_exam_check.js
 */
const lib = require('./browser_lib');
const { check, finish } = lib.createChecker('exam-category');
const { sleep, getList, putList } = lib;

const EXAM_ITEM = 'tmp_exam_ui_case';
const TITLE = 'EXAM-UITEMP Standard Regression Scenario';
const EXAM_COLOR = 'rgb(217, 119, 6)';

const selectExamList = (page) => page.evaluate(() => {
    const el = Array.from(document.querySelectorAll('div'))
        .filter((d) => (d.className || '').includes('cursor-pointer'))
        .find((d) => (d.textContent || '').includes('Benchmarks & Acceptance'));
    if (!el) return false;
    el.click();
    return true;
});

(async () => {
    const { browser, page, consoleErrors } = await lib.openBrowser();
    const before = await getList('exam');

    try {
        await lib.openBoard(page);

        const sidebar = await page.evaluate(() => {
            const dot = document.querySelector('span[title="Benchmarks & Acceptance"]');
            const entry = Array.from(document.querySelectorAll('div'))
                .filter((d) => (d.className || '').includes('cursor-pointer'))
                .find((d) => (d.textContent || '').includes('Benchmarks & Acceptance'));
            return {
                dotColor: dot ? getComputedStyle(dot).backgroundColor : null,
                hasEntry: !!entry
            };
        });
        check('exam category dot uses its configured colour',
            sidebar.dotColor === EXAM_COLOR, sidebar);
        check('exam list appears in the sidebar', sidebar.hasEntry, sidebar);

        check('exam list is selectable', await selectExamList(page));
        await sleep(700);
        const heading = await page.evaluate(() => {
            const h = document.querySelector('h2');
            return h ? h.innerText.trim() : null;
        });
        check('board switched to Benchmarks & Acceptance', heading === 'Benchmarks & Acceptance', heading);

        // Append our temp entry instead of replacing the whole list — replacing
        // would drop real exam cases filed by others.
        const pre = await getList('exam');
        await putList('exam', pre.items.concat([{
            itemId: EXAM_ITEM, title: TITLE, status: 'open',
            priority: 'Medium', comment: 'UI verification temporary item'
        }]), pre.rev);
        await page.waitForFunction(
            (t) => document.body.innerText.includes(t), { timeout: 8000 }, TITLE);
        check('a standard case entry renders in the board', true);
        await lib.shot(page, 'exam_entry');

        // Remove ONLY our own temp entry. Wiping the whole list would delete
        // real exam cases that other people filed — which is exactly what this
        // script used to do.
        const cur = await getList('exam');
        await putList('exam', cur.items.filter((i) => i.itemId !== EXAM_ITEM), cur.rev);
        await page.waitForFunction(
            (t) => !document.body.innerText.includes(t), { timeout: 8000 }, TITLE);
        check('entry disappears once removed (file watcher pushed the change)', true);

        const real = lib.realErrors(consoleErrors);
        check('no unexpected console errors', real.length === 0, real);
    } catch (err) {
        check('script completed without throwing', false, String(err && err.message));
        try { await lib.shot(page, 'exam_error'); } catch (e) {}
    } finally {
        // Restore the SNAPSHOT, not a hardcoded empty list.
        const cur = await getList('exam');
        await putList('exam', before.items, cur.rev);
        const after = await getList('exam');
        check('exam list restored to its pre-test id set',
            JSON.stringify(after.items.map((i) => i.itemId)) ===
                JSON.stringify(before.items.map((i) => i.itemId)),
            { before: before.items.map((i) => i.itemId),
              after: after.items.map((i) => i.itemId) });
        await browser.close();
    }

    finish();
})();
