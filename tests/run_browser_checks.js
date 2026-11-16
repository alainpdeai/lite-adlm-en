/**
 * M1 entry point — one command runs every browser check.
 *
 * Each check asserts against the running server in a real Chrome and returns
 * a non-zero exit code when an assertion fails. This runner turns that into a
 * single pass/fail, and prints the tail of any check that crashes so the
 * failure is visible without re-running it by hand.
 *
 * Usage: node tests/run_browser_checks.js
 *        node tests/run_browser_checks.js --only exam
 */
const { spawnSync } = require('child_process');
const path = require('path');

const CHECKS = [
    { file: 'browser_conflict_check.js', name: 'save-conflict' },
    { file: 'browser_ui_check.js', name: 'ui-columns-and-overview' },
    { file: 'browser_gaps_panel_check.js', name: 'gaps-panel' },
    { file: 'browser_exam_check.js', name: 'exam-category' },
    { file: 'browser_front_newtask_check.js', name: 'front-new-task-provenance' },
    { file: 'browser_exam_case01_check.js', name: 'exam-case-01' },
    { file: 'browser_exam_case02_check.js', name: 'exam-case-02' },
    { file: 'browser_exam_case03_check.js', name: 'exam-case-03' },
    { file: 'browser_render_baseline_check.js', name: 'dom-render-baseline' }
];

const only = process.argv.includes('--only')
    ? process.argv[process.argv.indexOf('--only') + 1]
    : null;
const selected = only
    ? (only.endsWith('.js')
        ? [{ file: only, name: only.replace(/\.js$/, '') }]
        : CHECKS.filter((c) => c.name.includes(only) || c.file.includes(only)))
    : CHECKS;

if (!selected.length) {
    console.error('no check matches --only ' + only);
    process.exit(2);
}

// All checks of one aggregate run share a single artifacts run directory
// (browser_lib reads LITETASK_RUN_ID); spawnSync children inherit the env.
process.env.LITETASK_RUN_ID = new Date().toISOString().replace(/[-:.]/g, '')
    + '_pid' + process.pid;

const rows = [];
for (const c of selected) {
    const started = Date.now();
    const r = spawnSync(process.execPath, [path.join(__dirname, c.file)],
        { encoding: 'utf8' });
    const out = (r.stdout || '') + (r.stderr || '');
    const m = out.match(/RESULT\[[^\]]*\]:\s*(\d+)\/(\d+) passed/);
    const failures = (out.match(/^  FAILED: .*$/gm) || [])
        .map((s) => s.replace('  FAILED: ', ''));

    const ok = r.status === 0 && !!m;
    rows.push({
        name: c.name, passed: m ? +m[1] : 0, total: m ? +m[2] : 0,
        ms: Date.now() - started, ok, failures, out
    });

    const secs = ((Date.now() - started) / 1000).toFixed(1);
    console.log('  %s  %s  %s',
        ok ? 'PASS' : 'FAIL',
        c.name.padEnd(26),
        m ? `${m[1]}/${m[2]} passed  (${secs}s)` : 'crashed, no RESULT line');

    if (!ok) {
        const lines = out.trim().split('\n');
        console.log(lines.slice(-15).map((l) => '        ' + l).join('\n'));
    }
}

const passed = rows.reduce((a, r) => a + r.passed, 0);
const total = rows.reduce((a, r) => a + r.total, 0);
const bad = rows.filter((r) => !r.ok);

console.log('\n=== browser checks: %d/%d assertions across %d checks ===',
    passed, total, rows.length);
if (bad.length) {
    bad.forEach((r) => console.log('  %s failed: %s', r.name, r.failures.join(', ') || 'crashed'));
    process.exitCode = 1;
} else {
    console.log('ALL GREEN');
}
