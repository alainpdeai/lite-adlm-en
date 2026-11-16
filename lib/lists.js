'use strict';
const { createListRoutes } = require('./lists_routes');
const { createItemRoutes } = require('./items');
const core = require('./lists_core');

// Lists/Items aggregator (route ①, Round 9). lib/lists.js used to hold the helpers,
// the four /api/lists routes, the three item routes and the integrity report in one
// register() closure; it is now a thin seam:
//
//   server.js -> lists.register(app, io, { getStatusConfig, collectStatuses,
//                                          sanitizeStatus, validateItems,
//                                          sanitizeRelatesTo, sanitizeLocalDirectories })
//                  |- lists_core   (ETag / actor / confirm gate / tree lookups /
//                  |                integrity index)  — depends on config + util only
//                  |- lists_routes (GET,POST,PUT,DELETE /api/lists + /api/integrity)
//                  '- items        (POST,PUT,DELETE /api/lists/:id/items[/:itemId])
//
// Dependency direction stays one-way (routes -> core -> config/util), so there is
// no cycle back into server.js scope.
//
// requireConfirm and actorOf are still exported from here: server.js destructures
// them for the shared-lists watcher, and archive.register() takes requireConfirm as
// an injected dep.

let _requireConfirm = null;
let _actorOf = null;

const register = (app, io, deps) => {
    const {
        getStatusConfig, collectStatuses, sanitizeStatus, validateItems,
        sanitizeRelatesTo, sanitizeLocalDirectories
    } = deps;

    createListRoutes(app, io, {
        core,
        getStatusConfig, collectStatuses, sanitizeStatus, validateItems,
        sanitizeRelatesTo, sanitizeLocalDirectories
    });
    createItemRoutes(app, io, {
        core,
        getStatusConfig, collectStatuses, sanitizeStatus, validateItems,
        sanitizeRelatesTo, sanitizeLocalDirectories
    });

    _requireConfirm = core.requireConfirm;
    _actorOf = core.actorOf;
};

module.exports = {
    register,
    requireConfirm: (...args) => (_requireConfirm ? _requireConfirm(...args) : undefined),
    actorOf: (...args) => (_actorOf ? _actorOf(...args) : Promise.resolve(undefined))
};
