'use strict';
const path = require('path');
const fs = require('fs-extra');

const cfg = require('./config');
const { SHARED_LISTS_DIR, ARCHIVE_DIR } = cfg;

const register = (app, io, deps) => {
    const getCategories = deps.getCategories;
    const getStatusConfig = deps.getStatusConfig;

    // Categories API — the three major software-dev task types + relation vocab
    app.get('/api/categories', async (req, res) => {
        try {
            const cfg = await getCategories();
            const sc = await getStatusConfig();
            res.json({
                categories: Array.isArray(cfg.categories) ? cfg.categories : [],
                relations: Array.isArray(cfg.relations) ? cfg.relations : [],
                statuses: sc.statuses,
                statusFlow: sc.flow,
                traceability: Array.isArray(cfg.traceability) ? cfg.traceability : []
            });
        } catch (err) {
            res.status(500).json({ error: 'Failed to read categories' });
        }
    });

    // Global relation graph, shared by /api/links, /api/trace and /api/gaps.
    //
    // It also reads data/archive/: archiving moves an item's *storage*, not its
    // *evidence*. A func item verified by a test item is still verified after that
    // test item is archived — dropping it from the graph turned every archived
    // verifier into a fresh "func-not-verified" gap. Archived nodes/edges carry
    // `archived: true` so consumers can tell the two apart; /api/gaps uses them as
    // evidence but never reports them as gaps (see below).
    const buildLinkGraph = async () => {
        await fs.ensureDir(SHARED_LISTS_DIR);
        const nodes = {};
        const edges = [];
        const visit = (listId, listName, it, archived) => {
            if (!it || !it.itemId) return;
            if (nodes[it.itemId]) return;      // first writer wins: active beats archived
            nodes[it.itemId] = {
                itemId: it.itemId,
                listId,
                listName: listName || listId,
                title: it.title || 'Untitled',
                isDone: Boolean(it.isDone),
                status: typeof it.status === 'string' ? it.status : (it.isDone ? 'done' : 'open'),
                priority: it.priority || 'Medium',
                archived: Boolean(archived)
            };
            if (Array.isArray(it.relatesTo)) {
                for (const r of it.relatesTo) {
                    if (r && r.listId && r.itemId) {
                        edges.push({
                            from: { listId, itemId: it.itemId },
                            to: { listId: r.listId, itemId: r.itemId },
                            relation: r.relation || 'related'
                        });
                    }
                }
            }
            if (Array.isArray(it.subTasks)) {
                it.subTasks.forEach(s => visit(listId, listName, s, archived));
            }
        };
        const visitDir = async (dir, archived) => {
            const files = await fs.readdir(dir);
            for (const file of files) {
                if (!file.endsWith('.json')) continue;
                const data = await fs.readJson(path.join(dir, file));
                const listId = data.listId || file.replace('.json', '');
                const listName = data.listName || listId;
                const items = Array.isArray(data.items) ? data.items : [];
                items.forEach(it => visit(listId, listName, it, archived));
            }
        };
        await visitDir(SHARED_LISTS_DIR, false);
        await fs.ensureDir(ARCHIVE_DIR);
        await visitDir(ARCHIVE_DIR, true);
        // An edge is archived when either end is; both ends may not have been
        // visited yet while edges are collected, so resolve it afterwards.
        for (const e of edges) {
            const from = nodes[e.from.itemId];
            const to = nodes[e.to.itemId];
            e.archived = Boolean((from && from.archived) || (to && to.archived));
        }
        return { nodes: Object.values(nodes), edges };
    };

    app.get('/api/links', async (req, res) => {
        try {
            const { nodes, edges } = await buildLinkGraph();
            res.json({ nodes, edges });
        } catch (err) {
            res.status(500).json({ error: 'Failed to build links graph' });
        }
    });

    /* F3 — reverse/forward traceability query.
     * GET /api/trace?listId=func&itemId=xxx&direction=back|forward|both&depth=1..6
     * Breadth-first walk over the relation graph; cycles are cut by the visited set
     * so a malformed loop can never hang the request. */
    app.get('/api/trace', async (req, res) => {
        try {
            const listId = String(req.query.listId || '');
            const itemId = String(req.query.itemId || '');
            const direction = ['back', 'forward', 'both'].includes(req.query.direction) ? req.query.direction : 'back';
            const depth = Math.max(1, Math.min(6, Number(req.query.depth) || 3));
            if (!listId || !itemId) return res.status(400).json({ error: 'listId and itemId are required' });

            const { nodes, edges } = await buildLinkGraph();
            const nodeMap = new Map(nodes.map(n => [n.itemId, n]));
            const root = nodeMap.get(itemId);
            if (!root) return res.status(404).json({ error: 'item not found: ' + itemId });

            const back = direction !== 'forward';
            const forward = direction !== 'back';
            const visited = new Set([itemId]);
            const items = [];
            let frontier = [{ id: itemId, path: [] }];

            for (let d = 1; d <= depth; d++) {
                const next = [];
                for (const cur of frontier) {
                    const outgoing = forward
                        ? edges.filter(e => e.from.itemId === cur.id)
                            .map(e => ({ id: e.to.itemId, relation: e.relation, dir: 'forward' }))
                        : [];
                    const incoming = back
                        ? edges.filter(e => e.to.itemId === cur.id)
                            .map(e => ({ id: e.from.itemId, relation: e.relation, dir: 'back' }))
                        : [];
                    for (const step of outgoing.concat(incoming)) {
                        if (visited.has(step.id)) continue;
                        const n = nodeMap.get(step.id);
                        if (!n) continue;
                        visited.add(step.id);
                        const path = cur.path.concat([{
                            itemId: step.id, listId: n.listId, title: n.title,
                            relation: step.relation, direction: step.dir
                        }]);
                        items.push({
                            itemId: n.itemId, listId: n.listId, listName: n.listName,
                            title: n.title, status: n.status, isDone: n.isDone,
                            archived: Boolean(n.archived),
                            depth: d, path
                        });
                        next.push({ id: step.id, path });
                    }
                }
                if (next.length === 0) break;
                frontier = next;
            }
            res.json({ root, direction, depth, count: items.length, items });
        } catch (err) {
            res.status(500).json({ error: 'Failed to trace relations: ' + err.message });
        }
    });

    /* F3 — coverage / gap analysis.
     * GET /api/gaps                       -> every rule in categories.json → traceability
     * GET /api/gaps?rule=<value>          -> a single configured rule
     * GET /api/gaps?owner=func&referrer=test&relation=verifies   -> ad-hoc rule */
    app.get('/api/gaps', async (req, res) => {
        try {
            const cfg = await getCategories();
            const configured = Array.isArray(cfg.traceability) ? cfg.traceability : [];
            let rules;
            if (req.query.owner) {
                rules = [{
                    value: 'adhoc',
                    label: `${req.query.owner} tasks not referenced by ${req.query.referrer || 'any list'}`,
                    owner: String(req.query.owner),
                    referrer: req.query.referrer ? String(req.query.referrer) : null,
                    relation: req.query.relation ? String(req.query.relation) : null
                }];
            } else if (req.query.rule) {
                rules = configured.filter(r => r.value === req.query.rule);
                if (rules.length === 0) return res.status(400).json({ error: 'unknown rule: ' + req.query.rule });
            } else {
                rules = configured;
            }

            const { nodes, edges } = await buildLinkGraph();
            // Archived items are evidence, not backlog: their relations still cover
            // an owner, but they are never reported as a gap themselves — otherwise
            // archiving would manufacture gaps out of finished work.
            const out = rules.map(rule => {
                if (!rule.owner || rule.owner === '*') {
                    const linked = new Set();
                    edges.forEach(e => { linked.add(e.from.itemId); linked.add(e.to.itemId); });
                    const items = nodes.filter(n => !linked.has(n.itemId) && !n.archived);
                    return { value: rule.value, label: rule.label || 'Orphan Tasks', owner: '*',
                             referrer: null, relation: null, count: items.length, items };
                }
                const covered = new Set();
                edges.forEach(e => {
                    if (rule.relation && e.relation !== rule.relation) return;
                    if (rule.referrer && e.from.listId !== rule.referrer) return;
                    covered.add(e.to.itemId);
                });
                const items = nodes.filter(n => n.listId === rule.owner
                    && !covered.has(n.itemId) && !n.archived);
                return { value: rule.value, label: rule.label || rule.value, owner: rule.owner,
                         referrer: rule.referrer || null, relation: rule.relation || null,
                         count: items.length, items };
            });
            res.json({ rules: out });
        } catch (err) {
            res.status(500).json({ error: 'Failed to compute gaps: ' + err.message });
        }
    });

};

module.exports = { register };
