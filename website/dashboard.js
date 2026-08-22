/**
 * Shared dashboard logic for AITBC customer and shop web dashboards.
 *
 * Calls live coordinator, marketplace, and wallet endpoints via the nginx
 * proxy and degrades gracefully when a service is down.
 */

const AITBC = window.AITBC_CONFIG || { chainId: 'ait-hub.aitbc.bubuit.net' };

async function apiGet(path) {
    try {
        const res = await fetch(path);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (e) {
        console.error(`GET ${path} failed:`, e);
        return null;
    }
}

async function apiPost(path, body) {
    try {
        const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (e) {
        console.error(`POST ${path} failed:`, e);
        return null;
    }
}

function formatDate(ts) {
    if (!ts) return 'N/A';
    return new Date(ts).toISOString().slice(0, 19).replace('T', ' ');
}

function renderTable(containerId, rows, columns) {
    const container = document.getElementById(containerId);
    if (!rows || rows.length === 0) {
        container.innerHTML = '<p class="endpoint-note">No data available.</p>';
        return;
    }
    let html = '<table class="block-list-table">';
    html += '<tr>' + columns.map(c => `<th style="text-align:left;padding:0.5rem;border-bottom:1px solid var(--border);">${c.label}</th>`).join('') + '</tr>';
    rows.forEach(row => {
        html += '<tr>' + columns.map(c => `<td style="padding:0.5rem;border-bottom:1px solid var(--border);">${row[c.key] != null ? row[c.key] : 'N/A'}</td>`).join('') + '</tr>';
    });
    html += '</table>';
    container.innerHTML = html;
}

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

// ---------- Customer dashboard ----------

async function loadCustomerDashboard() {
    const jobsData = await apiGet('/v1/jobs?limit=20') || {};
    const jobs = Array.isArray(jobsData) ? jobsData : (jobsData.items || []);

    const states = {};
    const payments = {};
    const rows = [];
    for (const job of jobs) {
        if (!job || typeof job !== 'object') continue;
        states[job.state || 'UNKNOWN'] = (states[job.state || 'UNKNOWN'] || 0) + 1;
        payments[job.payment_status || 'unknown'] = (payments[job.payment_status || 'unknown'] || 0) + 1;

        const payload = job.payload || {};
        const result = job.result || {};
        const model = result.model || payload.model || (result.result || {}).model || (result.receipt || {}).model || 'N/A';
        rows.push({
            id: job.job_id || job.id || 'N/A',
            state: job.state || 'N/A',
            payment: job.payment_status || 'N/A',
            model: model,
            created: formatDate(job.requested_at || job.created_at),
        });
    }

    setText('cust-total-jobs', jobs.length);
    setText('cust-job-states', Object.entries(states).map(([k, v]) => `${k}: ${v}`).join(', ') || '—');
    setText('cust-payment-statuses', Object.entries(payments).map(([k, v]) => `${k}: ${v}`).join(', ') || '—');

    renderTable('cust-jobs-table', rows, [
        { label: 'Job ID', key: 'id' },
        { label: 'State', key: 'state' },
        { label: 'Payment', key: 'payment' },
        { label: 'Model', key: 'model' },
        { label: 'Created', key: 'created' },
    ]);

    // Payments are reflected in the job payment_status column and wallet daemon.
    // Wallet data may not be reachable from the browser if not proxied.
    const walletData = await apiGet('/v1/wallets') || {};
    const wallets = Array.isArray(walletData) ? walletData : (walletData.items || []);
    const walletRows = [];
    for (const w of wallets.slice(0, 10)) {
        if (!w || typeof w !== 'object') continue;
        const walletId = w.wallet_id || w.id || 'N/A';
        const bal = await apiGet(`/v1/chains/${AITBC.chainId}/wallets/${walletId}/balance`) || {};
        walletRows.push({
            wallet: walletId,
            address: w.address || (w.metadata || {}).address || 'N/A',
            balance: bal.balance != null ? `${bal.balance} AIT` : 'N/A',
        });
    }
    setText('cust-wallet-count', walletRows.length);
    renderTable('cust-wallets-table', walletRows, [
        { label: 'Wallet', key: 'wallet' },
        { label: 'Address', key: 'address' },
        { label: 'Balance', key: 'balance' },
    ]);
}

// ---------- Shop dashboard ----------

function detectMinerId() {
    const fromUrl = new URLSearchParams(window.location.search).get('miner_id');
    return fromUrl || window.location.hostname || 'unknown';
}

async function loadShopDashboard() {
    const minerId = detectMinerId();
    setText('shop-miner-id', minerId);

    const metrics = await apiGet('/v1/monitoring/metrics') || {};
    const jobsMetrics = metrics.jobs || {};
    const minersMetrics = metrics.miners || {};

    setText('shop-network-jobs', jobsMetrics.total || 0);
    setText('shop-network-completed', jobsMetrics.completed || 0);
    setText('shop-network-pending', jobsMetrics.pending || 0);
    setText('shop-network-failed', jobsMetrics.failed || 0);
    setText('shop-miners-total', minersMetrics.total || 0);
    setText('shop-miners-online', minersMetrics.online || 0);

    const jobsResp = await apiPost(`/v1/miners/${encodeURIComponent(minerId)}/jobs`, { limit: 20 }) || {};
    const assignedJobs = Array.isArray(jobsResp) ? jobsResp : (jobsResp.jobs || jobsResp.items || []);
    const jobRows = assignedJobs.map(job => ({
        id: job.job_id || job.id || 'N/A',
        state: job.state || 'N/A',
        payment: job.payment_status || 'N/A',
        model: (job.result || {}).model || (job.payload || {}).model || 'N/A',
        created: formatDate(job.requested_at || job.created_at),
    }));
    setText('shop-assigned-jobs', jobRows.length);
    renderTable('shop-jobs-table', jobRows, [
        { label: 'Job ID', key: 'id' },
        { label: 'State', key: 'state' },
        { label: 'Payment', key: 'payment' },
        { label: 'Model', key: 'model' },
        { label: 'Created', key: 'created' },
    ]);

    const earnings = await apiPost(`/v1/miners/${encodeURIComponent(minerId)}/earnings`) || {};
    setText('shop-earnings-total', earnings.total_earnings != null ? earnings.total_earnings : 'N/A');
    setText('shop-earnings-paid', earnings.paid_earnings != null ? earnings.paid_earnings : 'N/A');
    setText('shop-earnings-pending', earnings.pending_earnings != null ? earnings.pending_earnings : 'N/A');

    const gpuData = await apiGet('/v1/gpu/discover') || {};
    const gpus = Array.isArray(gpuData) ? gpuData : (gpuData.gpus || []);
    setText('shop-gpu-count', gpus.length);
    renderTable('shop-gpus-table', gpus.map(g => ({
        name: g.name || g.model || 'N/A',
        device: g.device || g.device_id || 'N/A',
        memory: g.memory || g.memory_total || 'N/A',
        status: g.status || 'N/A',
    })), [
        { label: 'GPU', key: 'name' },
        { label: 'Device', key: 'device' },
        { label: 'Memory', key: 'memory' },
        { label: 'Status', key: 'status' },
    ]);

    const offersData = await apiGet('/v1/marketplace/offer?limit=20') || {};
    const allOffers = Array.isArray(offersData) ? offersData : (offersData.offers || []);
    const shopOffers = allOffers.filter(o => (o.node_id || o.provider_address || '').includes(minerId));
    setText('shop-offer-count', shopOffers.length);
    renderTable('shop-offers-table', shopOffers.map(o => ({
        plugin: o.plugin_id || 'N/A',
        model: o.model || 'N/A',
        price: `${o.price || 0} ${o.price_unit || 'units'}`,
        status: o.status || 'unknown',
        rating: `${(o.avg_rating || 0).toFixed(1)} (${o.rating_count || 0})`,
    })), [
        { label: 'Plugin', key: 'plugin' },
        { label: 'Model', key: 'model' },
        { label: 'Price', key: 'price' },
        { label: 'Status', key: 'status' },
        { label: 'Rating', key: 'rating' },
    ]);

    const walletData = await apiGet('/v1/wallets') || {};
    const wallets = Array.isArray(walletData) ? walletData : (walletData.items || []);
    const walletRows = [];
    for (const w of wallets.slice(0, 5)) {
        if (!w || typeof w !== 'object') continue;
        const walletId = w.wallet_id || w.id || 'N/A';
        const bal = await apiGet(`/v1/chains/${AITBC.chainId}/wallets/${walletId}/balance`) || {};
        walletRows.push({
            wallet: walletId,
            address: w.address || (w.metadata || {}).address || 'N/A',
            balance: bal.balance != null ? `${bal.balance} AIT` : 'N/A',
        });
    }
    setText('shop-wallet-count', walletRows.length);
    renderTable('shop-wallets-table', walletRows, [
        { label: 'Wallet', key: 'wallet' },
        { label: 'Address', key: 'address' },
        { label: 'Balance', key: 'balance' },
    ]);
}
