'use strict';

// P2-5: comment HTML is rebuilt from a whitelist. This is intentionally not a
// blacklist: unknown tags are dropped (their text is kept, escaped), blocked
// containers are removed with their content, and only known tags/attributes are
// emitted. No npm dependency; the front end has a second DOMPurify pass.

const MAX_CHARS = (() => {
    const n = Number(process.env.LITETASK_COMMENT_MAX_CHARS || 20000);
    return Number.isFinite(n) && n > 0 ? n : 20000;
})();

const ALLOWED_TAGS = new Set(['p', 'br', 'strong', 'b', 'em', 'i', 'u', 's',
    'ol', 'ul', 'li', 'a', 'span']);
const DROP_WITH_CONTENT = ['script', 'style', 'iframe', 'object', 'embed',
    'svg', 'math', 'template', 'noscript', 'form'];

const ENTITY_RE = /^&(amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);/;

const escapeText = (text) => {
    let out = '';
    for (let i = 0; i < text.length; i++) {
        const ch = text[i];
        if (ch === '<') out += '&lt;';
        else if (ch === '>') out += '&gt;';
        else if (ch === '&') {
            const tail = text.slice(i);
            const m = ENTITY_RE.exec(tail);
            if (m) {
                out += m[0];
                i += m[0].length - 1;
            } else {
                out += '&amp;';
            }
        } else out += ch;
    }
    return out;
};

const safeHref = (href) => {
    const v = String(href || '').trim();
    if (!v) return null;
    if (/^(https?:|mailto:)/i.test(v)) return v;
    if (/^[./#?]/.test(v)) return v;           // relative/same-page
    return null;
};

const attrMap = (raw) => {
    const out = {};
    const re = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*(?:=\s*("([^"]*)"|'([^']*)'|([^\s>]+)))?/g;
    let m;
    while ((m = re.exec(raw)) !== null) {
        out[m[1].toLowerCase()] = m[3] !== undefined ? m[3]
            : m[4] !== undefined ? m[4] : (m[5] !== undefined ? m[5] : '');
    }
    return out;
};

const classAllowed = (v) => /^ql-(align|size|font|indent|direction)-[a-z0-9-]+$/.test(v);

const renderTag = (name, rawAttrs, closing) => {
    if (!ALLOWED_TAGS.has(name)) return '';
    if (name === 'br') return '<br>';
    if (closing) return `</${name}>`;
    const a = attrMap(rawAttrs || '');
    const parts = [];
    if (name === 'a') {
        const href = safeHref(a.href);
        if (!href) return '<a>';
        parts.push(`href="${href.replace(/"/g, '&quot;')}"`);
        if (a.target === '_blank') {
            parts.push('target="_blank"');
            parts.push('rel="noopener noreferrer"');
        }
    } else if (name === 'p' || name === 'span') {
        if (a.class && classAllowed(a.class)) parts.push(`class="${a.class}"`);
    } else if (name === 'li') {
        if (a['data-list'] && /^(ordered|bullet|checked|unchecked)$/.test(a['data-list'])) {
            parts.push(`data-list="${a['data-list']}"`);
        }
    }
    return parts.length ? `<${name} ${parts.join(' ')}>` : `<${name}>`;
};

const stripBlockedContainers = (html) => {
    let s = html;
    for (const tag of DROP_WITH_CONTENT) {
        const re = new RegExp(`<${tag}\\b[^>]*>[\\s\\S]*?<\\/${tag}\\s*>`, 'gi');
        let prev;
        do {
            prev = s;
            s = s.replace(re, '');
        } while (s !== prev);
        s = s.replace(new RegExp(`<${tag}\\b[^>]*\\/?>`, 'gi'), '');
    }
    return s.replace(/<!--[\s\S]*?-->/g, '');
};

const sanitizeCommentHtml = (html) => {
    if (typeof html !== 'string') return { ok: true, html, violations: [] };
    if (html.length > MAX_CHARS) {
        return { ok: false, html, violations: ['COMMENT_TOO_LONG'],
            code: 'COMMENT_TOO_LONG', limit: MAX_CHARS, actual: html.length };
    }
    const violations = [];
    let s = stripBlockedContainers(html);
    let out = '';
    let i = 0;
    while (i < s.length) {
        const lt = s.indexOf('<', i);
        if (lt < 0) {
            out += escapeText(s.slice(i));
            break;
        }
        out += escapeText(s.slice(i, lt));
        const gt = s.indexOf('>', lt + 1);
        if (gt < 0) {
            out += escapeText(s.slice(lt));
            break;
        }
        const raw = s.slice(lt + 1, gt);
        if (/^!|^\?/.test(raw)) { i = gt + 1; continue; }
        const closing = raw.startsWith('/');
        const body = closing ? raw.slice(1).trim() : raw.trim();
        const nameMatch = /^([a-zA-Z][a-zA-Z0-9]*)/.exec(body);
        if (!nameMatch) {
            out += escapeText(s.slice(lt, gt + 1));
            i = gt + 1;
            continue;
        }
        const name = nameMatch[1].toLowerCase();
        const attrs = body.slice(name.length);
        if (!ALLOWED_TAGS.has(name)) {
            violations.push(`unknown-tag:${name}`);
            // Keep inner text only; the tag itself is dropped.
        } else {
            out += renderTag(name, attrs, closing);
        }
        i = gt + 1;
    }
    // A second pass is a no-op because unknown tags are gone and entities are
    // preserved; this keeps sanitize(sanitize(x)) === sanitize(x).
    return { ok: true, html: out, violations };
};

const sanitizeCommentsInPlace = (items) => {
    const violations = [];
    const walk = (arr) => {
        for (const it of (arr || [])) {
            if (!it || typeof it !== 'object') continue;
            if (typeof it.comment === 'string' && it.comment) {
                const r = sanitizeCommentHtml(it.comment);
                if (!r.ok) return { ok: false, code: r.code, limit: r.limit,
                    actual: r.actual, itemId: it.itemId || null, violations: r.violations };
                it.comment = r.html;
                violations.push(...r.violations);
            }
            const sub = walk(it.subTasks);
            if (sub && !sub.ok) return sub;
        }
        return { ok: true };
    };
    const r = walk(items);
    return r && !r.ok ? r : { ok: true, violations };
};

module.exports = {
    COMMENT_MAX_CHARS: MAX_CHARS,
    sanitizeCommentHtml,
    sanitizeCommentsInPlace,
};