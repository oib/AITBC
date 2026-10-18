function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function formatHash(hash) {
    if (!hash) return 'N/A';
    return escapeHtml(hash);
}



// Transaction-type palette — kept in sync with the activity timeline's
// type_colors map in apps/blockchain-explorer/routers/analytics.py so a
// block's content breakdown reads the same as the daily stats.
const TX_TYPE_COLORS = {
    BRIDGE_LOCK: '#22d3ee',
    BRIDGE_RELEASE: '#06b6d4',
    BRIDGE_REFUND: '#0891b2',
    ESCROW_FEE_SWEEP: '#a855f7',
    ESCROW_LOCK: '#c4b5fd',
    ESCROW_REFUND: '#7c3aed',
    ESCROW_RELEASE: '#8b5cf6',
    EXCHANGE: '#84cc16',
    GOVERNANCE_EXECUTE: '#d97706',
    GOVERNANCE_PROPOSE: '#fbbf24',
    GOVERNANCE_VOTE: '#f59e0b',
    GPU_ALLOCATE: '#6366f1',
    GPU_DEREGISTER: '#f97316',
    GPU_MARKET: '#3b82f6',
    GPU_MARKETPLACE: '#60a5fa',
    GPU_REGISTER: '#ef4444',
    IPFS_SUBSCRIPTION: '#14b8a6',
    STAKE_LOCK: '#fb7185',
    STAKE_RELEASE: '#f43f5e',
    TRANSFER: '#10b981',
};

// Fallback for types missing from TX_TYPE_COLORS — same idea as the backend's
// hue-from-hash (deterministic per type), using a small sync FNV-1a hash.
function txTypeColor(type) {
    const known = TX_TYPE_COLORS[type];
    if (known) return known;
    let h = 0x811c9dc5;
    for (let i = 0; i < type.length; i++) {
        h ^= type.charCodeAt(i);
        h = Math.imul(h, 0x01000193) >>> 0;
    }
    return `hsl(${h % 360} 65% 55%)`;
}

// Count a block's transactions by type — alphabetical like the timeline's
// dataset order.
function blockComposition(transactions) {
    const counts = {};
    (transactions || []).forEach(t => {
        const type = t.type || 'UNKNOWN';
        counts[type] = (counts[type] || 0) + 1;
    });
    return Object.entries(counts).sort(([a], [b]) => a.localeCompare(b));
}

function txChipsHtml(comp) {
    return comp.map(([type, n]) =>
        `<span class="tx-chip" data-tx-type="${escapeHtml(type)}"><i class="tx-chip-dot"></i>${escapeHtml(aitbcFmt.type(type))}&nbsp;×${n}</span>`
    ).join('');
}

// Applies the hash-derived tx colors and segment widths to rendered chip/bar
// markup via trusted CSSOM writes (inline style attributes are CSP-blocked).
function applyTxCompositionStyles(container) {
    container.querySelectorAll('[data-tx-type]').forEach(el => {
        el.style.setProperty('--tx-color', txTypeColor(el.getAttribute('data-tx-type') || 'UNKNOWN'));
    });
    container.querySelectorAll('[data-tx-percent]').forEach(el => {
        const percent = Number(el.getAttribute('data-tx-percent'));
        el.style.width = `${Number.isFinite(percent) ? Math.min(100, Math.max(0, percent)) : 0}%`;
    });
}

// Block content summary in the activity-timeline style: a thin stacked bar
// (segment width ∝ count, same colors) plus legend chips with counts.
function blockContentHtml(transactions) {
    const comp = blockComposition(transactions);
    if (comp.length === 0) {
        return '<span class="tx-comp-empty">no transactions</span>';
    }
    const total = comp.reduce((s, [, n]) => s + n, 0);
    const bar = comp.map(([type, n]) =>
        `<span class="tx-comp-seg" data-tx-type="${escapeHtml(type)}" data-tx-percent="${(n / total) * 100}" title="${escapeHtml(type)} ×${n}"></span>`
    ).join('');
    return `<div class="tx-comp-bar">${bar}</div><div class="tx-chips">${txChipsHtml(comp)}</div>`;
}

// Shared block card — used by the Latest Blocks page.
function renderBlockCard(block) {
    let timestamp = 'N/A';
    if (block.timestamp) {
        const raw = typeof block.timestamp === 'number' ? block.timestamp * 1000 : block.timestamp;
        const stamp = aitbcFmt.date(raw);
        // Local-clock stamp carries its real zone label — never a hard-coded
        // UTC word (WEB-TZ-1). stamp === '-' means unparseable → stays N/A
        // with no zone word.
        if (stamp !== '-') {
            timestamp = stamp + (typeof aitbcFmt.zone === 'function' ? ' ' + aitbcFmt.zone(raw) : '');
        }
    }
    const txCount = block.txCount || 0;
    const blockHash = block.hash || 'N/A';
    const proposer = block.proposer || 'N/A';
    const contentRow = Array.isArray(block.transactions)
        ? `<tr><td>Content</td><td class="tx-comp-cell">${blockContentHtml(block.transactions)}</td></tr>`
        : '';
    return `
        <div class="endpoint table-card fade-in block-item" data-height="${escapeHtml(block.height)}" tabindex="0" role="link" data-href="/block.html?height=${encodeURIComponent(block.height)}">
            <div class="table-wrap">
            <table class="block-list-table" aria-label="Block summary">
                <tr><th scope="row">Height</th><td><span class="badge badge-primary">BLOCK</span> #${escapeHtml(block.height)}</td></tr>
                <tr><th scope="row">Hash</th><td>${escapeHtml(blockHash)} ${aitbcCopyBtn(blockHash, 'block hash')}</td></tr>
                <tr><th scope="row">Proposer</th><td>${escapeHtml(proposer)}</td></tr>
                <tr><th scope="row">Transactions</th><td>${escapeHtml(txCount)}</td></tr>
                ${contentRow}
                <tr><th scope="row">Timestamp</th><td>${escapeHtml(timestamp)}</td></tr>
            </table>
            </div>
        </div>
    `;
}


// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', function() {
    // explorer.js is also loaded on blocks.html for the shared renderBlockCard
    // helper. On a page without the Explorer's live-feed panel none of this
    // init applies — running it anyway threw on the missing search controls
    // and started three intervals polling the explorer API for nothing.
    if (!document.getElementById('live-feed-list')) return;

    // Initialize icons
    lucide.createIcons();

    // Configuration - API endpoint (from shared website/config.js)
    const EXPLORER_API_URL = window.AITBC_CONFIG.explorerApiUrl; // Use nginx proxy
    let currentChain = window.AITBC_CONFIG.chainId;

    // ── Shared read/state helpers ──────────────────────────────────────
    // Every panel keeps its last good render. A failed or unreadable reply
    // lands the panel in stale (old content + last-good time) or failed
    // (reason + Try again) — never in empty, zero or loading.
    const FEED_DISCONNECT_MS = 2 * 60 * 1000; // two missed 60 s polls = disconnected
    let feedLastOkAt = 0;
    let feedLastBlockHeight = null;

    function ageAgo(ts) {
        const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
        if (s < 5) return 'just now';
        if (s < 90) return `${s} s ago`;
        return `${Math.round(s / 60)} min ago`;
    }

    function renderPanelSource(id, state, detail) {
        const src = document.getElementById(id);
        if (!src) return;
        const text = src.querySelector('.panel-src-text');
        const retry = src.querySelector('.bridge-retry');
        if (state === 'live') {
            src.dataset.lastGoodAt = String(Date.now());
            src.className = 'panel-source is-live';
            if (text) text.textContent = 'read just now';
            if (retry) retry.hidden = true;
            return;
        }
        if (state === 'stale') {
            const t = Number(src.dataset.lastGoodAt || 0);
            const when = t ? `last good read ${ageAgo(t)}` : 'keeping last data';
            src.className = 'panel-source is-stale';
            if (text) text.textContent = `${detail} — ${when}, checks again every 30 s`;
            if (retry) retry.hidden = true;
            return;
        }
        // failed — no good read has ever landed for this panel
        src.className = 'panel-source is-failed';
        if (text) text.textContent = `${detail} — checks again every 30 s`;
        if (retry) retry.hidden = false;
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

    function readFail(r, label) {
        return `${label}: ${r.err || `HTTP ${r.status}`}`;
    }

    // Refresh data
    async function refreshData() {
        await loadActivityChart();
        await updateLiveFeed();
        await loadTopAddresses();
    }

    // The legend counts and filters only datasets that actually show bars —
    // one predicate shared by the Chart.js labels.filter and the "Types (N)"
    // toggle label so they can never disagree.
    function datasetHasActivity(ds) {
        return !!ds && Array.isArray(ds.data) && ds.data.some(function (v) { return Number(v) > 0; });
    }

    // null = "no user choice yet" — the media query decides. Once the user
    // toggles, their choice survives the refresh rebuild and breakpoint
    // crossings (the chart instance is destroyed and rebuilt every 30 s, so
    // the choice must live outside it).
    let legendCollapsed = null;

    // WEB-LEGEND-3: dataset labels the user hid — lives outside the chart
    // like legendCollapsed so per-type choices survive the 30 s rebuild.
    const hiddenTypes = new Set();

    function chartDatasetVisible(chart, i) {
        return chart.isDatasetVisible ? chart.isDatasetVisible(i) : !(chart.data.datasets[i] || {}).hidden;
    }

    function setChartDatasetVisible(chart, i, visible) {
        if (chart.setDatasetVisibility) chart.setDatasetVisibility(i, visible);
        else chart.data.datasets[i].hidden = !visible;
    }

    function rememberDatasetVisible(chart, i) {
        const ds = chart.data.datasets[i];
        if (!ds || !ds.label) return;
        if (chartDatasetVisible(chart, i)) hiddenTypes.delete(ds.label);
        else hiddenTypes.add(ds.label);
    }

    // Compact per-type filter rendered only while the canvas legend is
    // collapsed (display === false) — the expanded Chart.js legend already
    // toggles series natively, so the chips never sit next to it.
    function syncLegendChips() {
        const box = document.getElementById('legend-chips');
        if (!box) return;
        const chart = window.activityChartInstance;
        if (!chart || chart.options.plugins.legend.display !== false) {
            box.hidden = true;
            box.innerHTML = '';
            return;
        }
        box.innerHTML = '';
        (chart.data.datasets || []).forEach(function (ds, i) {
            if (!datasetHasActivity(ds)) return;
            const visible = chartDatasetVisible(chart, i);
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'legend-chip';
            chip.setAttribute('aria-pressed', String(visible));
            const swatch = document.createElement('span');
            swatch.className = 'legend-chip-swatch';
            swatch.style.setProperty('--chip-color', ds.backgroundColor || '#71717a');
            chip.appendChild(swatch);
            const label = document.createElement('span');
            label.className = 'legend-chip-label';
            label.textContent = String(ds.label || `Type ${i + 1}`);
            chip.appendChild(label);
            chip.addEventListener('click', function () {
                setChartDatasetVisible(chart, i, !chartDatasetVisible(chart, i));
                rememberDatasetVisible(chart, i);
                chart.update();
                syncLegendChips();
            });
            box.appendChild(chip);
        });
        box.hidden = false;
    }

    function legendAutoCollapsed() {
        return !!(window.matchMedia && window.matchMedia('(max-width: 640px)').matches);
    }

    function syncLegendToggle() {
        const btn = document.getElementById('legend-toggle');
        if (!btn) return;
        const chart = window.activityChartInstance;
        if (!chart) {
            // No chart data at all — the failed/stale note stands alone and
            // the toggle must never read "Types (0)".
            btn.hidden = true;
            syncLegendChips();
            return;
        }
        const collapsed = chart.options.plugins.legend.display === false;
        const shown = (chart.data.datasets || []).filter(datasetHasActivity).length;
        btn.hidden = false;
        btn.textContent = `Types (${shown})`;
        btn.setAttribute('aria-expanded', String(!collapsed));
        syncLegendChips();
    }

    function toggleLegend() {
        const chart = window.activityChartInstance;
        if (!chart) return;
        legendCollapsed = !(chart.options.plugins.legend.display === false);
        chart.options.plugins.legend.display = !legendCollapsed;
        chart.update();
        syncLegendToggle();
    }

    // Load activity timeline chart
    function markChartStale(canvas) {
        if (!canvas || !canvas.parentElement) return;
        let note = canvas.parentElement.querySelector('.chart-refresh-note');
        if (!note) {
            note = document.createElement('p');
            note.className = 'muted-text chart-refresh-note';
            canvas.parentElement.insertBefore(note, canvas.nextSibling);
        }
        note.textContent = `Activity chart could not refresh (${aitbcFmt.time()}).`;
    }

    function clearChartStale(canvas) {
        const note = canvas && canvas.parentElement && canvas.parentElement.querySelector('.chart-refresh-note');
        if (note) note.remove();
    }

    async function loadActivityChart() {
        const canvas = document.getElementById('activity-chart');
        const r = await readJson(`${EXPLORER_API_URL}/api/analytics/activity?chain_id=${currentChain}&days=30`);
        if (!canvas) return;
        const data = r.data;
        // A failed or shapeless reply keeps the old chart — only a valid
        // empty labels array is a true "no activity".
        if (!r.ok || !data || !Array.isArray(data.labels)) {
            const reason = r.ok ? 'reply was not the expected shape' : (r.err || `HTTP ${r.status}`);
            markChartStale(canvas);
            renderPanelSource('chart-source', window.activityChartInstance ? 'stale' : 'failed', `activity could not refresh (${reason})`);
            syncLegendToggle();
            return;
        }
        if (data.labels.length > 0) {
            // Humanize dataset labels once — the canvas legend, tooltips and
            // the collapsed-state chips all read ds.label (WEB-LEGEND-3).
            (data.datasets || []).forEach(function (ds) {
                if (ds && ds.label) ds.label = aitbcFmt.type(ds.label);
            });
            const ctx = canvas.getContext('2d');
            // Destroy existing chart if any
            if (window.activityChartInstance) {
                window.activityChartInstance.destroy();
            }
            window.activityChartInstance = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.labels,
                    datasets: data.datasets,
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { stacked: true, ticks: { color: '#71717a' } },
                        y: { stacked: true, ticks: { color: '#71717a' }, grid: { color: '#27272a' } },
                    },
                    plugins: {
                        legend: {
                            // Collapsed by default at <=640px (WEB-LEGEND-1):
                            // the 17-item legend otherwise takes half the
                            // 200px chart box. A user choice outlives the
                            // refresh rebuild via legendCollapsed.
                            display: !(legendCollapsed === null ? legendAutoCollapsed() : legendCollapsed),
                            labels: {
                                color: '#e4e4e7',
                                boxWidth: 10,
                                boxHeight: 10,
                                padding: 8,
                                font: { size: 11 },
                                // Hide transaction types with no activity in this
                                // window: the legend lists only what the bars show.
                                filter: function (item, chartData) {
                                    return datasetHasActivity(chartData.datasets[item.datasetIndex]);
                                },
                            },
                            // Same toggling as the default handler, plus
                            // recording into hiddenTypes so the choice also
                            // survives the next rebuild like chip clicks do.
                            onClick: function (_e, item, legend) {
                                const c = legend.chart;
                                const i = item.datasetIndex;
                                setChartDatasetVisible(c, i, !chartDatasetVisible(c, i));
                                rememberDatasetVisible(c, i);
                                c.update();
                            },
                        },
                    },
                },
            });
            // Reapply per-type hides recorded before this rebuild.
            const built = window.activityChartInstance;
            (built.data.datasets || []).forEach(function (ds, i) {
                if (ds && hiddenTypes.has(ds.label)) setChartDatasetVisible(built, i, false);
            });
        }
        syncLegendToggle();
        clearChartStale(canvas);
        renderPanelSource('chart-source', 'live');
    }

    // Live feed
    let liveFeedItems = [];

    function hideFeedDisconnect() {
        const box = document.getElementById('feed-disconnect');
        if (box) box.hidden = true;
    }

    function checkFeedDisconnected() {
        const box = document.getElementById('feed-disconnect');
        if (!box) return;
        // Only a feed that once answered can be "disconnected" — a feed that
        // never landed shows failed/stale on its source line instead.
        const age = feedLastOkAt ? Date.now() - feedLastOkAt : 0;
        if (!feedLastOkAt || age < FEED_DISCONNECT_MS) {
            hideFeedDisconnect();
            return;
        }
        box.hidden = false;
        const ago = document.getElementById('feed-stopped-ago');
        if (ago) ago.textContent = ageAgo(feedLastOkAt);
        const lb = document.getElementById('feed-last-block');
        if (lb) lb.textContent = feedLastBlockHeight !== null
            ? `latest known block #${feedLastBlockHeight}`
            : 'no block height received yet';
    }

    async function updateLiveFeed() {
        const container = document.getElementById('live-feed-list');
        const r = await readJson(`${EXPLORER_API_URL}/api/blocks/latest?chain_id=${currentChain}&limit=10`);
        const blocksData = r.data;
        // A failed or shapeless reply keeps the old items — the feed must
        // never collapse to an empty list on a bad read.
        if (!r.ok || !blocksData || !Array.isArray(blocksData.blocks)) {
            const reason = r.ok ? 'reply was not the expected shape' : (r.err || `HTTP ${r.status}`);
            // Keep the last good items; show one muted refresh-failed line.
            if (container) {
                let note = container.querySelector('.feed-refresh-note');
                if (!note) {
                    note = document.createElement('p');
                    note.className = 'muted-text feed-refresh-note';
                    container.prepend(note);
                }
                note.textContent = `Live feed could not refresh (${aitbcFmt.time()}).`;
            }
            renderPanelSource('feed-source', liveFeedItems.length ? 'stale' : 'failed', `live feed could not refresh (${reason})`);
            checkFeedDisconnected();
            return;
        }

        feedLastOkAt = Date.now();
        const newest = (blocksData.blocks || []).find(b => b && b.height !== undefined && b.height !== null);
        if (newest) feedLastBlockHeight = newest.height;

        const newItems = [];
        (blocksData.blocks || []).forEach(b => {
            newItems.push({
                type: 'BLOCK',
                label: `#${b.height}`,
                hash: b.hash,
                time: b.timestamp,
                url: `/block.html?height=${encodeURIComponent(b.height)}`,
                comp: txChipsHtml(blockComposition(b.transactions)),
            });
            // Extract transactions from block
            (b.transactions || []).forEach(t => {
                newItems.push({
                    type: t.type || 'TX',
                    label: (t.tx_hash || t.hash || '').substring(0, 16) + '...',
                    hash: t.tx_hash || t.hash,
                    time: t.created_at,
                    url: `/tx.html?hash=${encodeURIComponent(t.tx_hash || t.hash || '')}`,
                });
            });
        });

        // Sort by time descending
        newItems.sort((a, b) => {
            const ta = a.time ? new Date(a.time).getTime() : 0;
            const tb = b.time ? new Date(b.time).getTime() : 0;
            return tb - ta;
        });

        // Keep only top 10
        liveFeedItems = newItems.slice(0, 10);
        renderLiveFeed();
        renderPanelSource('feed-source', 'live');
        hideFeedDisconnect();
        // Clear a stale refresh-failed note once the feed answers again.
        const note = container && container.querySelector('.feed-refresh-note');
        if (note) note.remove();
    }

    let lastAnnouncedFeedKey = null;

    function renderLiveFeed() {
        const container = document.getElementById('live-feed-list');
        if (!container) return;
        const statusEl = document.getElementById('live-feed-status');
        if (statusEl && liveFeedItems.length && liveFeedItems[0].hash !== lastAnnouncedFeedKey) {
            lastAnnouncedFeedKey = liveFeedItems[0].hash;
            statusEl.textContent = `Live feed updated: ${aitbcFmt.type(liveFeedItems[0].type)} ${liveFeedItems[0].label}`;
        }
        if (liveFeedItems.length === 0) {
            container.innerHTML = '<p class="loading-text">Waiting for activity...</p>';
            return;
        }
        container.innerHTML = liveFeedItems.map(item => {
            const timeStr = item.time ? aitbcFmt.time(item.time) : '';
            return `
                <div class="live-feed-item" tabindex="0" role="link" aria-label="${escapeHtml(aitbcFmt.type(item.type))} ${escapeHtml(item.hash || '')}" data-href="${escapeHtml(item.url)}">
                    <span class="live-feed-type">${escapeHtml(aitbcFmt.type(item.type))}</span>
                    <span class="live-feed-hash">${escapeHtml(item.label)}</span>
                    ${item.comp ? `<span class="live-feed-comp">${item.comp}</span>` : ''}
                    <span class="live-feed-time">${escapeHtml(timeStr)}</span>
                </div>
            `;
        }).join('');
        applyTxCompositionStyles(container);
    }

    // Top addresses leaderboard
    async function loadTopAddresses() {
        const container = document.getElementById('top-addresses-container');
        if (!container) return;
        const r = await readJson(`${EXPLORER_API_URL}/api/analytics/top-addresses?chain_id=${currentChain}&limit=20`);
        const data = r.data;
        if (!r.ok || !data || !Array.isArray(data.addresses)) {
            const reason = r.ok ? 'reply was not the expected shape' : (r.err || `HTTP ${r.status}`);
            // Keep the last good table — a failed read never becomes an
            // empty table or a zero.
            renderPanelSource('ta-source', container.dataset.taLoaded === '1' ? 'stale' : 'failed', `could not load top addresses (${reason})`);
            return;
        }
        container.dataset.taLoaded = '1';
        renderPanelSource('ta-source', 'live');
        const addresses = data.addresses;
        if (addresses.length === 0) {
            container.innerHTML = '<p class="loading-text">No address data yet.</p>';
            return;
        }
        container.innerHTML = `
        <div class="table-wrap" role="region" tabindex="0" aria-label="Top addresses by volume">
            <table aria-label="Top addresses by volume">
                <thead><tr><th scope="col">#</th><th scope="col">Address</th><th scope="col">TXs</th><th scope="col">Volume (AIT)</th></tr></thead>
                <tbody>
                    ${addresses.map((a, i) => `
                        <tr tabindex="0" role="link" data-href="/search.html?query=${encodeURIComponent(a.address)}">
                            <td>${i + 1}</td>
                            <td>${escapeHtml(a.address)}</td>
                            <td>${escapeHtml(a.transaction_count)}</td>
                            <td>${typeof a.volume === 'number' ? aitbcFmt.num(a.volume, 2) : escapeHtml(a.volume)}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
        `;
    }

    // ── Search: three kept-apart answers ──────────────────────────────
    // found (labelled + link to details) · nothing found (only after a
    // proven 404 or empty answer) · could not be completed (reason +
    // Try again — a failure is not a "nothing exists").

    function setSearchRetry(visible) {
        const btn = document.getElementById('search-retry-btn');
        if (btn) btn.hidden = !visible;
    }

    function showSearchAnswer(html, countText) {
        const section = document.getElementById('results-section');
        const container = document.getElementById('results-container');
        const count = document.getElementById('results-count');
        if (!section || !container) return;
        section.classList.remove('hidden');
        section.hidden = false;
        container.innerHTML = html;
        if (count) count.textContent = countText || '';
    }

    function searchNothingFound(query) {
        showSearchAnswer(
            `<p class="join-neutral">Nothing found for <strong>&ldquo;${escapeHtml(query)}&rdquo;</strong> — all lookups answered empty or not-found.</p>`
        );
        setSearchRetry(false);
    }

    function searchFailed(query, reason) {
        showSearchAnswer(
            `<div class="join-failed" role="alert">` +
            `<p class="join-failed-title">Search could not be completed (${escapeHtml(reason)})</p>` +
            `<p class="join-failed-detail">This does not mean nothing exists for &ldquo;${escapeHtml(query)}&rdquo; — the search could not be checked.</p>` +
            `</div>`
        );
        setSearchRetry(true);
    }

    function searchFound(label, href, countText) {
        showSearchAnswer(
            `<p class="answer-found">Found: <strong>${escapeHtml(label)}</strong> — <a href="${escapeHtml(href)}">open details</a></p>`,
            countText
        );
        setSearchRetry(false);
    }

    function plural(n, word) {
        return `${n} ${word}${n === 1 ? '' : 's'}`;
    }

    // Clear search
    function clearSearch() {
        document.getElementById('search-input').value = '';
        const section = document.getElementById('results-section');
        section.classList.add('hidden');
        section.hidden = true;
        setSearchRetry(false);
    }

    // Perform the search — queries the same explorer-api routes the
    // dedicated search page uses; the three answers land in the results card.
    async function performSearch() {
        let query = document.getElementById('search-input').value.trim();
        if (!query) {
            return;
        }

        // Strip # prefix if present (e.g., user enters "#27381")
        query = query.replace(/^#/, '');

        const isNumber = /^\d+$/.test(query);
        const isHash = /^(0x)?[a-fA-F0-9]{64}$/.test(query);

        showSearchAnswer('<p class="endpoint-note-sm">Searching…</p>');
        setSearchRetry(false);

        if (isNumber) {
            const r = await readJson(`${EXPLORER_API_URL}/api/blocks/${encodeURIComponent(query)}`);
            if (r.ok) {
                searchFound(`Block ${aitbcFmt.num(Number(query), 0)}`, `/block.html?height=${encodeURIComponent(query)}`, '1 result');
            } else if (r.status === 404) {
                searchNothingFound(query);
            } else {
                searchFailed(query, r.err || `HTTP ${r.status}`);
            }
            return;
        }

        if (isHash) {
            const tx = await readJson(`${EXPLORER_API_URL}/api/transactions/${encodeURIComponent(query)}`);
            if (tx.ok) {
                searchFound('Transaction', `/tx.html?hash=${encodeURIComponent(query)}`, '1 result');
                return;
            }
            if (tx.status !== 404) {
                searchFailed(query, tx.err || `HTTP ${tx.status}`);
                return;
            }
            const blk = await readJson(`${EXPLORER_API_URL}/api/blocks/by-hash/${encodeURIComponent(query)}`);
            if (blk.ok) {
                const h = blk.data && blk.data.height !== undefined ? ` ${aitbcFmt.num(Number(blk.data.height), 0)}` : '';
                searchFound(`Block${h}`, `/block.html?hash=${encodeURIComponent(query)}`, '1 result');
            } else if (blk.status === 404) {
                searchNothingFound(query);
            } else {
                searchFailed(query, blk.err || `HTTP ${blk.status}`);
            }
            return;
        }

        // Address or free text — the three-legged search the dedicated page
        // runs. "Found" stands on the hard legs (transactions, blocks);
        // "nothing found" needs every leg proven empty — a degraded
        // messages leg makes the answer inconclusive, not a not-found.
        const [txs, blocks, msgs] = await Promise.all([
            readJson(`${EXPLORER_API_URL}/api/transactions/search?address=${encodeURIComponent(query)}&limit=50`),
            readJson(`${EXPLORER_API_URL}/api/blocks/by-address/${encodeURIComponent(query)}?limit=50`),
            readJson(`${EXPLORER_API_URL}/api/messages/search?q=${encodeURIComponent(query)}&limit=50`),
        ]);
        const hardFail = [txs, blocks].find(r => !r.ok && r.status !== 404);
        if (hardFail) {
            searchFailed(query, hardFail.err || `HTTP ${hardFail.status}`);
            return;
        }
        // An ok reply is only a proven-empty when it carries the array —
        // an ok body without it ("{}") is a shape failure, not a zero.
        const legItems = (r, key) => (r.data && Array.isArray(r.data[key])) ? r.data[key] : null;
        const txArr = txs.ok ? legItems(txs, 'transactions') : null;
        const blkArr = blocks.ok ? legItems(blocks, 'blocks') : null;
        const msgArr = msgs.ok ? legItems(msgs, 'messages') : null;
        // A hard leg answered ok but without its list — inconclusive,
        // not "nothing found".
        if ((txs.ok && txArr === null) || (blocks.ok && blkArr === null)) {
            searchFailed(query, 'reply was not the expected shape');
            return;
        }
        // The messages leg is proxied: any non-ok (incl. 404 — a missing
        // route cannot prove "no match") or shapeless ok degrades it.
        const msgLegFailed = !msgs.ok || (msgs.ok && msgArr === null);
        const msgLegReason = msgs.ok
            ? 'reply was not the expected shape'
            : (msgs.err || `HTTP ${msgs.status}`);
        const txN = txArr ? txArr.length : 0;
        const blkN = blkArr ? blkArr.length : 0;
        const msgN = msgArr ? msgArr.length : 0;
        if (txN + blkN + msgN > 0) {
            const parts = [
                txN ? plural(txN, 'transaction') : null,
                blkN ? plural(blkN, 'block') : null,
                msgN ? plural(msgN, 'message') : null,
            ].filter(Boolean).join(' · ');
            showSearchAnswer(
                `<p class="answer-found">Found: <strong>${escapeHtml(parts)}</strong> for &ldquo;${escapeHtml(query)}&rdquo; — ` +
                `<a href="/search.html?query=${encodeURIComponent(query)}">open full results</a></p>`,
                `${txN + blkN + msgN} results`
            );
            setSearchRetry(false);
            return;
        }
        if (msgLegFailed) {
            searchFailed(query, `messages leg: ${msgLegReason}`);
            return;
        }
        searchNothingFound(query);
    }

    // Auto-refresh every 30 seconds
    setInterval(refreshData, 30000);
    // Live feed refreshes every 60 seconds
    setInterval(updateLiveFeed, 60000);
    // Disconnected-state check: ages the "stopped N s ago" line and trips
    // the box once the feed's last good answer crosses the threshold.
    setInterval(checkFeedDisconnected, 30000);

    // Event listeners
    document.getElementById('clear-search-btn').addEventListener('click', clearSearch);
    document.getElementById('search-input').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            performSearch();
        }
    });
    const wire = (id, fn) => { const el = document.getElementById(id); if (el) el.addEventListener('click', fn); };
    wire('search-retry-btn', performSearch);
    wire('feed-reconnect-btn', updateLiveFeed);
    wire('feed-retry-btn', updateLiveFeed);
    wire('chart-retry-btn', loadActivityChart);
    wire('legend-toggle', toggleLegend);
    wire('ta-retry-btn', loadTopAddresses);

    // Initial load
    refreshData();

    // Redirect old ?search= param to dedicated search page
    const urlSearch = new URL(window.location.href).searchParams.get('search');
    if (urlSearch) {
        location.replace(`/search.html?query=${encodeURIComponent(urlSearch)}`);
    }
});
