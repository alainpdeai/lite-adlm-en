/**
 * Exam case 02 as filed on the board — rendered check.
 *
 * The exam entry carries the four-path answer in its note, so it is only useful
 * if the UI actually shows it. Read-only: the entry is never modified or
 * deleted here.
 *
 * Same trap as exam case 01: the board hides completed work by default, and the
 * case is *closed* once it is finished — so force Show Closed before looking for
 * it, or every check below silently passes against an empty board.
 */
const lib = require('./browser_lib');

const CASE_TITLE = 'Exam Case 02: B3 Conflict Four Resolution Paths';

(async () => {
    const { page, browser, consoleErrors } = await lib.openBrowser();
    const { check, finish } = lib.createChecker('exam-case-02');

    try {
        await lib.openBoard(page);

        // the entry must exist in the data, not just on screen
        const exam = await lib.getList('exam');
        const entry = exam.items.find((i) => i.title === CASE_TITLE);
        const CASE_ID = entry ? entry.itemId : null;
        check('exam case 02 exists in the exam list', !!entry,
            exam.items.map((i) => i.title));
        check('its note records the four resolutions',
            !!entry && (entry.comment.includes('1. Adopt Mine') )
            && (entry.comment.includes('4. Cancel') ),
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
        check('exam case 02 title rendered on the board', shown, shown);

        // the note lives behind the Notes toggle — and it must be *this* row's
        // toggle: the board now holds two exam cases, and the first Notes button
        // on the page belongs to case 01.
        const expanded = await lib.clickNotesInRow(page, CASE_TITLE);
        check('Notes toggle of the case-02 row reachable', expanded === 'clicked', expanded);
        await lib.sleep(1100);

        const note = await page.evaluate(() => {
            const eds = Array.from(document.querySelectorAll('.ql-editor'));
            return eds.map((e) => (e.innerText || e.textContent || ''));
        });
        const mine = note.find((t) => (t.includes('Adopt Mine') ) && (t.includes('Cancel') ));
        check('expanded note shows the case-02 answer text', !!mine,
            note.length ? note.map((t) => t.replace(/\s+/g, ' ').slice(0, 60))
                : 'no .ql-editor on the page');

        await lib.shot(page, 'exam_case02_entry');

        // the verifies edge to the B3 feature must be in the link graph
        const links = await lib.api('GET', '/api/links');
        const edge = CASE_ID
            ? (links.body.edges || []).find((e) =>
                (e.from && e.from.itemId === CASE_ID) ||
                (e.source && e.source === CASE_ID))
            : null;
        check('verifies edge exam -> func(B3 follow-up) present in the graph', !!edge,
            edge ? JSON.stringify(edge).slice(0, 120) : null);

        const real = lib.realErrors(consoleErrors);
        check('no unexpected console errors', real.length === 0, real);
    } catch (err) {
        check('script completed without throwing', false, String(err && err.message));
        try { await lib.shot(page, 'exam_case02_error'); } catch (e) {}
    } finally {
        await browser.close();
    }

    finish();
})();
