/* ETH-11 phase 1: read-only order book + trade tape (Sepolia testnet).
 *
 * Fetch-only: GETs two nginx-gated endpoints and renders the book. No POST,
 * no wallet connect, no signing. Every server string is rendered via
 * textContent / DOM nodes — never innerHTML — because address and label
 * fields are database-provided and untrusted.
 */
(function () {
    'use strict';

    // ── tuning constants ────────────────────────────────────────────
    const LIVE_WINDOW_DAYS = 7;            // rows older than this are "inactive test data"
    const REFRESH_MS = 15000;              // poll while the tab is visible
    const MAX_BACKOFF_MS = 120000;         // error backoff ceiling
    const TAPE_MAX = 20;                   // last N trades
    const ORDERBOOK_URL = '/exchange-api/orderbook';
    const TRADES_URL = '/exchange-api/trades';

    const LIVE_MS = LIVE_WINDOW_DAYS * 86400 * 1000;
    let timer = null;
    let backoffMs = REFRESH_MS;

    // ── small helpers (all output is text, never markup) ────────────
    function el(tag, cls, text) {
        const n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text !== undefined) n.textContent = text;
        return n;
    }

    function parseTime(v) {
        // Handles "2026-08-19 17:35:29" (naive UTC, orderbook) and
        // ISO-8601 with offset (trades). Returns epoch ms or null.
        if (!v) return null;
        let s = String(v).trim();
        if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(s)) s = s.replace(' ', 'T') + 'Z';
        const t = Date.parse(s);
        return isFinite(t) ? t : null;
    }

    function isLive(createdAt) {
        const t = parseTime(createdAt);
        return t !== null && (Date.now() - t) <= LIVE_MS;
    }

    function fmtTime(createdAt) {
        const t = parseTime(createdAt);
        if (t === null) return String(createdAt || '-');
        const d = new Date(t);
        const day = String(d.getUTCDate()).padStart(2, '0');
        const mon = d.toLocaleString('en', { month: 'short', timeZone: 'UTC' });
        return `${mon} ${day} ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}Z`;
    }

    function fmtNum(v, maxDp) {
        const n = Number(v);
        if (!isFinite(n)) return String(v ?? '-');
        let s = n.toFixed(maxDp);
        if (s.indexOf('.') >= 0) s = s.replace(/0+$/, '').replace(/\.$/, '');
        return s;
    }

    function shortAddr(v) {
        const s = String(v || '');
        if (s.length <= 12) return s || '-';
        return `${s.slice(0, 6)}…${s.slice(-4)}`;
    }

    function orderMaker(o) {
        return o.user_address || o.maker || o.owner || '';
    }

    // ── book aggregation: collapse rows into price levels ───────────
    function toLevels(rows, side) {
        const map = new Map();   // price-string level -> summed remaining
        for (const o of rows || []) {
            const p = String(o.price);
            const rem = Number(o.remaining ?? o.amount ?? 0);
            if (!isFinite(rem) || rem <= 0) continue;
            const cur = map.get(p) || { price: p, size: 0, makers: [], newest: 0 };
            cur.size += rem;
            cur.makers.push(orderMaker(o));
            const t = parseTime(o.created_at) || 0;
            if (t > cur.newest) cur.newest = t;
            map.set(p, cur);
        }
        const arr = [...map.values()];
        arr.sort((a, b) => side === 'ask' ? Number(a.price) - Number(b.price)
                                        : Number(b.price) - Number(a.price));
        let cum = 0;
        for (const l of arr) { cum += l.size; l.depth = cum; }
        return arr;
    }

    function splitLive(rows) {
        const live = [], stale = [];
        for (const o of rows || []) (isLive(o.created_at) ? live : stale).push(o);
        return { live, stale };
    }

    // ── ladder rendering ─────────────────────────────────────────────
    function ladderRow(level, maxDepth, sideCls, live) {
        const tr = el('tr', 'ob-row ' + sideCls + (live ? '' : ' ob-stale'));
        const depthPct = maxDepth > 0 ? Math.min(100, (level.depth / maxDepth) * 100) : 0;
        const bar = el('span', 'ob-depth-bar');
        bar.style.width = depthPct.toFixed(1) + '%';
        const priceTd = el('td', 'ob-price');
        priceTd.appendChild(bar);
        priceTd.appendChild(el('span', 'ob-cell-text', fmtNum(level.price, 8)));
        tr.appendChild(priceTd);
        tr.appendChild(el('td', 'ob-num', fmtNum(level.size, 8)));
        tr.appendChild(el('td', 'ob-num', fmtNum(level.depth, 8)));
        const seen = [...new Set(level.makers.filter(Boolean))];
        tr.appendChild(el('td', 'ob-maker', seen.length ? seen.map(shortAddr).join(', ') : '-'));
        const flags = el('td', 'ob-flags');
        flags.appendChild(el('span', 'ob-unfunded', 'unfunded'));
        tr.appendChild(flags);
        return tr;
    }

    function renderBook(data) {
        const asksAll = (data && data.sells) || [];
        const bidsAll = (data && data.buys) || [];
        const asks = splitLive(asksAll);
        const bids = splitLive(bidsAll);
        const staleCount = asks.stale.length + bids.stale.length;

        const askLevels = toLevels(asks.live, 'ask');   // best ask = first
        const bidLevels = toLevels(bids.live, 'bid');
        const maxDepth = Math.max(
            askLevels.length ? askLevels[askLevels.length - 1].depth : 0,
            bidLevels.length ? bidLevels[bidLevels.length - 1].depth : 0);

        // stats row
        const bestAsk = askLevels.length ? Number(askLevels[0].price) : null;
        const bestBid = bidLevels.length ? Number(bidLevels[0].price) : null;
        const spreadEl = document.getElementById('ob-spread');
        const midEl = document.getElementById('ob-mid');
        if (bestAsk !== null && bestBid !== null) {
            const spread = bestAsk - bestBid;
            const pct = bestBid !== 0 ? (spread / bestBid) * 100 : null;
            if (spreadEl) spreadEl.textContent =
                `${fmtNum(spread, 8)} ETH/AIT` + (pct !== null ? ` (${pct.toFixed(1)}%)` : '');
            if (midEl) midEl.textContent = `${fmtNum((bestAsk + bestBid) / 2, 8)} ETH per AIT`;
        } else {
            if (spreadEl) spreadEl.textContent = '—';
            if (midEl) midEl.textContent = '—';
        }

        // ladder
        const asksBody = document.getElementById('ob-asks-body');
        const bidsBody = document.getElementById('ob-bids-body');
        const emptyEl = document.getElementById('ob-empty');
        const wrapEl = document.getElementById('ob-ladder');
        if (asksBody) asksBody.replaceChildren();
        if (bidsBody) bidsBody.replaceChildren();

        const hasLive = askLevels.length + bidLevels.length > 0;
        if (wrapEl) wrapEl.style.display = hasLive ? '' : 'none';
        if (emptyEl) emptyEl.style.display = hasLive ? 'none' : 'block';

        if (hasLive) {
            // asks render worst→best top-down so the best ask sits next to the spread
            for (const l of [...askLevels].reverse()) asksBody.appendChild(ladderRow(l, maxDepth, 'ob-ask', true));
            for (const l of bidLevels) bidsBody.appendChild(ladderRow(l, maxDepth, 'ob-bid', true));
        }

        // inactive section
        const det = document.getElementById('ob-inactive');
        const detBody = document.getElementById('ob-inactive-body');
        const detLabel = document.getElementById('ob-inactive-label');
        if (det && detBody) {
            if (staleCount > 0) {
                det.style.display = 'block';
                if (detLabel) detLabel.textContent = `Inactive test data (${staleCount} orders)`;
                detBody.replaceChildren();
                const all = [...asks.stale, ...bids.stale]
                    .sort((a, b) => (parseTime(b.created_at) || 0) - (parseTime(a.created_at) || 0));
                for (const o of all) {
                    const tr = el('tr', 'ob-row ob-stale');
                    tr.appendChild(el('td', '', o.order_type === 'BUY' ? 'bid' : 'ask'));
                    tr.appendChild(el('td', 'ob-num', fmtNum(o.price, 8)));
                    tr.appendChild(el('td', 'ob-num', fmtNum(o.remaining ?? o.amount, 8)));
                    tr.appendChild(el('td', 'ob-maker', shortAddr(orderMaker(o))));
                    tr.appendChild(el('td', '', fmtTime(o.created_at)));
                    detBody.appendChild(tr);
                }
            } else {
                det.style.display = 'none';
            }
        }
    }

    // ── tape ─────────────────────────────────────────────────────────
    function renderTape(data) {
        const rows = Array.isArray(data) ? data : (data && data.trades) || [];
        const live = [], stale = [];
        for (const t of rows) (isLive(t.created_at) ? live : stale).push(t);

        const body = document.getElementById('ob-tape-body');
        const emptyEl = document.getElementById('ob-tape-empty');
        const tableEl = document.getElementById('ob-tape-table');
        if (body) body.replaceChildren();

        const show = live.slice(0, TAPE_MAX);
        if (tableEl) tableEl.style.display = show.length ? '' : 'none';
        if (emptyEl) emptyEl.style.display = show.length ? 'none' : 'block';

        for (const t of show) {
            const tr = el('tr', 'ob-row');
            tr.appendChild(el('td', 'ob-num', fmtNum(t.price, 8)));
            tr.appendChild(el('td', 'ob-num', fmtNum(t.amount, 8)));
            const party = (t.buyer || t.buyer_address || '') + '↤' + (t.seller || t.seller_address || '');
            tr.appendChild(el('td', 'ob-maker', party === '↤' ? '-' : party.replace('↤', ' ← ')));
            tr.appendChild(el('td', '', fmtTime(t.created_at)));
            body.appendChild(tr);
        }

        const lastEl = document.getElementById('ob-last');
        if (lastEl) lastEl.textContent = show.length ? `${fmtNum(show[0].price, 8)} ETH per AIT` : '—';

        const det = document.getElementById('ob-tape-inactive');
        const detBody = document.getElementById('ob-tape-inactive-body');
        const detLabel = document.getElementById('ob-tape-inactive-label');
        if (det && detBody) {
            if (stale.length) {
                det.style.display = 'block';
                if (detLabel) detLabel.textContent = `Inactive test data (${stale.length} trades)`;
                detBody.replaceChildren();
                for (const t of stale.slice(0, TAPE_MAX)) {
                    const tr = el('tr', 'ob-row ob-stale');
                    tr.appendChild(el('td', 'ob-num', fmtNum(t.price, 8)));
                    tr.appendChild(el('td', 'ob-num', fmtNum(t.amount, 8)));
                    tr.appendChild(el('td', '', fmtTime(t.created_at)));
                    detBody.appendChild(tr);
                }
            } else {
                det.style.display = 'none';
            }
        }
    }

    // ── fetch + poll loop ────────────────────────────────────────────
    function setError(which, msg) {
        const e = document.getElementById(which);
        if (!e) return;
        if (msg) { e.textContent = msg; e.style.display = 'block'; }
        else e.style.display = 'none';
    }

    async function fetchJson(url) {
        const resp = await fetch(url, { headers: { 'Accept': 'application/json' } });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return resp.json();
    }

    async function refresh() {
        let ok = true;
        try {
            renderBook(await fetchJson(ORDERBOOK_URL));
            setError('ob-error', null);
        } catch (err) {
            ok = false;
            setError('ob-error', 'Order book unavailable — retrying automatically.');
            console.error('orderbook fetch failed:', err);
        }
        try {
            renderTape(await fetchJson(TRADES_URL));
            setError('ob-tape-error', null);
        } catch (err) {
            ok = false;
            setError('ob-tape-error', 'Trade tape unavailable — retrying automatically.');
            console.error('trades fetch failed:', err);
        }
        const lu = document.getElementById('ob-updated');
        if (lu) lu.textContent = 'last updated ' + new Date().toLocaleTimeString();
        backoffMs = ok ? REFRESH_MS : Math.min(backoffMs * 2, MAX_BACKOFF_MS);
    }

    function schedule() {
        if (timer) clearTimeout(timer);
        timer = setTimeout(async () => { await refresh(); schedule(); }, backoffMs);
    }

    function start() {
        if (!document.getElementById('ob-ladder')) return;   // page section absent
        refresh();         // immediate first paint
        schedule();
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                if (timer) { clearTimeout(timer); timer = null; }
            } else if (!timer) {
                refresh();
                schedule();
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
