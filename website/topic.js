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
    let msgsLastGoodAt = 0;

    function ageAgo(ts) {
        const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
        if (s < 5) return 'just now';
        if (s < 90) return `${s} s ago`;
        return `${Math.round(s / 60)} min ago`;
    }

    // One read, one outcome object: ok only for status-ok AND parseable JSON.
    async function readJson(url) {
        try {
            const resp = await fetch(url);
            if (!resp.ok) return { ok: false, status: resp.status };
            try {
                return { ok: true, status: resp.status, data: await resp.json() };
            } catch (e) {
                return { ok: false, status: resp.status, err: 'reply was not readable' };
            }
        } catch (e) {
            return { ok: false, status: 0, err: 'network request failed' };
        }
    }

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

    // The single read-state note for the message list — one element, never
    // one line per poll.
    function renderReadState(container, state, detail, retry) {
        const prev = [...container.children].find(c => c.classList && c.classList.contains('msg-read-note'));
        if (prev) prev.remove();
        if (state === 'live') return;
        const note = el('div', state === 'failed' ? 'msg-state msg-read-note' : 'msg-state-note msg-read-note');
        note.setAttribute('role', state === 'failed' ? 'alert' : 'status');
        if (state === 'failed') {
            note.appendChild(el('p', 'msg-state-title', detail));
        } else {
            note.appendChild(el('span', '', detail));
        }
        const btn = el('button', 'bridge-retry', 'Try again');
        btn.type = 'button';
        btn.addEventListener('click', retry);
        note.appendChild(btn);
        container.prepend(note);
    }

    function renderMessages(messages, append) {
        const container = document.getElementById('messages-container');
        if (!append) container.textContent = '';
        if (!messages.length && !append) {
            container.appendChild(el('p', 'msg-empty', sanitizeChainText(`No messages in ${topic} yet.`)));
            return;
        }
        messages.forEach((m) => {
            const item = el('div', 'msg-item');
            const head = el('div', 'msg-item-head');

            head.appendChild(el('span', 'msg-kind', sanitizeChainText(m.kind || 'post')));

            // Moderation badges in words — colour is backup only.
            if (m.pinned) head.appendChild(el('span', 'msg-badge msg-badge-pinned', 'PINNED'));
            if (m.after_lock) head.appendChild(el('span', 'msg-badge msg-badge-locked', 'POSTED AFTER LOCK'));
            if (m.hidden) head.appendChild(el('span', 'msg-badge msg-badge-hidden', 'HIDDEN BY MODERATOR'));

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
            if (m.hidden) {
                // A hidden message is not deleted: author, fee and hash stay,
                // the body collapses behind an explicit Show anyway.
                const body = el('div', 'msg-body msg-body-collapsed', sanitizeChainText(m.body || ''));
                const note = el('div', 'msg-hidden-note');
                note.appendChild(el('span', '', 'Body hidden by a moderator.'));
                const fee = Number(m.fee);
                if (Number.isFinite(fee)) {
                    note.appendChild(el('span', 'msg-fee', ` fee ${aitbcFmt.num(fee / 36000000, 4)} AIT`));
                }
                const show = el('button', 'msg-show-anyway', 'Show anyway');
                show.type = 'button';
                show.addEventListener('click', () => {
                    body.classList.remove('msg-body-collapsed');
                    show.remove();
                });
                note.appendChild(show);
                item.appendChild(note);
                item.appendChild(body);
            } else {
                item.appendChild(el('div', 'msg-body', sanitizeChainText(m.body || '')));
            }

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
            const btn = el('button', 'bridge-retry', 'Try again');
            btn.type = 'button';
            btn.addEventListener('click', loadTopic);
            container.appendChild(btn);
        }
    }

    async function loadMessages(reset) {
        if (busy) return;
        busy = true;
        const more = document.getElementById('load-more');
        more.style.display = 'none';
        const container = document.getElementById('messages-container');
        try {
            const qs = new URLSearchParams({ topic, limit: String(PAGE_LIMIT) });
            if (!reset && nextCursor) qs.set('cursor', nextCursor);
            const r = await readJson(`${API}/api/messages?${qs}`);
            const data = r.data;
            if (!r.ok || !data || !Array.isArray(data.messages)) {
                const reason = r.ok ? 'reply was not the expected shape' : (r.err || `HTTP ${r.status}`);
                if (msgsLastGoodAt) {
                    // old rows stay; ONE stale note names the last good read
                    renderReadState(container, 'stale', `Stale, last read ${ageAgo(msgsLastGoodAt)} — could not refresh (${reason})`, () => loadMessages(true));
                } else {
                    container.textContent = '';
                    renderReadState(container, 'failed', `Messages could not be loaded. (${reason})`, () => loadMessages(true));
                }
                announce(`Messages failed to load: ${reason}`);
                return;
            }
            msgsLastGoodAt = Date.now();
            renderMessages(data.messages, !reset);
            renderReadState(container, 'live');
            nextCursor = data.next_cursor || null;
            more.style.display = nextCursor ? 'inline-block' : 'none';
            announce(`${data.count || 0} messages loaded`);
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
