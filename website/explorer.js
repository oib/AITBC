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
    return comp.map(([type, n]) => {
        const c = txTypeColor(type);
        return `<span class="tx-chip" style="color:${c};border-color:${c};background:color-mix(in srgb, ${c} 15%, transparent)"><i class="tx-chip-dot" style="background:${c}"></i>${escapeHtml(type)}&nbsp;×${n}</span>`;
    }).join('');
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
        `<span class="tx-comp-seg" style="width:${(n / total) * 100}%;background:${txTypeColor(type)}" title="${escapeHtml(type)} ×${n}"></span>`
    ).join('');
    return `<div class="tx-comp-bar">${bar}</div><div class="tx-chips">${txChipsHtml(comp)}</div>`;
}

// Shared block card — used by the Latest Blocks page.
function renderBlockCard(block) {
    let timestamp = 'N/A';
    if (block.timestamp) {
        if (typeof block.timestamp === 'string') {
            timestamp = aitbcFmt.date(block.timestamp);
        } else if (typeof block.timestamp === 'number') {
            timestamp = aitbcFmt.date(block.timestamp * 1000);
        }
    }
    const txCount = block.txCount || 0;
    const blockHash = block.hash || 'N/A';
    const proposer = block.proposer || 'N/A';
    const contentRow = Array.isArray(block.transactions)
        ? `<tr><td>Content</td><td class="tx-comp-cell">${blockContentHtml(block.transactions)}</td></tr>`
        : '';
    return `
        <div class="endpoint fade-in block-item" data-height="${escapeHtml(block.height)}" style="cursor:pointer;padding:0;" tabindex="0" role="link" onkeydown="if(event.key==='Enter'&&event.target===this)this.click()" onclick="location.href='/block.html?height=${encodeURIComponent(block.height)}'">
            <div class="table-wrap">
            <table class="block-list-table" aria-label="Block summary">
                <tr><th scope="row">Height</th><td><span class="badge badge-primary">BLOCK</span> #${escapeHtml(block.height)}</td></tr>
                <tr><th scope="row">Hash</th><td>${escapeHtml(blockHash)} ${aitbcCopyBtn(blockHash, 'block hash')}</td></tr>
                <tr><th scope="row">Proposer</th><td>${escapeHtml(proposer)}</td></tr>
                <tr><th scope="row">Transactions</th><td>${escapeHtml(txCount)}</td></tr>
                ${contentRow}
                <tr><th scope="row">Timestamp</th><td>${escapeHtml(timestamp)} UTC</td></tr>
            </table>
            </div>
        </div>
    `;
}


// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', function() {
    // Initialize icons
    lucide.createIcons();

    // Configuration - API endpoint (from shared website/config.js)
    const EXPLORER_API_URL = window.AITBC_CONFIG.explorerApiUrl; // Use nginx proxy
    let currentChain = window.AITBC_CONFIG.chainId;

    // Refresh data
    async function refreshData() {
        await loadActivityChart();
        await updateLiveFeed();
        await loadTopAddresses();
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
        try {
            const response = await fetch(`${EXPLORER_API_URL}/api/analytics/activity?chain_id=${currentChain}&days=30`);
            if (!canvas) return;
            const data = await response.json();
            // A failed or shapeless reply keeps the old chart — only a valid
            // empty labels array is a true "no activity".
            if (!response.ok || !Array.isArray(data.labels)) {
                markChartStale(canvas);
                return;
            }
            if (data.labels.length === 0) return;

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
                        legend: { labels: { color: '#e4e4e7' } },
                    },
                },
            });
            clearChartStale(canvas);
        } catch (error) {
            console.error('Error loading activity chart:', error);
            markChartStale(canvas);
        }
    }

    // Live feed
    let liveFeedItems = [];
    async function updateLiveFeed() {
        const container = document.getElementById('live-feed-list');
        try {
            const blocksResp = await fetch(`${EXPLORER_API_URL}/api/blocks/latest?chain_id=${currentChain}&limit=10`);
            const blocksData = await blocksResp.json();
            // A failed or shapeless reply keeps the old items — the feed must
            // never collapse to an empty list on a bad read.
            if (!blocksResp.ok || !blocksData || !Array.isArray(blocksData.blocks)) {
                throw new Error(blocksResp.ok ? 'unexpected reply' : `HTTP ${blocksResp.status}`);
            }

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
        } catch (error) {
            console.error('Error updating live feed:', error);
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
        }
    }

    let lastAnnouncedFeedKey = null;

    function renderLiveFeed() {
        const container = document.getElementById('live-feed-list');
        if (!container) return;
        const statusEl = document.getElementById('live-feed-status');
        if (statusEl && liveFeedItems.length && liveFeedItems[0].hash !== lastAnnouncedFeedKey) {
            lastAnnouncedFeedKey = liveFeedItems[0].hash;
            statusEl.textContent = `Live feed updated: ${liveFeedItems[0].type} ${liveFeedItems[0].label}`;
        }
        if (liveFeedItems.length === 0) {
            container.innerHTML = '<p class="loading-text">Waiting for activity...</p>';
            return;
        }
        container.innerHTML = liveFeedItems.map(item => {
            const timeStr = item.time ? aitbcFmt.time(item.time) : '';
            return `
                <div class="live-feed-item" tabindex="0" role="link" aria-label="${escapeHtml(item.type)} ${escapeHtml(item.hash || '')}" onkeydown="if(event.key==='Enter'&&event.target===this)this.click()" onclick="location.href='${escapeHtml(item.url)}'">
                    <span class="live-feed-type">${escapeHtml(item.type)}</span>
                    <span class="live-feed-hash">${escapeHtml(item.label)}</span>
                    ${item.comp ? `<span class="live-feed-comp">${item.comp}</span>` : ''}
                    <span class="live-feed-time">${escapeHtml(timeStr)}</span>
                </div>
            `;
        }).join('');
    }

    // Top addresses leaderboard
    async function loadTopAddresses() {
        const container = document.getElementById('top-addresses-container');
        if (!container) return;
        try {
            const resp = await fetch(`${EXPLORER_API_URL}/api/analytics/top-addresses?chain_id=${currentChain}&limit=20`);
            if (!resp.ok) {
                throw new Error(`HTTP ${resp.status}`);
            }
            const data = await resp.json();
            if (!data || !Array.isArray(data.addresses)) {
                throw new Error('unexpected reply');
            }
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
                            <tr tabindex="0" role="link" onkeydown="if(event.key==='Enter'&&event.target===this)this.click()" onclick="location.href='/search.html?query=${encodeURIComponent(a.address)}'" style="cursor:pointer;">
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
        } catch (error) {
            console.error('Error loading top addresses:', error);
            container.innerHTML = '<p class="error-text">Failed to load top addresses.</p>';
        }
    }

    // Clear search
    function clearSearch() {
        document.getElementById('search-input').value = '';
        document.getElementById('results-section').style.display = 'none';
    }

    // Perform simple search
    async function performSearch() {
        let query = document.getElementById('search-input').value.trim();
        if (!query) {
            return;
        }

        // Strip # prefix if present (e.g., user enters "#27381")
        query = query.replace(/^#/, '');

        // Try to determine if it's a block height, hash, or address
        const isNumber = /^\d+$/.test(query);
        const isHash = /^(0x)?[a-fA-F0-9]{64}$/.test(query);


        if (isNumber) {
            // Go directly to block detail
            location.href = `/block.html?height=${query}`;
        } else if (isHash) {
            // Try hash as transaction first, then block
            location.href = `/tx.html?hash=${encodeURIComponent(query)}`;
        } else {
            // Address or other search -> dedicated search page
            location.href = `/search.html?query=${encodeURIComponent(query)}`;
        }
    }

    // Auto-refresh every 30 seconds
    setInterval(refreshData, 30000);
    // Live feed refreshes every 60 seconds
    setInterval(updateLiveFeed, 60000);

    // Event listeners
    document.getElementById('clear-search-btn').addEventListener('click', clearSearch);
    document.getElementById('search-input').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            performSearch();
        }
    });

    // Initial load
    refreshData();

    // Redirect old ?search= param to dedicated search page
    const urlSearch = new URL(window.location.href).searchParams.get('search');
    if (urlSearch) {
        location.replace(`/search.html?query=${encodeURIComponent(urlSearch)}`);
    }
});
