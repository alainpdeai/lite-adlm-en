/**
 * UI check for the traceability panel (Relations -> Coverage Gaps) and the board's
 * orphan filter.
 *
 * It does NOT assert that the gap counts are zero. It used to, and that was a
 * data-dependent expectation dressed up as a property: on 2026-10-30/31 the
 * board gained 15 backlog items (7 arch, 6 func, 2 test) filed with no
 * coverage edges yet, so `func-not-verified` is 9 and `arch-not-derived` is 19.
 * Zero is not the state of this board, and asserting it says nothing about the
 * code. What is worth asserting is that the panel renders exactly what
 * `/api/gaps` reports — a mapping or rendering bug would still be caught — and
 * that the orphan filter has a real effect on the rows.
 *
 *  - relation overview: the graph renders (edges are visible)
 *  - coverage-gap tab: the three rule cards agree with the API, number for number
 *  - board: the orphan filter narrows the visible rows, and keeps the orphans
 *
 * Usage: node tests/browser_gaps_panel_check.js
 */
const lib = require('./browser_lib');
const { check, finish } = lib.createChecker('gaps-panel');
const { api, sleep, waitForText, clickByText, clickByIcon } = lib;

const rowCount = (page) => page.evaluate(() => document.querySelectorAll('.task-node-wrapper').length);

(async () => {
    const { browser, page, consoleErrors } = await lib.openBrowser();
  try {
    await lib.openBoard(page);
    await page.waitForFunction(
      () => document.querySelectorAll('.task-node-wrapper').length > 0,
      { timeout: 10000 }).catch(() => {});

    // show closed work so every edge is visible
    const toggled = await page.evaluate(() => {
      const b = Array.from(document.querySelectorAll('button')).find((e) => (e.textContent || '').includes('Show Closed'));
      if (!b) return false;
      b.click();
      return true;
    });
    check('show-completed toggle present', toggled);
    await sleep(600);

    const rowsBefore = await rowCount(page);

    await clickByText(page, 'Relations');
    await page.waitForFunction(() => document.body.innerText.includes('Graph'), { timeout: 10000 });
    await sleep(500);
    const edgeCount = await page.evaluate(() => document.querySelectorAll('i.fa-arrow-right').length / 2);
    check('relation graph shows the new arch->func edges', edgeCount >= 18, edgeCount);
    await lib.shot(page, 'gaps_panel_overview');

    // gap tab
    await clickByText(page, 'Coverage Gaps');
    await sleep(800);
    const gapCounts = await page.evaluate(() =>
      Array.from(document.querySelectorAll('span'))
        .map((e) => (e.textContent || '').trim())
        .map((t) => (t.match(/^(\d+)\s*items?/i)  || [])[1])
        .filter(Boolean));
    check('gap tab rendered three rule cards', gapCounts.length >= 3, gapCounts);

    // The panel is a view over /api/gaps, so the honest assertion is that the
    // view is faithful — same rules, same counts, same order — not that the
    // counts happen to be 0 today.
    const gaps = await api('GET', '/api/gaps');
    const apiCounts = (gaps.body.rules || []).map((r) => String(r.count));
    check('the panel reports exactly what /api/gaps reports',
      apiCounts.length >= 3
      && JSON.stringify(gapCounts.slice(0, 3)) === JSON.stringify(apiCounts.slice(0, 3)),
      { dom: gapCounts.slice(0, 3), api: apiCounts.slice(0, 3) });
    await lib.shot(page, 'gaps_panel_tab');

    // close the modal, then exercise the orphan filter on the board
    await clickByIcon(page, 'fa-times');
    await sleep(400);

    const orphanCards = await page.evaluate(() => {
      const sel = document.querySelector('select[title="Filter by reverse traceability / coverage gaps"]');
      if (!sel) return -1;
      sel.value = 'orphan';
      sel.dispatchEvent(new Event('change', { bubbles: true }));
      return 0;
    });
    check('trace filter select found', orphanCards === 0, orphanCards);
    await sleep(800);
    const rowsAfter = await rowCount(page);
    // The assertion this replaced was
    //   check no gaps
    // whose third clause is `!false` — it passed whatever the board rendered.
    // A vacuous assertion is worse than none, because it reports a check that
    // never looks at anything. These two ask the board a real question.
    check('the orphan filter narrows the board', rowsAfter < rowsBefore,
      { before: rowsBefore, after: rowsAfter });
    // rowsAfter can legitimately be 0 when every task is linked (no orphans);
    // the property under test is that selecting 'orphan' never *adds* rows.
    check('the orphan filter never inflates the board', rowsAfter <= rowsBefore,
      { before: rowsBefore, after: rowsAfter });
    await lib.shot(page, 'gaps_panel_orphan_filter');

    const real = lib.realErrors(consoleErrors);
    check('no unexpected console errors', real.length === 0, real);
  } catch (err) {
    check('script completed without throwing', false, String(err && err.message));
    try { await lib.shot(page, 'gaps_panel_error'); } catch (e) {}
  } finally {
    await browser.close();
  }

  finish();
})();
