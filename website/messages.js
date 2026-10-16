/**
 * On-chain forum messages (MSG-4) — read-only view over /api/messages/*.
 *
 * Rendering safety is the hard requirement: every chain-sourced string goes
 * through textContent or an attribute only — never an HTML-string sink — after
 * sanitizeChainText() replaces bidi-override/isolate controls and zero-width
 * characters with a visible [U+XXXX] placeholder (the byte content stays
 * inspectable instead of being silently dropped).
 */
(function () {
    'use strict';

    const API = (window.AITBC_CONFIG && window.AITBC_CONFIG.explorerApiUrl) || '/explorer-api';
    const PAGE_LIMIT = 50;

    // MSG-4b (folds MSG-FIX-2): every Unicode format character (Cf) — bidi
    // overrides/isolates, zero-widths, soft hyphen, word joiner, invisible
    // operators — plus the C1 controls (U+0080-U+009F, category Cc), U+061C,
    // U+180E and the astral tag block U+E0000-U+E007F, which can carry hidden
    // text to agents reading bodies.
    // Mirrors aitbc/textsafety.py; parity pinned by tests/unit/test_textsafety.py.
    const NEUTRAL_RE = /[\u0080-\u009F\p{Cf}\u061C\u180E\u{E0000}-\u{E007F}]/gu;

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

    let activeTopic = getParam('topic') || '';
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

    function renderTopics(topics) {
        const container = document.getElementById('topics-container');
        container.textContent = '';
        const list = el('div', 'filter-buttons');
        const all = el('button', 'filter-btn' + (activeTopic ? '' : ' active'), 'all');
        all.type = 'button';
        all.addEventListener('click', () => selectTopic(''));
        list.appendChild(all);
        (topics || []).forEach((t) => {
            const slug = sanitizeChainText(t.topic || '');
            const b = el('button', 'filter-btn' + (t.topic === activeTopic ? ' active' : ''), `${slug} (${t.message_count})`);
            b.type = 'button';
            b.addEventListener('click', () => selectTopic(t.topic));
            list.appendChild(b);
        });
        container.appendChild(list);
    }

    function selectTopic(topic) {
        activeTopic = topic || '';
        nextCursor = null;
        const heading = document.getElementById('messages-heading');
        heading.textContent = activeTopic ? `Topic: ${sanitizeChainText(activeTopic)}` : 'Latest messages';
        document.getElementById('messages-container').textContent = '';
        loadTopics();
        loadMessages(true);
    }

    function renderMessages(messages, append) {
        const container = document.getElementById('messages-container');
        if (!append) container.textContent = '';
        if (!messages.length && !append) {
            container.appendChild(el('p', 'loading-text', 'No messages yet.'));
            return;
        }
        messages.forEach((m) => {
            const item = el('div', 'msg-item');
            const head = el('div', 'msg-item-head');

            const topicLink = el('a', 'msg-topic-chip', sanitizeChainText(m.topic || ''));
            topicLink.href = `/messages.html?topic=${encodeURIComponent(m.topic || '')}`;
            head.appendChild(topicLink);

            head.appendChild(el('span', 'msg-kind', sanitizeChainText(m.kind || 'post')));

            const author = m.author || m.sender || '';
            const authorLink = el('a', 'clickable-value msg-author', sanitizeChainText(author));
            authorLink.href = `/search.html?query=${encodeURIComponent(author)}`;
            head.appendChild(authorLink);
            if (author && typeof aitbcCopyBtn === 'function') {
                head.insertAdjacentHTML('beforeend', aitbcCopyBtn(author, 'author address'));
            }

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

    async function loadTopics() {
        try {
            const data = await fetchJson(`${API}/api/messages/topics?limit=${PAGE_LIMIT}`);
            renderTopics(data.topics || []);
        } catch (e) {
            const c = document.getElementById('topics-container');
            c.textContent = '';
            c.appendChild(el('p', 'error-text', `Topics unavailable: ${e.message}`));
        }
    }

    async function loadMessages(reset) {
        if (busy) return;
        busy = true;
        const more = document.getElementById('load-more');
        more.style.display = 'none';
        try {
            const qs = new URLSearchParams({ limit: String(PAGE_LIMIT) });
            if (activeTopic) qs.set('topic', activeTopic);
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
        if (activeTopic) {
            document.getElementById('messages-heading').textContent = `Topic: ${sanitizeChainText(activeTopic)}`;
        }
        document.getElementById('load-more').addEventListener('click', () => loadMessages(false));
        loadTopics();
        loadMessages(true);
    });
})();
