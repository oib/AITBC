function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// ── Shared read/state helpers ────────────────────────────────────────
// Every read keeps its last good result. A failed or unreadable reply
// lands the element in stale (old value + last-good time) or failed
// (Unavailable / reason + Try again) — never in empty, zero or "--".

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

// A stat cell keeps its last good number across failures. With a last
// good it goes stale (value stays, "last read" note); without one it
// shows Unavailable — amber, never "--" or 0.
function setStatGood(id, num) {
    const el = document.getElementById(id);
    if (!el) return;
    el.dataset.lastGood = String(num);
    el.dataset.lastGoodAt = String(Date.now());
    el.classList.remove('stat-failed', 'stat-stale');
    el.textContent = Number(num).toLocaleString('en-US');
}

function setStatFailed(id, reason) {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.dataset.lastGood !== undefined) {
        el.classList.remove('stat-failed');
        el.classList.add('stat-stale');
        el.innerHTML = `${escapeHtml(Number(el.dataset.lastGood).toLocaleString('en-US'))}` +
            `<span class="stat-note">last read ${escapeHtml(ageAgo(Number(el.dataset.lastGoodAt)))} — could not refresh (${escapeHtml(reason)})</span>`;
    } else {
        el.classList.remove('stat-stale');
        el.classList.add('stat-failed');
        el.innerHTML = `Unavailable<span class="stat-note">${escapeHtml(reason)}</span>`;
    }
}

let allOffers = [];
let offersLastGoodAt = 0;
let offersStale = false;
let offersFailReason = '';
let currentFilter = 'all';
let currentStatusFilter = 'all';
let confirmedOnly = false;

// The offers list failed. Last-good cards stay and one stale note names
// the reason + last-good time; with nothing good the amber card carries
// reason + Try again — a failed read never reads as an empty market.
function renderOffersFailed(reason) {
    const container = document.getElementById('offers-container');
    const count = document.getElementById('offer-count');
    if (!container) return;
    if (!allOffers.length) {
        container.innerHTML = `
            <div class="offers-state" role="alert">
                <p class="offers-state-title">Offers could not be loaded (${escapeHtml(reason)})</p>
                <p class="offers-state-detail">This does not mean no offers exist — the read failed. Checks again every 30 s.</p>
                <button id="offers-retry-btn" type="button" class="bridge-retry">Try again</button>
            </div>`;
        const btn = container.querySelector('#offers-retry-btn');
        if (btn) btn.addEventListener('click', fetchOffers);
        if (count) count.textContent = 'Could not load offers';
        return;
    }
    // keep the last good cards — stale note is rendered by renderOffers
    offersStale = true;
    offersFailReason = reason;
    renderOffers();
    if (count) count.textContent = `Showing ${filterOffers(allOffers, currentFilter, currentStatusFilter).length} of ${allOffers.length} offers — last read ${ageAgo(offersLastGoodAt)}`;
}

async function fetchOffers() {
    // Build query parameters based on current filters
    const params = new URLSearchParams();
    if (currentFilter !== 'all') {
        params.append('service_type', currentFilter);
    }
    if (currentStatusFilter !== 'all') {
        params.append('status', currentStatusFilter);
    }

    const r = await readJson(`/v1/market/offer?${params.toString()}`);
    const data = r.data;
    if (!r.ok || !data || !Array.isArray(data.offers)) {
        const reason = r.ok ? 'reply was not the expected shape' : (r.err || `HTTP ${r.status}`);
        renderOffersFailed(reason);
        setStatFailed('stat-listed-offers', reason);
        return;
    }
    allOffers = data.offers;
    offersLastGoodAt = Date.now();
    offersStale = false;
    setStatGood('stat-listed-offers', allOffers.length);
    updateOfferCount();
    renderOffers();
}

function updateOfferCount() {
    const filteredOffers = filterOffers(allOffers, currentFilter, currentStatusFilter);
    document.getElementById('offer-count').textContent = `Showing ${filteredOffers.length} of ${allOffers.length} offers`;
}

function filterOffers(offers, serviceType, status) {
    return offers.filter(offer => {
        const matchesServiceType = serviceType === 'all' || offer.service_type === serviceType;
        const matchesStatus = status === 'all' || offer.status === status;
        const matchesConfirmed = !confirmedOnly || offer.confirmed === true;
        return matchesServiceType && matchesStatus && matchesConfirmed;
    });
}

function renderOffers() {
    const container = document.getElementById('offers-container');
    const filteredOffers = filterOffers(allOffers, currentFilter, currentStatusFilter);

    // Two kept-apart empties: "filters leave zero" only after a good load,
    // "nothing listed" only after a proven ok empty list.
    if (filteredOffers.length === 0) {
        if (allOffers.length === 0) {
            container.innerHTML = `
                <div class="no-offers">
                    <p>No offers listed yet.</p>
                </div>`;
        } else {
            container.innerHTML = `
                <div class="no-offers">
                    <p>No offers match these filters.</p>
                    <button id="clear-filters-btn" type="button" class="bridge-retry">Clear filters</button>
                </div>`;
            const btn = container.querySelector('#clear-filters-btn');
            if (btn) btn.addEventListener('click', clearFilters);
        }
        return;
    }

    const staleNote = offersStale
        ? `<div class="offers-state offers-stale-note" role="status">
               <span>Offers could not refresh (${escapeHtml(offersFailReason)}) — showing the list read ${escapeHtml(ageAgo(offersLastGoodAt))}. Checks again every 30 s.</span>
               <button id="offers-retry-btn" type="button" class="bridge-retry">Try again</button>
           </div>`
        : '';

    let html = '';
    filteredOffers.forEach(offer => {
        html += createOfferCard(offer);
    });

    container.innerHTML = staleNote + html;
    const btn = container.querySelector('#offers-retry-btn');
    if (btn) btn.addEventListener('click', fetchOffers);
    updateOfferCount();
    loadReputations();
}

function clearFilters() {
    currentFilter = 'all';
    currentStatusFilter = 'all';
    confirmedOnly = false;
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === 'all');
    });
    const status = document.getElementById('status-filter');
    if (status) status.value = 'all';
    const toggle = document.getElementById('confirmed-only-toggle');
    if (toggle) toggle.checked = false;
    renderOffers();
}

function createOfferCard(offer) {
    const statusClass = offer.status === 'active' ? 'active' : 'inactive';
    const statusText = offer.status ? offer.status.charAt(0).toUpperCase() + offer.status.slice(1) : 'Unknown';

    const ratingStars = offer.avg_rating ? '★'.repeat(Math.round(offer.avg_rating)) : 'N/A';
    const ratingCount = offer.rating_count || 0;
    const providerId = offer.provider_address || offer.node_id || '';

    const registeredRaw = offer.registered_at || offer.block_timestamp;
    const registeredDate = registeredRaw ? aitbcFmt.date(registeredRaw) : 'N/A';
    const updatedDate = offer.updated_at ? aitbcFmt.date(offer.updated_at) : 'N/A';

    // Blockchain verification information — badge in words, colour as backup.
    const isConfirmed = offer.confirmed === true;
    const confirmationBadge = isConfirmed
        ? `<span class="blockchain-confirmed">ON CHAIN · block #${escapeHtml(offer.block_height)}</span>`
        : `<span class="blockchain-pending">NOT CONFIRMED</span>`;

    const blockInfo = isConfirmed ? `
        <div class="blockchain-info">
            <div class="blockchain-detail">
                <span class="blockchain-label">Block Height:</span>
                <span class="blockchain-value">${offer.block_height != null
                    ? `<a href="/block.html?height=${encodeURIComponent(offer.block_height)}" target="_blank" rel="noopener noreferrer">#${escapeHtml(offer.block_height)}</a>`
                    : 'N/A'}</span>
            </div>
            <div class="blockchain-detail">
                <span class="blockchain-label">Block Hash:</span>
                <span class="blockchain-value">${formatBlockHash(offer.block_hash)}</span>
            </div>
            <div class="blockchain-detail">
                <span class="blockchain-label">Transaction Hash:</span>
                <span class="blockchain-value">${formatTxHash(offer.tx_hash)}</span>
            </div>
            <div class="blockchain-detail">
                <span class="blockchain-label">Block Time:</span>
                <span class="blockchain-value">${escapeHtml(offer.block_timestamp ? aitbcFmt.date(offer.block_timestamp) : 'N/A')}</span>
            </div>
            <div class="blockchain-detail">
                <span class="blockchain-label">Proposer:</span>
                <span class="blockchain-value">${formatAddress(offer.block_proposer)}</span>
            </div>
        </div>
    ` : '';

    return `
        <div class="offer-card">
            <div class="offer-header">
                <div class="offer-title">${formatServiceTitle(offer)}</div>
                <div class="offer-status ${statusClass}">${escapeHtml(statusText)}</div>
            </div>

            <div class="blockchain-status">
                ${confirmationBadge}
            </div>
            <div class="reputation-badge" data-provider="${escapeHtml(providerId)}" id="rep-${escapeHtml(offer.plugin_id || offer.id || Math.random().toString(36).slice(2))}">
                <span class="rep-score">--</span>
                <span class="rep-level">Loading...</span>
            </div>

            <div class="offer-description">
                ${escapeHtml(offer.description || 'No description available')}
            </div>

            <div class="offer-details">
                <div class="offer-detail">
                    <div class="offer-detail-label">Service Type</div>
                    <div class="offer-detail-value">${escapeHtml(offer.service_type || 'N/A')}</div>
                </div>
                <div class="offer-detail">
                    <div class="offer-detail-label">Model</div>
                    <div class="offer-detail-value">${escapeHtml(offer.model || 'N/A')}</div>
                </div>
                <div class="offer-detail">
                    <div class="offer-detail-label">Price</div>
                    <div class="offer-detail-value">${formatPrice(offer.price)} ${escapeHtml(offer.price_unit || 'units')}</div>
                </div>
                <div class="offer-detail">
                    <div class="offer-detail-label">GPU</div>
                    <div class="offer-detail-value">${formatGPU(offer.gpu_name, offer.gpu_device)}</div>
                </div>
                <div class="offer-detail">
                    <div class="offer-detail-label">Endpoint</div>
                    <div class="offer-detail-value">${formatEndpoint(offer.public_endpoint || offer.endpoint)}</div>
                </div>
            </div>

            <div class="offer-details-list">
                <div class="offer-list-item">
                    <span class="offer-list-label">Provider:</span>
                    <span class="offer-list-value">${formatAddress(offer.provider_address)}</span>
                </div>
                <div class="offer-list-item">
                    <span class="offer-list-label">Node ID:</span>
                    <span class="offer-list-value">${escapeHtml(offer.node_id || 'N/A')}</span>
                </div>
                <div class="offer-list-item">
                    <span class="offer-list-label">Plugin ID:</span>
                    <span class="offer-list-value">${escapeHtml(offer.plugin_id || 'N/A')}</span>
                </div>
            </div>

            <div class="offer-meta">
                <div class="offer-rating">
                    <span class="offer-rating-value">${ratingStars}</span>
                    <span>(${escapeHtml(ratingCount)} reviews)</span>
                </div>
                <div>
                    <span>Registered: ${escapeHtml(registeredDate)}</span>
                    <span style="margin-left: 1rem;">Updated: ${escapeHtml(updatedDate)}</span>
                </div>
            </div>
        </div>
    `;
}

function formatServiceTitle(offer) {
    const serviceType = escapeHtml(offer.service_type || 'Unknown Service');
    const model = escapeHtml(offer.model || '');
    return model ? `${serviceType} - ${model}` : serviceType;
}

function formatAddress(address) {
    return escapeHtml(address || 'N/A');
}

function formatHash(hash) {
    return escapeHtml(hash || 'N/A');
}

function formatTxHash(hash) {
    if (!hash) return 'N/A';
    return `<a href="/tx.html?hash=${encodeURIComponent(hash)}" target="_blank" rel="noopener noreferrer">${escapeHtml(hash.slice(0, 18))}...</a> ${aitbcCopyBtn(hash, 'transaction hash')}`;
}

function formatBlockHash(hash) {
    if (!hash) return 'N/A';
    return `<a href="/block.html?hash=${encodeURIComponent(hash)}" target="_blank" rel="noopener noreferrer">${escapeHtml(hash.slice(0, 18))}...</a> ${aitbcCopyBtn(hash, 'block hash')}`;
}

function formatPrice(price) {
    const n = parseFloat(price);
    if (isNaN(n)) return escapeHtml(price || '0');
    // Strip trailing zeros from decimal-stored prices ("0.10000000" -> "0.1")
    return escapeHtml(String(n));
}

function formatEndpoint(endpoint) {
    return escapeHtml(endpoint || 'N/A');
}

function formatGPU(gpuName, gpuDevice) {
    if (!gpuName) return 'N/A';
    const device = gpuDevice || 'N/A';
    return `${escapeHtml(gpuName)} (${escapeHtml(device)})`;
}

function formatTimestamp(timestamp) {
    if (!timestamp) return 'N/A';
    try {
        const date = new Date(timestamp);
        return escapeHtml(aitbcFmt.date(date));
    } catch (e) {
        return escapeHtml(timestamp);
    }
}

function setupFilterButtons() {
    const filterButtons = document.querySelectorAll('.filter-btn');
    filterButtons.forEach(button => {
        button.addEventListener('click', function() {
            // Remove active class from all buttons
            filterButtons.forEach(btn => btn.classList.remove('active'));
            // Add active class to clicked button
            this.classList.add('active');
            // Update filter
            currentFilter = this.dataset.filter;
            renderOffers();
        });
    });

    const statusFilter = document.getElementById('status-filter');
    if (statusFilter) {
        statusFilter.addEventListener('change', function() {
            currentStatusFilter = this.value;
            renderOffers();
        });
    }
}

function updateTimestamp() {
    const now = new Date();
    document.getElementById('last-updated').textContent = `Last updated: ${aitbcFmt.date(now)}`;
}

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', function() {
    fetchOffers();
    setupFilterButtons();
    updateTimestamp();

    const confirmedToggle = document.getElementById('confirmed-only-toggle');
    if (confirmedToggle) {
        confirmedToggle.addEventListener('change', function() {
            confirmedOnly = this.checked;
            renderOffers();
        });
    }

    // Auto-refresh every 30 seconds
    setInterval(fetchOffers, 30000);
    setInterval(updateTimestamp, 30000);
    setInterval(fetchNetworkStats, 30000);
    fetchNetworkStats();
});

// Fetch and display provider reputation
async function fetchReputation(providerId, elementId) {
    if (!providerId) return;
    try {
        const response = await fetch(`/explorer-api/api/analytics/provider-reputation/${encodeURIComponent(providerId)}?chain_id=${window.AITBC_CONFIG.chainId}`);
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const data = await response.json();
        const el = document.getElementById(elementId);
        if (el) {
            const scoreEl = el.querySelector('.rep-score');
            const levelEl = el.querySelector('.rep-level');
            if (scoreEl) scoreEl.textContent = data.score;
            if (levelEl) {
                levelEl.textContent = data.level;
                levelEl.className = 'rep-level rep-' + data.level.toLowerCase();
            }
            el.title = `${data.transactions} transactions, ${data.days_active} days active, ${data.total_volume} AIT volume`;
        }
    } catch (error) {
        console.error('Error fetching reputation:', error);
        const el = document.getElementById(elementId);
        if (el) el.title = 'reputation unavailable';
    }
}

function loadReputations() {
    document.querySelectorAll('.reputation-badge[data-provider]').forEach(el => {
        const providerId = el.getAttribute('data-provider');
        if (providerId) {
            fetchReputation(providerId, el.id);
        }
    });
}

// Fetch network stats — per-cell last-good: a failed read leaves every
// cell that ever answered showing its number with a "last read" note;
// only never-answered cells go Unavailable.
const NETWORK_STAT_CELLS = ['stat-total-ait', 'stat-transfer-volume', 'stat-active-offers', 'stat-unique-nodes', 'stat-unique-providers', 'stat-total-txs'];
async function fetchNetworkStats() {
    const r = await readJson(`/explorer-api/api/analytics/network-stats?chain_id=${window.AITBC_CONFIG.chainId}`);
    const data = r.data;
    // Every cell must be a real number — a partial reply is a failure,
    // not a partial table.
    const vals = r.ok && data ? [data.total_ait, data.transfer_volume_ait, data.active_offers, data.unique_nodes, data.unique_providers, data.total_transactions] : null;
    const bad = !vals || vals.some(v => v == null || !isFinite(Number(v)));
    const reason = bad ? (r.ok ? 'reply was not the expected shape' : (r.err || `HTTP ${r.status}`)) : '';
    NETWORK_STAT_CELLS.forEach((id, i) => {
        if (bad) {
            setStatFailed(id, reason);
        } else {
            setStatGood(id, vals[i]);
        }
    });
}
