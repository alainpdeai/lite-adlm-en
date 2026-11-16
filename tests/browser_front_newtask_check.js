/**
 * Can the Agent tell a human-created task from its own?
 *
 * Probe: create a task through the real UI (exactly what a human does) into the
 * empty `exam` list, then read the JSON back and inspect the provenance
 * fields. The task is deleted at the end so the list returns to 0 items.
 */
const lib = require('./browser_lib');

const LIST = 'exam';
const TITLE = 'UI-Human-Created-Trace-Probe';

(async () => {
    const { page, browser, consoleErrors } = await lib.openBrowser();
    const { check, finish } = lib.createChecker('front-new-task');

    try {
        await lib.openBoard(page);

        // snapshot first — the restore at the end must put back exactly this
        const before = await lib.getList(LIST);
        check('exam list snapshot taken', Array.isArray(before.items),
            before.items.map((i) => i.itemId));

        // switch to the exam list via the sidebar (entries are divs with @click)
        const switched = await page.evaluate(() => {
            const el = Array.from(document.querySelectorAll('div'))
                .filter((d) => (d.className || '').includes('cursor-pointer'))
                .find((d) => (d.textContent || '').includes('Benchmarks & Acceptance'));
            if (!el) return false;
            el.click();
            return true;
        });
        check('sidebar entry for exam category is clickable', switched, switched);
        await lib.sleep(800);

        const heading = await page.evaluate(() => {
            const h = document.querySelector('h2');
            return h ? h.textContent.trim() : null;
        });
        check('board switched to Benchmarks & Acceptance', heading === 'Benchmarks & Acceptance', heading);

        // type the title into the new-task input and submit
        const typed = await page.evaluate(() => {
            const inp = document.querySelector('input[type="text"]');
            if (!inp) return false;
            inp.focus();
            return true;
        });
        check('new-task input present', typed, typed);
        if (typed) await page.keyboard.type(TITLE);
        await page.keyboard.press('Enter');
        await lib.sleep(1500);

        // read the truth from disk-backed API, not from the DOM
        const after = await lib.getList(LIST);
        const created = after.items.find((i) => i.title === TITLE);
        check('human-created task reached the server', !!created,
            after.items.map((i) => i.title));

        if (created) {
            console.log('        provenance of the UI-created task:');
            for (const k of ['itemId', 'status', 'createdBy', 'createdByAgent',
                'localDirectory', 'comment', 'relatesTo', 'createdAt']) {
                console.log('          %s = %s', (k + '            ').slice(0, 14),
                    JSON.stringify(created[k]));
            }
            // The whole point: can we tell it was NOT created by an Agent?
            check('createdByAgent is distinguishable from the Agent default',
                created.createdByAgent !== 'AI Agent',
                'createdByAgent=' + JSON.stringify(created.createdByAgent));

            await lib.shot(page, 'front_new_task');

            // Restore to the SNAPSHOT, never to a hardcoded empty list. This
            // check once wiped a real exam entry that was filed after it was
            // written — a restore that assumes "the list was empty" is a
            // delete waiting to happen.
            await lib.putList(LIST, before.items, null, { force: true });
            const restored = await lib.getList(LIST);
            check('exam list restored to its pre-test id set',
                JSON.stringify(restored.items.map((i) => i.itemId)) ===
                    JSON.stringify(before.items.map((i) => i.itemId)),
                { before: before.items.map((i) => i.itemId),
                  after: restored.items.map((i) => i.itemId) });
        }

        const real = lib.realErrors(consoleErrors);
        check('no unexpected console errors', real.length === 0, real);
    } catch (err) {
        check('script completed without throwing', false, String(err && err.message));
        try { await lib.shot(page, 'front_new_task_error'); } catch (e) {}
    } finally {
        await browser.close();
    }

    finish();
})();
