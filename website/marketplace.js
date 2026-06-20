let allOffers = [];
let currentFilter = 'all';
let currentStatusFilter = 'all';

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
        return matchesServiceType && matchesStatus;
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
}

function createOfferCard(offer) {
    const statusClass = offer.status === 'active' ? 'active' : 'inactive';
    const statusText = offer.status ? offer.status.charAt(0).toUpperCase() + offer.status.slice(1) : 'Unknown';
    
    const ratingStars = offer.avg_rating ? '★'.repeat(Math.round(offer.avg_rating)) : 'N/A';
    const ratingCount = offer.rating_count || 0;
    
    const registeredDate = offer.registered_at ? new Date(offer.registered_at).toLocaleDateString() : 'N/A';
    const updatedDate = offer.updated_at ? new Date(offer.updated_at).toLocaleDateString() : 'N/A';

    return `
        <div class="offer-card">
            <div class="offer-header">
                <div class="offer-title">${formatServiceTitle(offer)}</div>
                <div class="offer-status ${statusClass}">${statusText}</div>
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
                    <div class="offer-detail-label">Provider</div>
                    <div class="offer-detail-value">${formatAddress(offer.provider_address)}</div>
                </div>
                <div class="offer-detail">
                    <div class="offer-detail-label">Node ID</div>
                    <div class="offer-detail-value">${offer.node_id || 'N/A'}</div>
                </div>
                <div class="offer-detail">
                    <div class="offer-detail-label">GPU</div>
                    <div class="offer-detail-value">${offer.gpu_name || 'N/A'} (${offer.gpu_device || 'N/A'})</div>
                </div>
                <div class="offer-detail">
                    <div class="offer-detail-label">Endpoint</div>
                    <div class="offer-detail-value">${formatEndpoint(offer.public_endpoint || offer.endpoint)}</div>
                </div>
                <div class="offer-detail">
                    <div class="offer-detail-label">Plugin ID</div>
                    <div class="offer-detail-value">${offer.plugin_id || 'N/A'}</div>
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
    if (!address) return 'N/A';
    if (address.length <= 16) return address;
    return `${address.substring(0, 8)}...${address.substring(address.length - 8)}`;
}

function formatEndpoint(endpoint) {
    if (!endpoint) return 'N/A';
    if (endpoint.length <= 30) return endpoint;
    return `${endpoint.substring(0, 20)}...`;
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
    
    // Auto-refresh every 30 seconds
    setInterval(fetchOffers, 30000);
    setInterval(updateTimestamp, 30000);
});