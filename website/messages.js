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
    // MSG-FIX-3 (operator pick: option b): the supplementary variation
    // selectors U+E0100-U+E01EF (category Mn, hidden-text capable) and the
    // blank-rendering fillers U+3164, U+115F, U+1160, U+FFA0, U+2800. The BMP
    // variation selectors U+FE00-U+FE0F stay untouched — emoji need them.
    // Mirrors aitbc/textsafety.py; parity pinned by tests/unit/test_textsafety.py.
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

    let activeTopic = getParam('topic') || '';
    let nextCursor = null;
    let busy = false;

    // ── Shared read/state helpers ────────────────────────────────────
    // Topics and messages are separate reads and fail separately. Each
    // keeps its last good render; a failed or unreadable reply lands in
    // stale (old rows + last-good time) or failed (reason + Try again) —
    // never in empty, loading or "nothing exists".
    let topicsLastGoodAt = 0;
    let msgsLastGoodAt = 0;
    let topicsStale = false;
    let msgsStale = false;
    let topicsFailReason = '';
    let msgsFailReason = '';

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

    // The single read-state note for a container — removed and rebuilt on
    // every render so a stale/failed state never appends one line per read.
    function renderReadState(container, state, detail, retry) {
        const prev = [...container.children].find(c => c.classList && c.classList.contains('msg-read-note'));
        if (prev) prev.remove();
        if (state === 'live') return;
        const note = el('div', state === 'failed' ? 'msg-state msg-read-note' : 'msg-state-note msg-read-note');
        note.setAttribute('role', state === 'failed' ? 'alert' : 'status');
        if (state === 'failed') {
            note.appendChild(el('p', 'msg-state-title', detail));
            const btn = el('button', 'bridge-retry', 'Try again');
            btn.type = 'button';
            btn.addEventListener('click', retry);
            note.appendChild(btn);
        } else {
            note.appendChild(el('span', '', detail));
            if (retry) {
                const btn = el('button', 'bridge-retry', 'Try again');
                btn.type = 'button';
                btn.addEventListener('click', retry);
                note.appendChild(btn);
            }
        }
        container.prepend(note);
    }

    // One markup for both layouts: a .topic-item carries name + meta
    // (message count, moderation badges). CSS lays the same list out as a
    // side rail on wide screens and a horizontally scrolling chip row
    // under 640 px — never a sideways-scrolling page body.
    function renderTopics(topics) {
        const container = document.getElementById('topics-container');
        container.textContent = '';
        const list = el('div', 'msg-topic-list');
        const all = el('button', 'topic-item filter-btn' + (activeTopic ? '' : ' active'));
        all.type = 'button';
        const allName = el('span', 'topic-item-name', 'all');
        all.appendChild(allName);
        all.addEventListener('click', () => selectTopic(''));
        list.appendChild(all);
        (topics || []).forEach((t) => {
            const slug = sanitizeChainText(t.topic || '');
            const b = el('button', 'topic-item filter-btn' + (t.topic === activeTopic ? ' active' : ''));
            b.type = 'button';
            b.appendChild(el('span', 'topic-item-name', slug));
            const meta = el('span', 'topic-item-meta');
            meta.appendChild(el('span', 'topic-item-count', `${t.message_count} messages`));
            if (t.locked) meta.appendChild(el('span', 'msg-badge msg-badge-locked', 'LOCKED'));
            if (t.pinned_count) meta.appendChild(el('span', 'msg-badge msg-badge-pinned', `PINNED ${t.pinned_count}`));
            if (t.hidden_count) meta.appendChild(el('span', 'msg-badge msg-badge-hidden', `HIDDEN ${t.hidden_count}`));
            b.appendChild(meta);
            b.addEventListener('click', () => selectTopic(t.topic));
            list.appendChild(b);
        });
        container.appendChild(list);
    }

    function selectTopic(topic) {
        activeTopic = topic || '';
        nextCursor = null;
        msgsStale = false;
        const heading = document.getElementById('messages-heading');
        heading.textContent = activeTopic ? `Topic: ${sanitizeChainText(activeTopic)}` : 'Latest messages';
        const mc = document.getElementById('messages-container');
        mc.textContent = '';
        msgsLastGoodAt = 0;
        loadTopics();
        loadMessages(true);
    }

    function renderMessages(messages, append) {
        const container = document.getElementById('messages-container');
        if (!append) container.textContent = '';
        if (!messages.length && !append) {
            // A proven ok empty list is the only path to this line — a
            // failed read never lands here.
            const text = activeTopic
                ? `No messages in ${activeTopic} yet.`
                : 'No messages yet.';
            container.appendChild(el('p', 'msg-empty', sanitizeChainText(text)));
            return;
        }
        messages.forEach((m) => {
            const item = el('div', 'msg-item');
            const head = el('div', 'msg-item-head');

            const topicLink = el('a', 'msg-topic-chip', sanitizeChainText(m.topic || ''));
            topicLink.href = `/topic.html?t=${encodeURIComponent(m.topic || '')}`;
            head.appendChild(topicLink);

            head.appendChild(el('span', 'msg-kind', sanitizeChainText(m.kind || 'post')));

            // Moderation badges in words — colour is backup only.
            if (m.pinned) head.appendChild(el('span', 'msg-badge msg-badge-pinned', 'PINNED'));
            if (m.after_lock) head.appendChild(el('span', 'msg-badge msg-badge-locked', 'POSTED AFTER LOCK'));
            if (m.hidden) head.appendChild(el('span', 'msg-badge msg-badge-hidden', 'HIDDEN BY MODERATOR'));

            const author = m.author || m.sender || '';
            // Same shortened form the other pages use — full value stays
            // discoverable via title/aria-label and the copy button.
            const authorShort = author.length > 14 ? `${author.slice(0, 8)}…${author.slice(-6)}` : author;
            const authorLink = el('a', 'clickable-value msg-author', sanitizeChainText(authorShort));
            authorLink.href = `/author.html?a=${encodeURIComponent(author)}`;
            if (authorShort !== author) {
                authorLink.title = author;
                authorLink.setAttribute('aria-label', author);
            }
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

    async function loadTopics() {
        const container = document.getElementById('topics-container');
        const r = await readJson(`${API}/api/messages/topics?limit=${PAGE_LIMIT}`);
        const data = r.data;
        if (!r.ok || !data || !Array.isArray(data.topics)) {
            const reason = r.ok ? 'reply was not the expected shape' : (r.err || `HTTP ${r.status}`);
            topicsFailReason = reason;
            if (topicsLastGoodAt) {
                // keep the last good chips; the note names the reason + time
                topicsStale = true;
                renderReadState(container, 'stale', `Could not refresh topics (${reason}) — last read ${ageAgo(topicsLastGoodAt)}`, loadTopics);
            } else {
                container.textContent = '';
                renderReadState(container, 'failed', `Topics could not be loaded. (${reason})`, loadTopics);
            }
            return;
        }
        topicsLastGoodAt = Date.now();
        topicsStale = false;
        renderTopics(data.topics);
        renderReadState(container, 'live');
    }

    async function loadMessages(reset) {
        if (busy) return;
        busy = true;
        const more = document.getElementById('load-more');
        more.style.display = 'none';
        const container = document.getElementById('messages-container');
        try {
            const qs = new URLSearchParams({ limit: String(PAGE_LIMIT) });
            if (activeTopic) qs.set('topic', activeTopic);
            if (!reset && nextCursor) qs.set('cursor', nextCursor);
            const r = await readJson(`${API}/api/messages?${qs}`);
            const data = r.data;
            if (!r.ok || !data || !Array.isArray(data.messages)) {
                const reason = r.ok ? 'reply was not the expected shape' : (r.err || `HTTP ${r.status}`);
                msgsFailReason = reason;
                if (msgsLastGoodAt) {
                    // old rows stay; ONE stale note names the last good read
                    msgsStale = true;
                    renderReadState(container, 'stale', `Stale, last read ${ageAgo(msgsLastGoodAt)} — could not refresh (${reason})`, () => loadMessages(true));
                } else {
                    container.textContent = '';
                    renderReadState(container, 'failed', `Messages could not be loaded. (${reason})`, () => loadMessages(true));
                }
                announce(`Messages failed to load: ${reason}`);
                return;
            }
            msgsLastGoodAt = Date.now();
            msgsStale = false;
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
        if (activeTopic) {
            document.getElementById('messages-heading').textContent = `Topic: ${sanitizeChainText(activeTopic)}`;
        }
        document.getElementById('load-more').addEventListener('click', () => loadMessages(false));
        loadTopics();
        loadMessages(true);
    });
})();
