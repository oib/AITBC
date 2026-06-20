let allOffers = [];
let currentFilter = 'all';
let currentStatusFilter = 'all';
let confirmedOnly = false;

async function fetchOffers() {
    try {
        // Build query parameters based on current filters
        const params = new URLSearchParams();
        if (currentFilter !== 'all') {
            params.append('service_type', currentFilter);
        }
        if (currentStatusFilter !== 'all') {
            params.append('status', currentStatusFilter);
        }
        
        const url = `/v1/marketplace/offer?${params.toString()}`;
        const response = await fetch(url);
        const data = await response.json();

        if (data.offers && Array.isArray(data.offers)) {
            allOffers = data.offers;
            updateOfferCount();
            renderOffers();
        } else {
            throw new Error('Invalid response format');
        }
    } catch (error) {
        console.error('Error fetching offers:', error);
        document.getElementById('offers-container').innerHTML = '<p class="error">Failed to load marketplace offers</p>';
        document.getElementById('offer-count').textContent = 'Error loading offers';
    }
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

    if (filteredOffers.length === 0) {
        container.innerHTML = `
            <div class="no-offers">
                <div class="no-offers-icon">📦</div>
                <p>No marketplace offers found matching your filters.</p>
                <p>Try adjusting your filters or check back later.</p>
            </div>
        `;
        return;
    }

    let html = '';
    filteredOffers.forEach(offer => {
        html += createOfferCard(offer);
    });

    container.innerHTML = html;
    updateOfferCount();
    loadReputations();
}

function createOfferCard(offer) {
    const statusClass = offer.status === 'active' ? 'active' : 'inactive';
    const statusText = offer.status ? offer.status.charAt(0).toUpperCase() + offer.status.slice(1) : 'Unknown';

    const ratingStars = offer.avg_rating ? '★'.repeat(Math.round(offer.avg_rating)) : 'N/A';
    const ratingCount = offer.rating_count || 0;
    const providerId = offer.provider_address || offer.node_id || '';
    
    const registeredDate = offer.registered_at ? new Date(offer.registered_at).toLocaleDateString() : 'N/A';
    const updatedDate = offer.updated_at ? new Date(offer.updated_at).toLocaleDateString() : 'N/A';
    
    // Blockchain verification information
    const isConfirmed = offer.confirmed === true;
    const confirmationBadge = isConfirmed 
        ? `<span class="blockchain-confirmed">✓ Confirmed in Block #${offer.block_height}</span>`
        : `<span class="blockchain-pending">⏳ Pending (Not on blockchain)</span>`;
    
    const blockInfo = isConfirmed ? `
        <div class="blockchain-info">
            <div class="blockchain-detail">
                <span class="blockchain-label">Block Height:</span>
                <span class="blockchain-value">${offer.block_height}</span>
            </div>
            <div class="blockchain-detail">
                <span class="blockchain-label">Block Hash:</span>
                <span class="blockchain-value">${formatHash(offer.block_hash)}</span>
            </div>
            <div class="blockchain-detail">
                <span class="blockchain-label">Transaction Hash:</span>
                <span class="blockchain-value">${formatHash(offer.tx_hash)}</span>
            </div>
            <div class="blockchain-detail">
                <span class="blockchain-label">Block Time:</span>
                <span class="blockchain-value">${offer.block_timestamp ? new Date(offer.block_timestamp).toLocaleString() : 'N/A'}</span>
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
                <div class="offer-status ${statusClass}">${statusText}</div>
            </div>
            
            <div class="blockchain-status">
                ${confirmationBadge}
            </div>
            <div class="reputation-badge" data-provider="${providerId}" id="rep-${offer.plugin_id || offer.id || Math.random().toString(36).slice(2)}">
                <span class="rep-score">--</span>
                <span class="rep-level">Loading...</span>
            </div>

            <div class="offer-description">
                ${offer.description || 'No description available'}
            </div>
            
            <div class="offer-details">
                <div class="offer-detail">
                    <div class="offer-detail-label">Service Type</div>
                    <div class="offer-detail-value">${offer.service_type || 'N/A'}</div>
                </div>
                <div class="offer-detail">
                    <div class="offer-detail-label">Model</div>
                    <div class="offer-detail-value">${offer.model || 'N/A'}</div>
                </div>
                <div class="offer-detail">
                    <div class="offer-detail-label">Price</div>
                    <div class="offer-detail-value">${offer.price || 0} ${offer.price_unit || 'units'}</div>
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
                    <span class="offer-list-value">${offer.node_id || 'N/A'}</span>
                </div>
                <div class="offer-list-item">
                    <span class="offer-list-label">Plugin ID:</span>
                    <span class="offer-list-value">${formatHash(offer.plugin_id)}</span>
                </div>
                <div class="offer-list-item">
                    <span class="offer-list-label">Block Height:</span>
                    <span class="offer-list-value">${offer.block_height || 'N/A'}</span>
                </div>
                <div class="offer-list-item">
                    <span class="offer-list-label">Block Hash:</span>
                    <span class="offer-list-value">${formatHash(offer.block_hash)}</span>
                </div>
                <div class="offer-list-item">
                    <span class="offer-list-label">TX Hash:</span>
                    <span class="offer-list-value">${formatHash(offer.tx_hash)}</span>
                </div>
                <div class="offer-list-item">
                    <span class="offer-list-label">Proposer:</span>
                    <span class="offer-list-value">${formatAddress(offer.block_proposer)}</span>
                </div>
                <div class="offer-list-item">
                    <span class="offer-list-label">Block Time:</span>
                    <span class="offer-list-value">${formatTimestamp(offer.block_timestamp)}</span>
                </div>
            </div>
            
            <div class="offer-meta">
                <div class="offer-rating">
                    <span class="offer-rating-value">${ratingStars}</span>
                    <span>(${ratingCount} reviews)</span>
                </div>
                <div>
                    <span>Registered: ${registeredDate}</span>
                    <span style="margin-left: 1rem;">Updated: ${updatedDate}</span>
                </div>
            </div>
        </div>
    `;
}

function formatServiceTitle(offer) {
    const serviceType = offer.service_type || 'Unknown Service';
    const model = offer.model || '';
    return model ? `${serviceType} - ${model}` : serviceType;
}

function formatAddress(address) {
    return address || 'N/A';
}

function formatHash(hash) {
    return hash || 'N/A';
}

function formatEndpoint(endpoint) {
    return endpoint || 'N/A';
}

function formatGPU(gpuName, gpuDevice) {
    if (!gpuName) return 'N/A';
    const device = gpuDevice || 'N/A';
    return `${gpuName} (${device})`;
}

function formatTimestamp(timestamp) {
    if (!timestamp) return 'N/A';
    try {
        const date = new Date(timestamp);
        return date.toLocaleString();
    } catch (e) {
        return timestamp;
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
    document.getElementById('last-updated').textContent = `Last updated: ${now.toLocaleString()}`;
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
    setInterval(checkServiceHealth, 30000);
    setInterval(fetchNetworkStats, 30000);
    checkServiceHealth();
    fetchNetworkStats();
});

// Fetch and display provider reputation
async function fetchReputation(providerId, elementId) {
    if (!providerId) return;
    try {
        const response = await fetch(`/api/analytics/provider-reputation/${encodeURIComponent(providerId)}?chain_id=ait-hub.aitbc.bubuit.net`);
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

// Service health check
async function checkServiceHealth() {
    const services = [
        { name: 'marketplace', url: '/v1/marketplace/status' },
        { name: 'explorer', url: '/api/chain/head' },
        { name: 'coordinator', url: '/v1/explorer/status' },
    ];

    for (const svc of services) {
        const start = performance.now();
        try {
            const response = await fetch(svc.url, { method: 'GET' });
            const latency = Math.round(performance.now() - start);
            const up = response.ok;
            updateHealthItem(svc.name, up, latency);
        } catch (e) {
            updateHealthItem(svc.name, false, 0);
        }
    }
}

function updateHealthItem(name, up, latency) {
    const item = document.querySelector(`.health-item[data-service="${name}"]`);
    if (!item) return;
    const statusEl = item.querySelector('.health-status');
    const latencyEl = item.querySelector('.health-latency');
    statusEl.className = 'health-status ' + (up ? 'up' : 'down');
    latencyEl.textContent = up ? `${latency}ms` : 'DOWN';
}

// Fetch network stats
async function fetchNetworkStats() {
    try {
        const response = await fetch('/api/analytics/network-stats?chain_id=ait-hub.aitbc.bubuit.net');
        const data = await response.json();
        document.getElementById('stat-total-ait').textContent = data.total_ait.toLocaleString();
        document.getElementById('stat-active-offers').textContent = data.active_offers.toLocaleString();
        document.getElementById('stat-unique-nodes').textContent = data.unique_nodes.toLocaleString();
        document.getElementById('stat-unique-providers').textContent = data.unique_providers.toLocaleString();
        document.getElementById('stat-total-txs').textContent = data.total_transactions.toLocaleString();
    } catch (error) {
        console.error('Error fetching network stats:', error);
    }
}