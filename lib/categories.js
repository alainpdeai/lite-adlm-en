'use strict';

const fs = require('fs-extra');

// Categories / task-type configuration loader (route ①, Round 6).
// categories.json is the single source of truth for the three-major-category
// list definitions, the status flow (F1) and the auto-archive policy (A1).
// This is a config read, kept separate from lib/config.js (which is
// dependency-free env/path constants) so the loader can perform I/O.
const { CATEGORIES_FILE } = require('./config');

const getCategories = async () => {
    try {
        if (await fs.pathExists(CATEGORIES_FILE)) {
            return await fs.readJson(CATEGORIES_FILE);
        }
    } catch (err) {
        console.error("Error reading categories.json:", err);
    }
    return { categories: [], relations: [] };
};

module.exports = { getCategories };
