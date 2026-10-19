const EXPLORER_API_URL = '/explorer-api';

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function getParam(name) {
    return new URL(window.location.href).searchParams.get(name);
}

// One read, one outcome object: ok only for status-ok AND parseable
// JSON (same shape as explorer.js/messages.js).
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

// An ok reply is only a proven-empty when it carries the array —
// an ok body without it ("{}") is a shape failure, not a zero.
const legItems = (r, key) => (r.data && Array.isArray(r.data[key])) ? r.data[key] : null;

function showError(msg, retry) {
    const errEl = document.getElementById('error');
    errEl.textContent = msg;
    if (retry) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'bridge-retry detail-retry';
        btn.textContent = 'Try again';
        btn.addEventListener('click', retry);
        errEl.appendChild(btn);
    }
    errEl.hidden = false;
}

function addrLink(addr) {
    if (!addr || addr === 'N/A') return 'N/A';
    return `<a href="/search.html?query=${encodeURIComponent(addr)}" class="clickable-value">${escapeHtml(addr)}</a>`;
}

function hashLink(hash) {
    if (!hash || hash === 'N/A') return 'N/A';
    return `<a href="/tx.html?hash=${encodeURIComponent(hash)}">${escapeHtml(hash)}</a>`;
}

function dirBadge(tx, searchedAddr) {
    if (!searchedAddr) return '';
    const s = (tx.sender || '').toLowerCase();
    const r = (tx.recipient || '').toLowerCase();
    const a = searchedAddr.toLowerCase();
    let dir = '';
    if (s === a && r === a) dir = 'self';
    else if (s === a) dir = 'out';
    else if (r === a) dir = 'in';
    if (!dir) return '';
    const labels = { out: 'OUT &rarr;', in: 'IN &larr;', self: 'SELF &orarr;' };
    return `<span class="dir-badge dir-${dir}">${labels[dir]}</span>`;
}

async function loadSearch() {
    const query = getParam('query') || getParam('search') || '';
    if (!query) {
        document.getElementById('loading').hidden = true;
        document.getElementById('error').textContent = 'Missing search query';
        document.getElementById('error').hidden = false;
        return;
    }

    // Smart redirect for block heights and hashes
    const cleanQuery = query.replace(/^#/, '');
    const isNumber = /^\d+$/.test(cleanQuery);
    const isHash = /^(0x)?[a-fA-F0-9]{64}$/.test(cleanQuery);

    if (isNumber) {
        location.href = `/block.html?height=${cleanQuery}`;
        return;
    }
    if (isHash) {
        location.href = `/tx.html?hash=${encodeURIComponent(cleanQuery)}`;
        return;
    }

    document.title = `Search: ${query}`;
    document.getElementById('query-display').textContent = query;

    try {
        const [txs, blocks, msgs] = await Promise.all([
            readJson(`${EXPLORER_API_URL}/api/transactions/search?address=${encodeURIComponent(query)}&limit=50`),
            readJson(`${EXPLORER_API_URL}/api/blocks/by-address/${encodeURIComponent(query)}?limit=50`),
            // MSG-17: body-text search over the messaging index —
            // a proxied route, so a non-ok or shapeless leg degrades
            // the answer to inconclusive, not "nothing found".
            readJson(`${EXPLORER_API_URL}/api/messages/search?q=${encodeURIComponent(query)}&limit=50`),
        ]);
        // A failed reply is not "no results" — only a 404 or a
        // proven empty list is.
        const hardFail = [txs, blocks].find(r => !r.ok && r.status !== 404);
        if (hardFail) {
            throw new Error(`Search could not be completed (${hardFail.err || `HTTP ${hardFail.status}`}). This is not a "not found".`);
        }
        const txArr = txs.ok ? legItems(txs, 'transactions') : null;
        const blkArr = blocks.ok ? legItems(blocks, 'blocks') : null;
        const msgArr = msgs.ok ? legItems(msgs, 'messages') : null;
        // A hard leg answered ok but without its list — inconclusive,
        // not "nothing found".
        if ((txs.ok && txArr === null) || (blocks.ok && blkArr === null)) {
            throw new Error('Search could not be completed (reply was not the expected shape). This is not a "not found".');
        }
        // The messages leg is proxied: any non-ok (incl. 404 — a
        // route miss cannot prove "no match") or shapeless ok
        // degrades it.
        const msgLegFailed = !msgs.ok || (msgs.ok && msgArr === null);
        const msgLegReason = msgs.ok
            ? 'reply was not the expected shape'
            : (msgs.err || `HTTP ${msgs.status}`);
        const txList = txArr || [];
        const blockList = blkArr || [];
        const msgList = msgArr || [];

        if (txList.length === 0 && blockList.length === 0 && msgList.length === 0) {
            document.getElementById('loading').hidden = true;
            if (msgLegFailed) {
                showError(`Search could not be completed (messages leg: ${msgLegReason}). This is not a "not found".`, loadSearch);
            } else {
                showError('No transactions, blocks or messages found for this query.');
            }
            return;
        }

        if (blockList.length > 0) {
            document.getElementById('blocks-section').hidden = false;
            document.getElementById('blocks-list').innerHTML = blockList.map(b => `
                <div class="endpoint table-card fade-in block-item" tabindex="0" role="link" data-href="/block.html?height=${encodeURIComponent(b.height)}">
                    <div class="table-wrap"><table class="block-list-table" aria-label="Result details">
                        <tr><th scope="row">Height</th><td><span class="badge badge-primary">${escapeHtml(aitbcFmt.type('BLOCK'))}</span> #${escapeHtml(b.height)}</td></tr>
                        <tr><th scope="row">Hash</th><td>${escapeHtml(b.hash || 'N/A')} ${aitbcCopyBtn(b.hash || '', 'block hash')}</td></tr>
                        <tr><th scope="row">Proposer</th><td>${addrLink(b.proposer)}</td></tr>
                        <tr><th scope="row">Transactions</th><td>${escapeHtml(b.txCount || 0)}</td></tr>
                        <tr><th scope="row">Timestamp</th><td>${escapeHtml(b.timestamp ? aitbcFmt.date(b.timestamp) : 'N/A')}</td></tr>
                    </table></div>
                </div>
            `).join('');
        }

        if (txList.length > 0) {
            document.getElementById('txs-section').hidden = false;
            document.getElementById('txs-list').innerHTML = txList.map(tx => {
                const dBadge = dirBadge(tx, query);
                return `
                <div class="endpoint table-card fade-in block-item" tabindex="0" role="link" data-href="/tx.html?hash=${encodeURIComponent(tx.tx_hash)}">
                    <div class="table-wrap"><table class="block-list-table" aria-label="Result details">
                        <tr><th scope="row">Type</th><td><span class="badge badge-primary">${escapeHtml(aitbcFmt.type(tx.type || 'TX'))}</span> ${dBadge}</td></tr>
                        <tr><th scope="row">Hash</th><td>${escapeHtml(tx.tx_hash || 'N/A')} ${aitbcCopyBtn(tx.tx_hash || '', 'transaction hash')}</td></tr>
                        <tr><th scope="row">From</th><td>${addrLink(tx.sender)}</td></tr>
                        <tr><th scope="row">To</th><td>${addrLink(tx.recipient)}</td></tr>
                        <tr><th scope="row">Block</th><td><a href="/block.html?height=${encodeURIComponent(tx.block_height)}">${escapeHtml(tx.block_height)}</a></td></tr>
                        <tr><th scope="row">Status</th><td>${escapeHtml(tx.status || 'N/A')}</td></tr>
                        <tr><th scope="row">Time</th><td>${escapeHtml(tx.created_at ? aitbcFmt.date(tx.created_at) : 'N/A')}</td></tr>
                    </table></div>
                </div>
                `;
            }).join('');
        }

        if (msgList.length > 0) {
            // MSG-17: chain-sourced text renders through DOM APIs only
            // (textContent/attributes) — the same rule as messages.js.
            const NEUTRAL_RE = /[\u0080-\u009F\p{Cf}\u061C\u180E\u{E0000}-\u{E007F}\u{E0100}-\u{E01EF}\u3164\u115F\u1160\uFFA0\u2800]/gu;
            const clean = (s) => String(s).replace(NEUTRAL_RE, (ch) => `[U+${ch.codePointAt(0).toString(16).toUpperCase().padStart(4, '0')}]`);
            const make = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
            const list = document.getElementById('messages-list');
            list.textContent = '';
            msgList.forEach((m) => {
                const item = make('div', 'msg-item');
                const head = make('div', 'msg-item-head');
                const topicLink = make('a', 'msg-topic-chip', clean(m.topic || ''));
                topicLink.href = `/topic.html?t=${encodeURIComponent(m.topic || '')}`;
                head.appendChild(topicLink);
                head.appendChild(make('span', 'msg-kind', clean(m.kind || 'post')));
                const author = m.author || m.sender || '';
                const authorLink = make('a', 'clickable-value msg-author', clean(author));
                authorLink.href = `/author.html?a=${encodeURIComponent(author)}`;
                head.appendChild(authorLink);
                const time = m.timestamp || m.created_at || '';
                head.appendChild(make('span', 'msg-time', time ? aitbcFmt.date(time) : ''));
                item.appendChild(head);
                item.appendChild(make('div', 'msg-body', clean(m.body || '')));
                const hashLine = make('div', 'msg-hash');
                const txLink = make('a', 'clickable-value', `${(m.tx_hash || '').substring(0, 18)}…`);
                txLink.href = `/tx.html?hash=${encodeURIComponent(m.tx_hash || '')}`;
                hashLine.appendChild(txLink);
                item.appendChild(hashLine);
                list.appendChild(item);
            });
            document.getElementById('messages-section').hidden = false;
        }

        document.getElementById('loading').hidden = true;
        document.getElementById('content').hidden = false;
    } catch (err) {
        document.getElementById('loading').hidden = true;
        showError(err.message || 'Search failed', loadSearch);
    }
}

document.addEventListener('DOMContentLoaded', loadSearch);
