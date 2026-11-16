/**
 * Exam case 01 as filed on the board — rendered check.
 *
 * The exam entry carries the answer in its note, so it is only useful if the
 * UI actually shows it: title on the board, note readable when expanded, and
 * the verifies edge to the F1 feature visible in the relation overview.
 *
 * Read-only: the exam entry is never modified or deleted here.
 */
const lib = require('./browser_lib');

// Look the entry up by title, not by id: ids change if the entry is ever
// re-filed, and a hardcoded id turns a benign re-run into a false failure.
const CASE_TITLE = 'Exam Case 01: Five-state Machine Flow Matrix (25 cells)';

(async () => {
    const { page, browser, consoleErrors } = await lib.openBrowser();
    const { check, finish } = lib.createChecker('exam-case-01');

    try {
        await lib.openBoard(page);

        // the entry must exist in the data, not just on screen
        const exam = await lib.getList('exam');
        const entry = exam.items.find((i) => i.title === CASE_TITLE);
        const CASE_ID = entry ? entry.itemId : null;
        check('exam case 01 exists in the exam list', !!entry,
            exam.items.map((i) => i.title));
        check('its note carries the recorded answer (22 accepted / 3 rejected)',
            !!entry && (entry.comment.includes('22 accepted / 3 rejected') ),
            !!entry ? entry.comment.slice(0, 40) : null);

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

        // The board hides completed work by default (F5). Once this case is
        // closed — which is the whole point of finishing it — the list renders
        // zero rows and every check below would pass against an empty board.
        // Force completed work visible first (idempotent: the button is gone
        // once already on).
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
        check('exam case title rendered on the board', shown, shown);

        // The note lives behind the Notes toggle (showComment/toggleComment).
        // Clicking the row only selects it; "Expand All" only affects subtasks.
        // Target this row's toggle: the board holds two exam cases now, and the
        // first Notes button on the page is not necessarily this entry's.
        const expanded = await lib.clickNotesInRow(page, CASE_TITLE);
        check('Notes toggle of the case-01 row reachable', expanded === 'clicked', expanded);
        await lib.sleep(1100);

        // The note is rendered by Quill into a contenteditable .ql-editor,
        // whose text is not part of document.body.innerText in every state.
        // Ask the editors directly, and dump a snippet when it is missing.
        await lib.sleep(900);
        const notes = await page.evaluate(() => Array.from(
            document.querySelectorAll('.ql-editor'))
            .map((e) => (e.innerText || e.textContent || '')));
        const mine = notes.find((t) => t.includes('22 accepted / 3 rejected') );
        check('expanded note shows the answer text', !!mine,
            notes.length ? notes.map((t) => t.replace(/\s+/g, ' ').slice(0, 60))
                : 'no .ql-editor on the page');

        await lib.shot(page, 'exam_case01_entry');

        // the verifies edge to the F1 feature must be in the link graph
        const links = await lib.api('GET', '/api/links');
        const edge = CASE_ID
            ? (links.body.edges || []).find((e) =>
                (e.from && e.from.itemId === CASE_ID) ||
                (e.source && e.source === CASE_ID))
            : null;
        check('verifies edge exam -> func(F1) present in the graph', !!edge,
            edge ? JSON.stringify(edge).slice(0, 120) : null);

        // and the exam category must NOT count as test coverage
        const gaps = await lib.api('GET', '/api/gaps');
        const rule = (gaps.body.rules || []).find(
            (r) => r.value === 'func-not-verified' || r.label === 'Feature not verified by test' );
        check('the func-not-verified rule is still reported',
            !!rule && typeof rule.count === 'number', rule && rule.count);
        // Filing a case must never close a coverage gap on its own. The property
        // under test is "the exam entry's own edge is not what covers the F1
        // feature" — NOT "the board has no gaps". This check used to assert
        // `count === 0`; the backlog has grown by 15 items since then and
        // `func-not-verified` is 9 today, so that assertion fails for reasons
        // that have nothing to do with the exam entry. Assert the property
        // instead: remove every edge whose source is the `exam` list, and the F1
        // feature must still be covered.
        const f1Id = edge && edge.to && edge.to.itemId;
        const verifiers = (links.body.edges || [])
            .filter((e) => e.relation === 'verifies'
                && e.to && e.to.itemId === f1Id && e.to.listId === 'func')
            .map((e) => ((e.from || {}).listId || '?') + ':' + ((e.from || {}).itemId || '?'));
        const withoutExam = verifiers.filter((v) => !v.startsWith('exam:'));
        check('the F1 feature is covered without the exam entry',
            verifiers.length > 0 && withoutExam.length > 0,
            { f1Id, verifiers, withoutExam });

        const real = lib.realErrors(consoleErrors);
        check('no unexpected console errors', real.length === 0, real);
    } catch (err) {
        check('script completed without throwing', false, String(err && err.message));
        try { await lib.shot(page, 'exam_case01_error'); } catch (e) {}
    } finally {
        await browser.close();
    }

    finish();
})();
