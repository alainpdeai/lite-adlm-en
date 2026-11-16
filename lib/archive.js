'use strict';
const { createArchiveCore } = require('./archive_core');
const { createArchiveRoutes } = require('./archive_routes');

// Archive aggregator (route ①, Round 8). lib/archive.js used to hold both the data
// helpers and the HTTP surface in one register() closure; it is now a thin seam that
// builds the core, hands it to the routes, and keeps the two module-level exports
// the rest of the app relies on.
//
//   server.js -> archive.register(app, io, { requireConfirm, getCategories })
//                   |- archive_core.createArchiveCore({ getCategories })
//                   '- archive_routes.createArchiveRoutes(app, io, { requireConfirm, core })
//
// Dependency direction stays one-way: routes -> core -> config/util, so there is no
// cycle back into server.js scope.

let _autoArchiveSweep = null;
let _getArchivePolicy = null;
let _recoverInterruptedTransactions = null;

const register = (app, io, deps) => {
    const requireConfirm = deps.requireConfirm;
    const getCategories = deps.getCategories;
    const writeAudit = deps.writeAudit;

    const core = createArchiveCore({ getCategories, writeAudit });
    createArchiveRoutes(app, io, { requireConfirm, core });

    _autoArchiveSweep = core.autoArchiveSweep;
    _getArchivePolicy = core.getArchivePolicy;
    _recoverInterruptedTransactions = core.recoverInterruptedTransactions;
};

// Called with no argument by the startup sweep in server.js. Before register() the
// sweep has nothing to run, so this resolves instead of throwing — identical to the
// old forwarder.
const autoArchiveSweep = (...args) =>
    (_autoArchiveSweep ? _autoArchiveSweep(...args) : Promise.resolve());

// Exported for parity with the old module surface; no caller outside this module
// uses it today. Fails loudly rather than inventing a policy if it is called before
// register(), where the old code failed with a TypeError on a null loader.
const getArchivePolicy = async (...args) => {
    if (!_getArchivePolicy) {
        throw new Error('getArchivePolicy() called before archive.register()');
    }
    return _getArchivePolicy(...args);
};

const recoverInterruptedTransactions = (...args) => (
    _recoverInterruptedTransactions
        ? _recoverInterruptedTransactions(...args)
        : Promise.resolve({ recovered: 0, committed: 0, failed: 0 })
);

module.exports = {
    register,
    autoArchiveSweep,
    getArchivePolicy,
    recoverInterruptedTransactions
};
