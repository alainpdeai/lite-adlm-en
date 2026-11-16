'use strict';

// Stable error code domain (P0 security hardening). Rejections share a unified shape:
//   { error: <readable message>, code: <STABLE_CODE>, ...extra }
// Responses never leak stack traces, absolute paths, file contents, or user lists.

const CODES = Object.freeze({
    INVALID_LIST_ID: 'INVALID_LIST_ID',
    INVALID_STAMP: 'INVALID_STAMP',
    INVALID_PATH: 'INVALID_PATH',
    NOT_A_DIRECTORY: 'NOT_A_DIRECTORY',
    AUTH_REQUIRED: 'AUTH_REQUIRED',
    SESSION_INVALID: 'SESSION_INVALID',
    UNKNOWN_ACTOR: 'UNKNOWN_ACTOR',
    ADMIN_REQUIRED: 'ADMIN_REQUIRED',
    NON_LOOPBACK_SOURCE: 'NON_LOOPBACK_SOURCE',
    OPEN_ROOT_NOT_CONFIGURED: 'OPEN_ROOT_NOT_CONFIGURED',
    PATH_OUTSIDE_ALLOWED_ROOT: 'PATH_OUTSIDE_ALLOWED_ROOT',
    PATH_NOT_READABLE: 'PATH_NOT_READABLE',
    LIST_NOT_FOUND: 'LIST_NOT_FOUND',
    PATH_NOT_FOUND: 'PATH_NOT_FOUND',
    INVALID_CREDENTIALS: 'INVALID_CREDENTIALS',
    TOO_MANY_REQUESTS: 'TOO_MANY_REQUESTS',
    LAUNCHER_UNAVAILABLE: 'LAUNCHER_UNAVAILABLE',
    ARCHIVE_TXN_FAILED: 'ARCHIVE_TXN_FAILED',
    ARCHIVE_TXN_MANUAL_RECOVERY: 'ARCHIVE_TXN_MANUAL_RECOVERY',
    ARCHIVE_TXN_PENDING: 'ARCHIVE_TXN_PENDING',
    INTERNAL: 'INTERNAL',
});

const DEFAULT_MESSAGES = Object.freeze({
    INVALID_LIST_ID: 'Invalid list identifier',
    INVALID_STAMP: 'Invalid snapshot timestamp',
    INVALID_PATH: 'Path must be an absolute path',
    NOT_A_DIRECTORY: 'Target is not a directory',
    AUTH_REQUIRED: 'Authentication required',
    SESSION_INVALID: 'Invalid session',
    UNKNOWN_ACTOR: 'Untrusted identity',
    ADMIN_REQUIRED: 'Administrator access required',
    NON_LOOPBACK_SOURCE: 'Loopback access only',
    OPEN_ROOT_NOT_CONFIGURED: 'Allowed root not configured, feature disabled',
    PATH_OUTSIDE_ALLOWED_ROOT: 'Path outside allowed root',
    PATH_NOT_READABLE: 'Path is not readable',
    LIST_NOT_FOUND: 'List not found',
    PATH_NOT_FOUND: 'Path does not exist',
    INVALID_CREDENTIALS: 'Invalid credentials',
    TOO_MANY_REQUESTS: 'Too many requests',
    LAUNCHER_UNAVAILABLE: 'System file manager unavailable',
    ARCHIVE_TXN_FAILED: 'Archive transaction failed, rolled back to prior state',
    ARCHIVE_TXN_MANUAL_RECOVERY: 'Archive transaction failed and rollback incomplete, manual recovery required',
    ARCHIVE_TXN_PENDING: 'List has an unfinished transaction, manual recovery required',
    INTERNAL: 'Internal error',
});

const isCode = (code) => Object.prototype.hasOwnProperty.call(CODES, code);

const errorBody = (code, message, extra) => {
    const key = isCode(code) ? code : CODES.INTERNAL;
    const body = {
        error: (typeof message === 'string' && message.length > 0)
            ? message
            : DEFAULT_MESSAGES[key],
        code: key,
    };
    if (extra && typeof extra === 'object' && !Array.isArray(extra)) {
        for (const [k, v] of Object.entries(extra)) {
            if (k === 'error' || k === 'code') continue;
            body[k] = v;
        }
    }
    return body;
};

const sendError = (res, status, code, message, extra) => {
    return res.status(status).json(errorBody(code, message, extra));
};

module.exports = {
    CODES,
    DEFAULT_MESSAGES,
    errorBody,
    sendError,
};
