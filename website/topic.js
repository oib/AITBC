/**
 * Topic page (MSG-17) — read-only view over /api/messages?topic= and
 * /api/messages/topics/<slug>/moderation.
 *
 * Same rendering rules as messages.js: chain-sourced strings reach the DOM
 * only via textContent/attributes after sanitizeChainText() makes format and
 * invisible characters visible as [U+XXXX] placeholders — never an HTML sink.
 */
(function () {
    'use strict';

    const API = (window.AITBC_CONFIG && window.AITBC_CONFIG.explorerApiUrl) || '/explorer-api';
    const PAGE_LIMIT = 50;

    // Same pinned ranges as messages.js (parity: aitbc/textsafety.py,
    // tests/unit/test_textsafety.py).
    const NEUTRAL_RE = /[\u0080-\u009F\p{Cf}\u061C\u180E\u{E0000}-\u{E007F}\u{E0100}-\u{E01EF}\u3164\u115F\u1160\uFFA0\u2800]/gu;

    function sanitizeChainText(s) {
        return String(s).replace(NEUTRAL_RE, (ch) => `[U+${ch.codePointAt(0).toString(16).toUpperCase().padStart(4, '0')}]`);
    }

    function el(tag, className, text) {
        const e = document.createElement(tag);
        if (className) e.className = className;
        if (text !== undefined) e.textContent = text;
        return e;
    }

    function announce(msg) {
        const a = document.getElementById('sr-announcer');
        if (a) a.textContent = msg;
    }

    function getParam(name) {
        return new URL(window.location.href).searchParams.get(name);
    }

    const topic = (getParam('t') || getParam('topic') || '').trim();
    let nextCursor = null;
    let busy = false;

    async function fetchJson(url) {
        const resp = await fetch(url);
        if (!resp.ok) {
            let detail = `HTTP ${resp.status}`;
            try {
                const j = await resp.json();
                if (j && j.detail) detail = j.detail;
            } catch (e) { /* keep the status */ }
            throw new Error(detail);
        }
        return resp.json();
    }

    function renderMessages(messages, append) {
        const container = document.getElementById('messages-container');
        if (!append) container.textContent = '';
        if (!messages.length && !append) {
            container.appendChild(el('p', 'loading-text', 'No messages in this topic.'));
            return;
        }
        messages.forEach((m) => {
            const item = el('div', 'msg-item');
            const head = el('div', 'msg-item-head');

            head.appendChild(el('span', 'msg-kind', sanitizeChainText(m.kind || 'post')));

            const author = m.author || m.sender || '';
            const authorLink = el('a', 'clickable-value msg-author', sanitizeChainText(author));
            authorLink.href = `/author.html?a=${encodeURIComponent(author)}`;
            head.appendChild(authorLink);
            if (author && typeof aitbcCopyBtn === 'function') {
                head.insertAdjacentHTML('beforeend', aitbcCopyBtn(author, 'author address'));
            }

            const time = m.timestamp || m.created_at || '';
            head.appendChild(el('span', 'msg-time', time ? aitbcFmt.date(time) : ''));

            item.appendChild(head);
            item.appendChild(el('div', 'msg-body', sanitizeChainText(m.body || '')));

            const hashLine = el('div', 'msg-hash');
            const txLink = el('a', 'clickable-value', `${(m.tx_hash || '').substring(0, 18)}…`);
            txLink.href = `/tx.html?hash=${encodeURIComponent(m.tx_hash || '')}`;
            txLink.title = 'Open transaction';
            hashLine.appendChild(txLink);
            if (m.tx_hash && typeof aitbcCopyBtn === 'function') {
                hashLine.insertAdjacentHTML('beforeend', aitbcCopyBtn(m.tx_hash, 'transaction hash'));
            }
            if (m.parent) {
                const parent = el('span', 'msg-parent', `reply to ${String(m.parent).substring(0, 18)}…`);
                parent.title = sanitizeChainText(m.parent);
                hashLine.appendChild(parent);
            }
            item.appendChild(hashLine);
            container.appendChild(item);
        });
    }

    async function loadTopic() {
        const container = document.getElementById('topic-container');
        container.textContent = '';
        try {
            const mod = await fetchJson(`${API}/api/messages/topics/${encodeURIComponent(topic)}/moderation`);
            const mods = (mod.moderators || []).map(sanitizeChainText);
            const stats = el('p', '', `Moderators: ${mods.length ? mods.join(', ') : 'none'}`);
            container.appendChild(stats);
            if (mod.authority_unresolved) {
                container.appendChild(el('p', 'loading-text', 'Moderator set is still resolving.'));
            }
        } catch (e) {
            container.textContent = '';
            container.appendChild(el('p', 'loading-text', `Topic details unavailable: ${e.message}`));
        }
    }

    async function loadMessages(reset) {
        if (busy) return;
        busy = true;
        const more = document.getElementById('load-more');
        more.style.display = 'none';
        try {
            const qs = new URLSearchParams({ topic, limit: String(PAGE_LIMIT) });
            if (!reset && nextCursor) qs.set('cursor', nextCursor);
            const data = await fetchJson(`${API}/api/messages?${qs}`);
            renderMessages(data.messages || [], !reset);
            nextCursor = data.next_cursor || null;
            more.style.display = nextCursor ? 'inline-block' : 'none';
            announce(`${data.count || 0} messages loaded`);
        } catch (e) {
            const c = document.getElementById('messages-container');
            if (!c.children.length) {
                c.textContent = '';
                c.appendChild(el('p', 'error-text', `Messages unavailable: ${e.message}`));
            } else {
                announce(`Messages failed to load: ${e.message}`);
            }
            nextCursor = null;
        } finally {
            busy = false;
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('topic-display').textContent = sanitizeChainText(topic || '(missing)');
        if (topic) {
            document.title = `Topic ${sanitizeChainText(topic)} — AITBC`;
        }
        document.getElementById('load-more').addEventListener('click', () => loadMessages(false));
        if (!topic) {
            const c = document.getElementById('messages-container');
            c.textContent = '';
            c.appendChild(el('p', 'error-text', 'Missing topic — open this page as topic.html?t=<name>.'));
            document.getElementById('topic-container').textContent = '';
            return;
        }
        loadTopic();
        loadMessages(true);
    });
})();
