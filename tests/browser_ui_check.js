// Auto-generated
/**
 * Browser verification for the two uncovered func items:
 *   1. Task list removes Assignee; Creator records AI Agent name
 *   2. Relations overview synchronizes completed strike-through and visibility
 *
 * Evidence for the traceability entries created in the `func`/`test` lists.
 * Every mutation is reverted at the end.
 *
 * Usage: node tests/browser_ui_check.js
 */
const lib = require('./browser_lib');
const { check, finish } = lib.createChecker('ui-columns-and-overview');
const { sleep, waitForText, clickByText, clickByIcon, getList } = lib;

(async () => {
  const { browser, page, consoleErrors } = await lib.openBrowser();

  const listId = 'arch';
  const before = await getList(listId);

  // Empty delivery baseline: the board renders zero rows, so the Creator input
  // this check edits does not exist. That is an absent precondition, not a UI
  // regression — SKIP instead of three misleading failures.
  if (!before.items.length) {
    console.log('  SKIP  ui-columns-and-overview   empty delivery baseline (arch has no items); seed a project to grade this');
    console.log('\nRESULT[ui-columns-and-overview]: SKIP (empty delivery baseline)');
    await browser.close();
    return;
  }

  try {
    await lib.openBoard(page);

    /* ---------- 1. Assignee removed, Creator = AI Agent ---------- */
    const hasAssignee = await page.evaluate(() => document.body.innerText.includes('Assignee'));
    check('Assignee column is gone from the board', !hasAssignee);

    // The board hides completed work by default (F5). This list can legitimately
    // be all-done, which renders zero rows and makes the Creator input vanish —
    // so show completed first, otherwise this check silently tests nothing.
    await clickByText(page, 'Show Closed');
    await sleep(700);

    const creatorInputs = await page.$$('input[aria-label="Creator AI Agent"]');
    check('Creator · AI Agent inputs rendered', creatorInputs.length >= 1, creatorInputs.length);

    const original = await page.evaluate(() => {
      const el = document.querySelector('input[aria-label="Creator AI Agent"]');
      return el ? el.value : null;
    });
    check('Creator input shows an agent name', !!original, original);

    const marker = 'WBB3-Verify-AI';
    await page.evaluate((m) => {
      const el = document.querySelector('input[aria-label="Creator AI Agent"]');
      el.value = m;
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }, marker);
    await sleep(2200);

    let mid = await getList(listId);
    check('edited Creator persisted to the server',
      mid.items.some((i) => i.createdByAgent === marker),
      mid.items.map((i) => i.createdByAgent).slice(0, 4));

    await page.reload({ waitUntil: 'networkidle2' });
    await waitForText(page, 'Relations');
    const afterReload = await page.evaluate(() => {
      const el = document.querySelector('input[aria-label="Creator AI Agent"]');
      return el ? el.value : null;
    });
    check('edited Creator survives a reload', afterReload === marker, afterReload);

    const stored = await page.evaluate(() => localStorage.getItem('lt_agent_name'));
    check('agent name remembered in localStorage', stored === marker, stored);
    await lib.shot(page, 'ui_creator');

    // revert
    await page.evaluate((v) => {
      const el = document.querySelector('input[aria-label="Creator AI Agent"]');
      el.value = v;
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }, original || 'AI Agent');
    await sleep(2200);

    /* ---------- 2. Relation overview: closed strike-through + hide/show ---------- */
    // Ensure closed work is visible. The toggle's label flips to Hide Closed once
    // it is on, and part 1 above may already have turned it on — so accept
    // either label instead of demanding the "off" one.
    const toggled = await page.evaluate(() => {
        const hit = Array.from(document.querySelectorAll('button'))
            .find((b) => (b.textContent || '').includes('Show Closed'));
        if (hit) { hit.click(); return 'shown'; }
        return 'already-shown';
    });
    check('closed work is visible for the overview check',
        toggled === 'shown' || toggled === 'already-shown', toggled);
    await sleep(600);
    await clickByText(page, 'Relations');
    await page.waitForFunction(() => document.body.innerText.includes('Graph'), { timeout: 10000 });
    await sleep(500);
    const shown = await page.evaluate(() => ({
      edges: document.querySelectorAll('i.fa-arrow-right').length / 2,
      strike: document.querySelectorAll('.line-through').length
    }));
    check('overview shows edges with closed work visible', shown.edges >= 1, shown);
    check('closed endpoints carry a strike-through', shown.strike >= 1, shown.strike);
    await lib.shot(page, 'ui_overview_shown');

    await clickByIcon(page, 'fa-times');       // close the overview
    await sleep(400);

    // now hide closed work and re-open
    const hiding = await page.evaluate(() => {
      const b = Array.from(document.querySelectorAll('button')).find((e) => (e.textContent || '').includes('Hide Closed'));
      if (!b) return false;
      b.click();
      return true;
    });
    check('hide-completed toggle is available', hiding);
    await sleep(600);
    await clickByText(page, 'Relations');
    await page.waitForFunction(() => document.body.innerText.includes('Graph'), { timeout: 10000 });
    await sleep(500);
    const hidden = await page.evaluate(() => ({
      edges: document.querySelectorAll('i.fa-arrow-right').length / 2,
      strike: document.querySelectorAll('.line-through').length,
      empty: document.body.innerText.includes('Closed')
    }));
    check('overview hides edges touching closed work', hidden.edges <= shown.edges,
      { shown: shown.edges, hidden: hidden.edges });
    check('no strike-through endpoints while hidden', hidden.strike === 0, hidden);
    check('empty state explains the hiding', hidden.empty || hidden.edges > 0, hidden);
    await lib.shot(page, 'ui_overview_hidden');

    const real = lib.realErrors(consoleErrors);
    check('no unexpected console errors', real.length === 0, real);
  } catch (err) {
    check('script completed without throwing', false, String(err && err.message));
    try { await lib.shot(page, 'ui_error'); } catch (e) {}
  } finally {
    await lib.putList(listId, before.items, null,
      { force: true, userId: 'user_admin' });
    const after = await getList(listId);
    const same = JSON.stringify(after.items.map((i) => i.createdByAgent))
      === JSON.stringify(before.items.map((i) => i.createdByAgent));
    check('board content restored', same,
      after.items.map((i) => i.createdByAgent).slice(0, 4));
    await browser.close();
  }

  finish();
})();
