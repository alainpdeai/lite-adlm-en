'use strict';

// P0 observability: request-log rotation (route ①, Round 7 split from logging.js).
// Depends only on fs/path/os + lib/config. Defines the LOG_DIR/LOG_FILE family
// and the serialised append chain. AUDIT_FILE (in audit.js) is derived from
// LOG_DIR, so audit.js imports LOG_DIR from here.

const fs = require('fs-extra');
const path = require('path');
const os = require('os');
const cfg = require('./config');

const LOG_DIR = process.env.LITETASK_LOG_DIR
    ? path.resolve(process.env.LITETASK_LOG_DIR)
    : path.join(os.tmpdir(), 'litetask-logs');
const LOG_FILE = path.join(LOG_DIR, 'access.log');
const LOG_MAX_BYTES = Math.max(1, Number(process.env.LITETASK_LOG_MAX_BYTES || 1024 * 1024));
const LOG_KEEP = Math.max(1, Number(process.env.LITETASK_LOG_KEEP || 3));

fs.ensureDirSync(LOG_DIR);

// Rotate by size: access.log -> .1 -> .2 ... the oldest is dropped. Writes are
// serialised through a promise chain so a rotation can never interleave with an
// append that is already in flight.
const rotateLogIfNeeded = async () => {
    try {
        const st = await fs.stat(LOG_FILE);
        if (st.size < LOG_MAX_BYTES) return;
    } catch (err) {
        return; // nothing written yet
    }
    for (let i = LOG_KEEP; i >= 1; i--) {
        const from = i === 1 ? LOG_FILE : `${LOG_FILE}.${i - 1}`;
        const to = `${LOG_FILE}.${i}`;
        if (!(await fs.pathExists(from))) continue;
        if (i === LOG_KEEP) await fs.remove(to);      // oldest generation goes
        await fs.move(from, to, { overwrite: true });
    }
};

let logChain = Promise.resolve();
const writeLogLine = (line) => {
    // A logging failure must never take a request down with it.
    logChain = logChain.then(async () => {
        try {
            await rotateLogIfNeeded();
            await fs.appendFile(LOG_FILE, line + '\n');
        } catch (err) {
            console.warn('[LiteTask] request log write failed:', err.message);
        }
    });
    return logChain;
};

module.exports = { LOG_DIR, LOG_FILE, LOG_MAX_BYTES, LOG_KEEP, rotateLogIfNeeded, writeLogLine };
