/**
 * Exam case 03 as filed on the board — rendered check.
 *
 * The exam entry carries the "archiving moves storage, not evidence" answer in
 * its note, so it is only useful if the UI actually shows it. Read-only: the
 * entry is never modified or deleted here.
 *
 * Two traps, both inherited from the earlier cases:
 *  - the board hides completed work by default, and this case ends up *closed*;
 *    force Show Closed before looking for it.
 *  - the board now holds three exam cases, so the first Notes button on the page
 *    is not this row's. Use clickNotesInRow(page, title).
 */
const lib = require('./browser_lib');

const CASE_TITLE = 'Exam Case 03: Archiving Moves Storage Not Evidence';

(async () => {
    const { page, browser, consoleErrors } = await lib.openBrowser();
    const { check, finish } = lib.createChecker('exam-case-03');

    try {
        await lib.openBoard(page);

        // the entry must exist in the data, not just on screen
        const exam = await lib.getList('exam');
        const entry = exam.items.find((i) => i.title === CASE_TITLE);
        const CASE_ID = entry ? entry.itemId : null;
        check('exam case 03 exists in the exam list', !!entry,
            exam.items.map((i) => i.title));
        check('its note records the standard answer',
            !!entry && (entry.comment.includes('Archiving = moving storage, not retracting evidence') )
            && (entry.comment.includes('Reverse contrast') ),
            !!entry ? entry.comment.slice(0, 40) : null);
        check('the note is not empty', !!entry && entry.comment.length > 200,
            !!entry ? entry.comment.length : null);

        // switch to the exam list (sidebar entries are divs with @click)
        const switched = await page.evaluate(() => {
            const el = Array.from(document.querySelectorAll('div'))
                .filter((d) => (d.className || '').includes('cursor-pointer'))
                .find((d) => (d.textContent || '').includes('Benchmarks & Acceptance'));
            if (!el) return false;
            el.click();
            return true;
        });
        check('exam list selectable in sidebar', switched, switched);
        await lib.sleep(800);

        const revealed = await page.evaluate(() => {
            const b = Array.from(document.querySelectorAll('button'))
                .find((x) => (x.textContent || '').includes('Show Closed'));
            if (b) { b.click(); return 'clicked'; }
            return 'already-shown';
        });
        check('completed work is visible for the case check', !!revealed, revealed);
        await lib.sleep(700);

        const shown = await page.evaluate(
            (t) => document.body.innerText.includes(t), CASE_TITLE);
        check('exam case 03 title rendered on the board', shown, shown);

        const expanded = await lib.clickNotesInRow(page, CASE_TITLE);
        check('Notes toggle of the case-03 row reachable', expanded === 'clicked', expanded);
        await lib.sleep(1100);

        const note = await page.evaluate(() => {
            const eds = Array.from(document.querySelectorAll('.ql-editor'));
            return eds.map((e) => (e.innerText || e.textContent || ''));
        });
        const mine = note.find((t) => (t.includes('moving storage') ) && (t.includes('contrast') ));
        check('expanded note shows the case-03 answer text', !!mine,
            note.length ? note.map((t) => t.replace(/\s+/g, ' ').slice(0, 60))
                : 'no .ql-editor on the page');

        await lib.shot(page, 'exam_case03_entry');

        // the verifies edge to the F3 feature must be in the link graph
        const links = await lib.api('GET', '/api/links');
        const edge = CASE_ID
            ? (links.body.edges || []).find((e) =>
                (e.from && e.from.itemId === CASE_ID) ||
                (e.source && e.source === CASE_ID))
            : null;
        check('verifies edge exam -> func(F3 reverse trace) present in the graph', !!edge,
            edge ? JSON.stringify(edge).slice(0, 120) : null);

        const real = lib.realErrors(consoleErrors);
        check('no unexpected console errors', real.length === 0, real);
    } catch (err) {
        check('script completed without throwing', false, String(err && err.message));
        try { await lib.shot(page, 'exam_case03_error'); } catch (e) {}
    } finally {
        await browser.close();
    }

    finish();
})();
