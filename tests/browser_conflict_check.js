/**
 * B3 follow-up browser check (real Chrome via puppeteer-core).
 *
 * Replays a genuine two-writer race against the running server:
 *   1. open the board (socket.io blocked so no realtime refresh hides the race)
 *   2. an external client modifies the list  -> server rev moves on
 *   3. the browser saves its own edit        -> 409 REV_CONFLICT -> diff modal
 *   4. "Overwrite with My Version"                     -> server ends up with the browser's copy
 *   5. repeat, then "Keep All Server"           -> browser drops its unsaved edit
 *
 * Usage: node tests/browser_conflict_check.js
 */
const lib = require('./browser_lib');
const { check, finish } = lib.createChecker('save-conflict');
const { api, sleep, getList, waitForText, clickByText } = lib;

(async () => {
  // Block realtime pushes: otherwise the board would silently refresh to the
  // newer rev and the race we want to test would never happen.
  const { browser, page, consoleErrors, dialogs } = await lib.openBrowser({ blockRealtime: true });

  const listId = 'arch';
  const original = await getList(listId);
  console.log('list:', listId, 'rev:', original.rev, 'items:', original.items.length);

  try {
    await lib.openBoard(page);
    check('board loaded', true);

    /* ---------- scenario 1: keep my version ---------- */
    // external writer moves the rev on
    const ext = JSON.parse(JSON.stringify(original.items));
    ext[0].comment = 'External client comment';
    ext[0].priority = 'High';
    const r1 = await api('PUT', '/api/lists/' + listId,
      { type: 'UPDATE_ITEMS', items: ext, userId: 'user_admin', baseRev: original.rev });
    check('external writer bumped the rev', r1.status === 200 && r1.body.rev !== original.rev, r1.status);

    await page.click('input[placeholder="What needs to be done? Press Enter."]');
    await page.keyboard.type('B3-Conflict-Adopt-Mine');
    await page.keyboard.press('Enter');
    await waitForText(page, 'Save Conflict', 20000);
    check('conflict dialog opened on 409', true);

    const diffBar = await page.evaluate(() => {
      const el = Array.from(document.querySelectorAll('span'))
        .map((e) => e.textContent.trim())
        .filter((t) => t.includes('My additions') || t.includes('Server additions') || t.includes('Both modified'));
      return el;
    });
    check('diff summary chips rendered', diffBar.length >= 3, diffBar);

    const rows = await page.evaluate(() =>
      Array.from(document.querySelectorAll('.grid-cols-\\[110px_1fr_1fr\\]')).length);
    check('field-diff rows rendered', rows >= 1, rows);

    const hasBothSides = await page.evaluate(() => {
      const t = document.body.innerText;
      return (t.includes('My') || t.includes('Mine')) && (t.includes('Server') || t.includes('External client comment'));
    });
    check('both sides of the conflict shown (incl. external value)', hasBothSides);

    await lib.shot(page, 'conflict_dialog');

    await clickByText(page, 'Overwrite with My Version');
    await sleep(2000);
    // Security boundary P2-C: adopting my version overwrites the whole list, so the UI
    // must ask before it sends `confirm: true`. It asks with a native
    // confirm(), which blocks the renderer until somebody answers it — with no
    // dialog handler this check used to die here with "Runtime.callFunctionOn
    // timed out", which reads like a rendering fault and is a modal nobody
    // dismissed. browser_lib now records and accepts every dialog.
    const asked = dialogs.find((d) => (d.message || '').includes('overwrite') || (d.message || '').includes('Using your version'));
    check('destructive overwrite asks for confirmation first', !!asked,
      dialogs.map((d) => (d.message || '').slice(0, 48)));
    const gone = await page.evaluate(() => !document.body.innerText.includes('Save Conflict'));
    check('dialog closed after adopting my version', gone);
    await lib.shot(page, 'conflict_resolved_mine');

    const afterMine = await getList(listId);
    const titles = afterMine.items.map((i) => i.title);
    check('my new task landed on the server', titles.includes('B3-Conflict-Adopt-Mine'), titles.slice(0, 3));
    check('external edit was overwritten (force semantics)',
      afterMine.items[0].comment !== 'External client comment', afterMine.items[0].comment);
    check('my unsaved task visible in board',
      await page.evaluate(() => document.body.innerText.includes('B3-Conflict-Adopt-Mine')));

    /* ---------- scenario 2: keep the server version ---------- */
    const base2 = await getList(listId);
    const ext2 = JSON.parse(JSON.stringify(base2.items));
    ext2[0].comment = 'Second round external write';
    const r2 = await api('PUT', '/api/lists/' + listId,
      { type: 'UPDATE_ITEMS', items: ext2, userId: 'user_admin', baseRev: base2.rev });
    check('second external write ok', r2.status === 200, r2.status);

    await page.click('input[placeholder="What needs to be done? Press Enter."]');
    await page.keyboard.type('B3-Conflict-Should-Discard');
    await page.keyboard.press('Enter');
    await waitForText(page, 'Save Conflict', 20000);
    await clickByText(page, 'Keep All Server');
    await sleep(2000);

    const afterServer = await getList(listId);
    check('dropped task never reached the server',
      !afterServer.items.some((i) => i.title === 'B3-Conflict-Should-Discard'),
      afterServer.items.map((i) => i.title).slice(0, 3));
    check('server value kept for the conflicted field',
      afterServer.items[0].comment === 'Second round external write', afterServer.items[0].comment);
    await lib.shot(page, 'conflict_resolved_server');

    /* ---------- scenario 3: per-field merge (apply selected) ---------- */
    const base3 = await getList(listId);
    const ext3 = JSON.parse(JSON.stringify(base3.items));
    ext3[0].comment = 'Third round external write';
    const r3 = await api('PUT', '/api/lists/' + listId,
      { type: 'UPDATE_ITEMS', items: ext3, userId: 'user_admin', baseRev: base3.rev });
    check('third external write ok', r3.status === 200, r3.status);

    await page.click('input[placeholder="What needs to be done? Press Enter."]');
    await page.keyboard.type('B3-Conflict-Apply-Merge');
    await page.keyboard.press('Enter');
    await waitForText(page, 'Save Conflict', 20000);
    // pick the SERVER side for the conflicted field, keep my new task
    await clickByText(page, 'Server');
    await sleep(300);
    await clickByText(page, 'Apply Selected Merge');
    await sleep(2000);

    const afterMerge = await getList(listId);
    // the merge unshifts new items to the top, so locate the conflicted item by id
    const targetId = base3.items[0].itemId;
    const tgt = afterMerge.items.find((i) => i.itemId === targetId);
    check('merge kept my new task',
      afterMerge.items.some((i) => i.title === 'B3-Conflict-Apply-Merge'),
      afterMerge.items.map((i) => i.title).slice(0, 3));
    check('merge kept the server value for the field I did not take',
      tgt && tgt.comment === 'Third round external write', tgt && tgt.comment);
    check('merge did not drop pre-existing items',
      afterMerge.items.length === base3.items.length + 1,
      afterMerge.items.length + ' vs ' + base3.items.length);
    await lib.shot(page, 'conflict_resolved_merge');

    /* ---------- scenario 4: plain save must still work (no conflict) ---------- */
    const base4 = await getList(listId);
    await page.click('input[placeholder="What needs to be done? Press Enter."]');
    await page.keyboard.type('B3-Regression-Normal-Save');
    await page.keyboard.press('Enter');
    await sleep(2500);
    const afterPlain = await getList(listId);
    check('plain save (no conflict) still lands on the server',
      afterPlain.items.some((i) => i.title === 'B3-Regression-Normal-Save'),
      afterPlain.items.map((i) => i.title).slice(0, 2));
    check('plain save kept the previous content',
      afterPlain.items.length === base4.items.length + 1,
      afterPlain.items.length + ' vs ' + base4.items.length);
    check('no conflict dialog for a clean save',
      await page.evaluate(() => !document.body.innerText.includes('Save Conflict')));

    // 409 is the conflict we deliberately provoke; 404 is the favicon.
    const realErrors = lib.realErrors(consoleErrors, ['404', '409']);
    check('no unexpected console errors', realErrors.length === 0, realErrors);
  } catch (err) {
    check('script completed without throwing', false, String(err && err.message));
    try { await lib.shot(page, 'conflict_error'); } catch (e) {}
  } finally {
    // restore the board to its pre-test content
    await lib.putList(listId, original.items, null,
      { force: true, userId: 'user_admin' });
    const restored = await getList(listId);
    check('board restored to pre-test content',
      JSON.stringify(restored.items) === JSON.stringify(original.items),
      restored.items.length + ' vs ' + original.items.length);
    await browser.close();
  }

  finish();
})();
