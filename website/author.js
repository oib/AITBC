/**
 * Author page (MSG-17) — read-only view over /api/messages?author= and
 * /api/messages/reputation/<address>.
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

    const author = (getParam('a') || getParam('author') || '').trim();
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
            container.appendChild(el('p', 'loading-text', 'No messages by this author.'));
            return;
        }
        messages.forEach((m) => {
            const item = el('div', 'msg-item');
            const head = el('div', 'msg-item-head');

            const topicLink = el('a', 'msg-topic-chip', sanitizeChainText(m.topic || ''));
            topicLink.href = `/topic.html?t=${encodeURIComponent(m.topic || '')}`;
            head.appendChild(topicLink);

            head.appendChild(el('span', 'msg-kind', sanitizeChainText(m.kind || 'post')));

            const time = m.timestamp || m.created_at || '';
            head.appendChild(el('span', 'msg-time', time ? new Date(time).toLocaleString() : ''));

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

    async function loadReputation() {
        const container = document.getElementById('reputation-container');
        try {
            const data = await fetchJson(`${API}/api/messages/reputation/${encodeURIComponent(author)}`);
            container.textContent = '';
            const score = data.reputation !== undefined ? data.reputation : data.score;
            container.appendChild(el('p', '', `Score: ${score !== undefined ? score : 'n/a'}`));
        } catch (e) {
            container.textContent = '';
            container.appendChild(el('p', 'loading-text', `Reputation unavailable: ${e.message}`));
        }
    }

    async function loadMessages(reset) {
        if (busy) return;
        busy = true;
        const more = document.getElementById('load-more');
        more.style.display = 'none';
        try {
            const qs = new URLSearchParams({ author, limit: String(PAGE_LIMIT) });
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
        const display = document.getElementById('author-display');
        display.textContent = author;
        if (author && typeof aitbcCopyBtn === 'function') {
            display.insertAdjacentHTML('beforeend', aitbcCopyBtn(author, 'author address'));
        }
        document.title = `Author ${author.substring(0, 10)}… — AITBC`;
        document.getElementById('load-more').addEventListener('click', () => loadMessages(false));
        if (!author) {
            const c = document.getElementById('messages-container');
            c.textContent = '';
            c.appendChild(el('p', 'error-text', 'Missing author — open this page as author.html?a=<address>.'));
            document.getElementById('reputation-container').textContent = '';
            return;
        }
        loadReputation();
        loadMessages(true);
    });
})();
