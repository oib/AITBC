/**
 * Shared dashboard logic for AITBC customer and shop web dashboards.
 *
 * Two data tiers:
 *  - Anonymous: network-wide public data (market service, explorer analytics,
 *    public RPC). Everything renders without credentials.
 *  - Operator credential: an optional miner API key or auth JWT pasted into
 *    the credential field unlocks the per-miner/per-customer coordinator
 *    views through the existing auth middleware. The page detects which
 *    header to send by credential shape (JWTs start with "eyJ" and have
 *    three dot-separated segments; anything else is sent as X-Api-Key).
 *
 * All panels degrade gracefully when a service is down or a credential is
 * rejected.
 */

const AITBC = window.AITBC_CONFIG || { chainId: 'ait-hub.aitbc.bubuit.net', explorerApiUrl: '/explorer-api' };

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// ---------- Operator credential ----------

const CRED_KEY = 'aitbc_credential';
let lastAuthRejected = false;

function getCredential() {
    try { return sessionStorage.getItem(CRED_KEY) || ''; } catch (e) { return ''; }
}

function storeCredential(v) {
    try {
        if (v) sessionStorage.setItem(CRED_KEY, v); else sessionStorage.removeItem(CRED_KEY);
    } catch (e) { /* storage unavailable */ }
}

function authHeaders() {
    const cred = getCredential();
    if (!cred) return {};
    if (cred.startsWith('eyJ') && cred.split('.').length === 3) {
        return { 'Authorization': 'Bearer ' + cred };
    }
    return { 'X-Api-Key': cred };
}

function credentialLabel() {
    const cred = getCredential();
    if (!cred) return '';
    return (cred.startsWith('eyJ') && cred.split('.').length === 3) ? 'auth token' : 'miner API key';
}

function refreshCredentialStatus() {
    const el = document.getElementById('cred-status');
    if (!el) return;
    if (!getCredential()) {
        el.textContent = 'No credential — showing public network data.';
    } else if (lastAuthRejected) {
        el.textContent = 'Credential rejected by the coordinator — check the key/token. Public data shown where available.';
    } else {
        el.textContent = `Credential active (${credentialLabel()}).`;
    }
}

function applyCredential(inputId) {
    const el = document.getElementById(inputId);
    storeCredential(el ? el.value.trim() : '');
    reloadCurrentDashboard();
}

function clearCredential(inputId) {
    const el = document.getElementById(inputId);
    if (el) el.value = '';
    storeCredential('');
    reloadCurrentDashboard();
}

function reloadCurrentDashboard() {
    lastAuthRejected = false;
    refreshCredentialStatus();
    if (document.getElementById('cust-jobs-table')) loadCustomerDashboard();
    if (document.getElementById('shop-jobs-table')) loadShopDashboard();
}

// ---------- Fetch helpers ----------

function noteAuth(res) {
    if (res && (res.status === 401 || res.status === 403)) lastAuthRejected = true;
}

async function apiGet(path, opts) {
    const useAuth = opts && opts.auth;
    try {
        const res = await fetch(path, useAuth ? { headers: authHeaders() } : undefined);
        if (useAuth) noteAuth(res);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (e) {
        console.error(`GET ${path} failed:`, e);
        return null;
    }
}

async function apiPost(path, body, opts) {
    const useAuth = opts && opts.auth;
    const headers = { 'Content-Type': 'application/json', ...(useAuth ? authHeaders() : {}) };
    try {
        const res = await fetch(path, { method: 'POST', headers: headers, body: JSON.stringify(body || {}) });
        if (useAuth) noteAuth(res);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (e) {
        console.error(`POST ${path} failed:`, e);
        return null;
    }
}

async function apiPostOrGet(path, params, opts) {
    // The coordinator-api registers the miner job/earnings reads as POST, but a
    // deployment or proxy may expose them GET-only; retry as GET on a 405.
    const useAuth = opts && opts.auth;
    const headers = { 'Content-Type': 'application/json', ...(useAuth ? authHeaders() : {}) };
    try {
        const res = await fetch(path, { method: 'POST', headers: headers, body: JSON.stringify(params || {}) });
        if (useAuth) noteAuth(res);
        if (res.ok) return await res.json();
        if (res.status !== 405) throw new Error(`HTTP ${res.status}`);
    } catch (e) {
        console.error(`POST ${path} failed:`, e);
        return null;
    }
    const query = params ? (path.includes('?') ? '&' : '?') + new URLSearchParams(params).toString() : '';
    return apiGet(path + query, opts);
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
    html += '<tr>' + columns.map(c => `<th style="text-align:left;padding:0.5rem;border-bottom:1px solid var(--border);">${escapeHtml(c.label)}</th>`).join('') + '</tr>';
    rows.forEach(row => {
        html += '<tr>' + columns.map(c => `<td style="padding:0.5rem;border-bottom:1px solid var(--border);">${row[c.key] != null ? escapeHtml(row[c.key]) : 'N/A'}</td>`).join('') + '</tr>';
    });
    html += '</table>';
    container.innerHTML = html;
}

function showAuthHint(containerId, text) {
    const container = document.getElementById(containerId);
    if (container) container.innerHTML = `<p class="endpoint-note">${escapeHtml(text)}</p>`;
}

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function formatAit(units) {
    // The chain settles in compute-units: 1 AIT = 36,000,000 units.
    const ait = Number(units) / 36000000;
    if (!isFinite(ait)) return 'N/A';
    return `${parseFloat(ait.toFixed(8))} AIT`;
}

async function loadAddressRows(limit) {
    // /v1/wallets and /v1/chains/.../balance are admin-gated on the wallet
    // daemon and loopback-only on the public vhost, so a browser can never
    // reach them. Show the public view instead: the most active on-chain
    // addresses from the explorer, with live balances from the public RPC.
    const explorerBase = AITBC.explorerApiUrl || '/explorer-api';
    const data = await apiGet(`${explorerBase}/api/analytics/top-addresses?chain_id=${AITBC.chainId}&limit=${limit}`) || {};
    const entries = Array.isArray(data) ? data : (data.addresses || []);
    const rows = [];
    for (const entry of entries.slice(0, limit)) {
        if (!entry || typeof entry !== 'object') continue;
        const address = entry.address || 'N/A';
        const account = address !== 'N/A' ? await apiGet(`/rpc/account/${encodeURIComponent(address)}`) : null;
        rows.push({
            address: address,
            balance: account && account.balance != null ? formatAit(account.balance) : 'N/A',
            txs: entry.transaction_count != null ? entry.transaction_count : 'N/A',
        });
    }
    return rows;
}

function jobRow(job) {
    const payload = job.payload || {};
    const result = job.result || {};
    const model = result.model || payload.model || (result.result || {}).model || (result.receipt || {}).model || job.service_type || 'N/A';
    return {
        id: job.job_id || job.id || 'N/A',
        state: job.state || 'N/A',
        payment: job.payment_status || 'N/A',
        model: model,
        created: formatDate(job.requested_at || job.created_at),
    };
}

// ---------- Customer dashboard ----------

async function loadCustomerDashboard() {
    refreshCredentialStatus();
    const cred = getCredential();

    // Keyed view: per-customer jobs from the coordinator (admin-or-client JWT).
    // Anonymous view: network-wide market jobs — public by design on the
    // market service and carrying the same state/payment_status fields.
    let jobs = [];
    let scopedView = false;
    if (cred) {
        const jobsData = await apiGet('/v1/jobs?limit=20', { auth: true }) || {};
        jobs = Array.isArray(jobsData) ? jobsData : (jobsData.items || []);
        scopedView = jobs.length > 0 && !lastAuthRejected;
    }
    if (!scopedView) {
        const marketJobs = await apiGet('/v1/market/jobs?limit=20') || [];
        jobs = Array.isArray(marketJobs) ? marketJobs : (marketJobs.items || marketJobs.jobs || []);
    }

    const states = {};
    const payments = {};
    const rows = [];
    for (const job of jobs) {
        if (!job || typeof job !== 'object') continue;
        states[job.state || 'UNKNOWN'] = (states[job.state || 'UNKNOWN'] || 0) + 1;
        payments[job.payment_status || 'unknown'] = (payments[job.payment_status || 'unknown'] || 0) + 1;
        rows.push(jobRow(job));
    }

    setText('cust-total-jobs', jobs.length);
    setText('cust-job-states', Object.entries(states).map(([k, v]) => `${k}: ${v}`).join(', ') || '—');
    setText('cust-payment-statuses', Object.entries(payments).map(([k, v]) => `${k}: ${v}`).join(', ') || '—');
    setText('cust-jobs-scope', scopedView ? 'your account' : 'market-wide');

    renderTable('cust-jobs-table', rows, [
        { label: 'Job ID', key: 'id' },
        { label: 'State', key: 'state' },
        { label: 'Payment', key: 'payment' },
        { label: 'Model', key: 'model' },
        { label: 'Created', key: 'created' },
    ]);

    // Payments are reflected in the job payment_status column. The wallet
    // daemon's routes are admin-gated and loopback-only on the public vhost,
    // so the panel lists the most active on-chain addresses instead.
    const walletRows = await loadAddressRows(10);
    setText('cust-wallet-count', walletRows.length);
    renderTable('cust-wallets-table', walletRows, [
        { label: 'Address', key: 'address' },
        { label: 'Balance', key: 'balance' },
        { label: 'Transactions', key: 'txs' },
    ]);
    refreshCredentialStatus();
}

// ---------- Shop dashboard ----------

function detectMinerId() {
    const fromUrl = new URLSearchParams(window.location.search).get('miner_id');
    if (fromUrl) return fromUrl;
    const field = document.getElementById('shop-miner-input');
    if (field && field.value.trim()) return field.value.trim();
    return '';
}

async function loadShopDashboard() {
    refreshCredentialStatus();
    const minerId = detectMinerId();
    setText('shop-miner-id', minerId || 'all miners');
    const cred = getCredential();
    const canQueryMiner = Boolean(cred && minerId);
    const explorerBase = AITBC.explorerApiUrl || '/explorer-api';

    if (canQueryMiner) {
        const metrics = await apiGet('/v1/monitoring/metrics', { auth: true }) || {};
        const jobsMetrics = metrics.jobs || {};
        const minersMetrics = metrics.miners || {};

        setText('shop-network-jobs', jobsMetrics.total != null ? jobsMetrics.total : '—');
        setText('shop-network-completed', jobsMetrics.completed != null ? jobsMetrics.completed : '—');
        setText('shop-network-pending', jobsMetrics.pending != null ? jobsMetrics.pending : '—');
        setText('shop-network-failed', jobsMetrics.failed != null ? jobsMetrics.failed : '—');
        setText('shop-miners-online', minersMetrics.online != null ? `${minersMetrics.online} / ${minersMetrics.total}` : '—');

        const jobsResp = await apiPostOrGet(`/v1/miners/${encodeURIComponent(minerId)}/jobs?limit=20`, {}, { auth: true }) || {};
        const assignedJobs = Array.isArray(jobsResp) ? jobsResp : (jobsResp.jobs || jobsResp.items || []);
        const jobRows = assignedJobs.map(jobRow);
        setText('shop-jobs-scope', `${jobRows.length} jobs — ${minerId}`);
        renderTable('shop-jobs-table', jobRows, [
            { label: 'Job ID', key: 'id' },
            { label: 'State', key: 'state' },
            { label: 'Payment', key: 'payment' },
            { label: 'Model', key: 'model' },
            { label: 'Created', key: 'created' },
        ]);

        const earnings = await apiPostOrGet(`/v1/miners/${encodeURIComponent(minerId)}/earnings`, {}, { auth: true }) || {};
        setText('shop-earnings-total', earnings.total_earnings != null ? earnings.total_earnings : 'N/A');
        setText('shop-earnings-paid', earnings.paid_earnings != null ? earnings.paid_earnings : 'N/A');
        setText('shop-earnings-pending', earnings.pending_earnings != null ? earnings.pending_earnings : 'N/A');
    } else {
        // Public network view: state counts over the open market-jobs feed plus
        // the explorer's network analytics — no credential needed.
        const marketJobs = await apiGet('/v1/market/jobs?limit=100');
        const jobs = Array.isArray(marketJobs) ? marketJobs : (marketJobs && (marketJobs.items || marketJobs.jobs)) || [];
        const stats = await apiGet(`${explorerBase}/api/analytics/network-stats?chain_id=${encodeURIComponent(AITBC.chainId)}`) || {};

        const pending = jobs.filter(j => ['QUEUED', 'ASSIGNED', 'RUNNING'].includes(j.state)).length;
        const completed = jobs.filter(j => j.state === 'COMPLETED').length;
        const failed = jobs.filter(j => j.state === 'FAILED').length;
        setText('shop-network-jobs', jobs.length);
        setText('shop-network-completed', completed);
        setText('shop-network-pending', pending);
        setText('shop-network-failed', failed);
        setText('shop-miners-online', stats.unique_providers != null ? stats.unique_providers : '—');

        setText('shop-earnings-total', '—');
        setText('shop-earnings-paid', '—');
        setText('shop-earnings-pending', '—');
        setText('shop-jobs-scope', cred ? 'awaiting miner ID' : 'credential required');
        showAuthHint('shop-jobs-table',
            cred ? 'Enter your miner ID above to load assigned jobs and earnings.'
                 : 'Public view: paste a miner API key and miner ID above to load assigned jobs and earnings.');
    }

    // GPUs: the coordinator's public gpu list carries miner_id, so it serves
    // both the anonymous view (all registered GPUs) and a miner-scoped view.
    const gpuData = await apiGet('/v1/market/gpu/list') || [];
    const allGpus = Array.isArray(gpuData) ? gpuData.filter(g => g && typeof g === 'object') : [];
    const gpus = minerId ? allGpus.filter(g => g.miner_id === minerId || (g.miner_id || '').includes(minerId)) : allGpus;
    setText('shop-gpu-count', gpus.length);
    renderTable('shop-gpus-table', gpus.map(g => ({
        name: g.model || g.name || 'N/A',
        device: g.id || g.uuid || g.device || g.device_id || 'N/A',
        memory: g.memory_gb != null ? `${g.memory_gb} GB` : (g.memory || g.memory_total || 'N/A'),
        status: g.status || 'detected',
    })), [
        { label: 'GPU', key: 'name' },
        { label: 'Device', key: 'device' },
        { label: 'Memory', key: 'memory' },
        { label: 'Status', key: 'status' },
    ]);

    const offersData = await apiGet('/v1/market/offer?limit=20') || {};
    const allOffers = Array.isArray(offersData) ? offersData : (offersData.offers || []);
    const shopOffers = minerId
        ? allOffers.filter(o => (o.node_id || o.provider_address || '').includes(minerId))
        : allOffers;
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

    const walletRows = await loadAddressRows(5);
    setText('shop-wallet-count', walletRows.length);
    renderTable('shop-wallets-table', walletRows, [
        { label: 'Address', key: 'address' },
        { label: 'Balance', key: 'balance' },
        { label: 'Transactions', key: 'txs' },
    ]);
    refreshCredentialStatus();
}
