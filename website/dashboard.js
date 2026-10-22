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

const AITBC = window.AITBC_CONFIG || { chainId: 'bc-2', explorerApiUrl: '/explorer-api' };

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// ---------- Operator credential ----------

const CRED_KEY = 'aitbc_credential';
let lastAuthStatus = 0;  // 0 = none; else the 401/403 the coordinator answered

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
    } else if (lastAuthStatus) {
        el.textContent = `Credential rejected (HTTP ${lastAuthStatus}) — check the key/token, then Clear and Apply.`;
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
    lastAuthStatus = 0;
    refreshCredentialStatus();
    if (document.getElementById('cust-jobs-table')) loadCustomerDashboard();
    if (document.getElementById('shop-jobs-table')) loadShopDashboard();
}

// ---------- Fetch helpers ----------

function noteAuth(res) {
    if (res && (res.status === 401 || res.status === 403)) lastAuthStatus = res.status;
}

// Every read returns {ok, status, data, err}. ok means HTTP-ok AND parseable;
// err names the failure plainly ("HTTP 503", "network request failed",
// "reply was not readable", "Credential rejected (HTTP 401)") — a failed read
// is never a silent null that a table could render as an empty list.
function readResult(useAuth, res) {
    if (useAuth && (res.status === 401 || res.status === 403)) {
        lastAuthStatus = res.status;
        return { ok: false, status: res.status, err: `Credential rejected (HTTP ${res.status})` };
    }
    if (!res.ok) return { ok: false, status: res.status, err: `HTTP ${res.status}` };
    return null;  // ok — caller parses
}

async function readApi(path, opts) {
    const useAuth = opts && opts.auth;
    let res;
    try {
        res = await fetch(path, useAuth ? { headers: authHeaders() } : undefined);
    } catch (e) {
        console.error(`GET ${path} failed:`, e);
        return { ok: false, status: 0, err: 'network request failed' };
    }
    const bad = readResult(useAuth, res);
    if (bad) return bad;
    try {
        return { ok: true, status: res.status, data: await res.json() };
    } catch (e) {
        return { ok: false, status: res.status, err: 'reply was not readable' };
    }
}

async function readApiPostOrGet(path, params, opts) {
    // The coordinator-api registers the miner job/earnings reads as POST, but a
    // deployment or proxy may expose them GET-only; retry as GET on a 405.
    const useAuth = opts && opts.auth;
    const headers = { 'Content-Type': 'application/json', ...(useAuth ? authHeaders() : {}) };
    let res;
    try {
        res = await fetch(path, { method: 'POST', headers: headers, body: JSON.stringify(params || {}) });
    } catch (e) {
        console.error(`POST ${path} failed:`, e);
        return { ok: false, status: 0, err: 'network request failed' };
    }
    if (res.ok) {
        try {
            return { ok: true, status: res.status, data: await res.json() };
        } catch (e) {
            return { ok: false, status: res.status, err: 'reply was not readable' };
        }
    }
    if (res.status !== 405) {
        const bad = readResult(useAuth, res);
        return bad || { ok: false, status: res.status, err: `HTTP ${res.status}` };
    }
    const query = params ? (path.includes('?') ? '&' : '?') + new URLSearchParams(params).toString() : '';
    return readApi(path + query, opts);
}

// An ok reply that lacks the field a panel needs is a shape failure, not a
// proven-empty list. pickList returns the array or null (wrong shape).
function pickList(data, keys) {
    if (Array.isArray(data)) return data;
    if (data && typeof data === 'object') {
        for (const k of keys) if (Array.isArray(data[k])) return data[k];
    }
    return null;
}

function tzLabel(d) {
    // Shared home since WEB-TZ-1: aitbcFmt.zone in status.js is the single
    // source so pages can't drift. The Intl copy below is only the fallback
    // for a page where status.js failed to load.
    if (window.aitbcFmt && typeof window.aitbcFmt.zone === 'function') {
        return window.aitbcFmt.zone(d);
    }
    try {
        const part = new Intl.DateTimeFormat('en', { timeZoneName: 'short' })
            .formatToParts(d).find(p => p.type === 'timeZoneName');
        if (part && part.value) return part.value;
    } catch (e) { /* older engines */ }
    const off = -d.getTimezoneOffset() / 60;
    return 'UTC' + (off >= 0 ? '+' : '') + off;
}

function formatDate(ts) {
    if (!ts) return 'N/A';
    const d = new Date(ts);
    if (isNaN(d.getTime())) return 'N/A';
    // Site convention (status.js): "YYYY-MM-DD HH:mm" in the viewer's local
    // clock — labelled with the zone so the clock's origin stays unambiguous.
    // status.js loads after this file but is defined by the time rows render;
    // the UTC fallback only covers a page where status.js failed to load.
    const stamp = (window.aitbcFmt && typeof window.aitbcFmt.date === 'function')
        ? window.aitbcFmt.date(ts)
        : d.toISOString().slice(0, 16).replace('T', ' ');
    return stamp === '-' ? 'N/A' : `${stamp} ${tzLabel(d)}`;
}

// Machine tokens (settlement_failed, per_audio_min) read as words in the UI.
function humanize(v) {
    return String(v).replace(/_/g, ' ');
}

// A failed read keeps last-good rows when they exist and shows exactly one
// note naming the reason plus a Try again; a rejected credential gets no
// retry — reloading cannot help until the credential changes.
function renderFailure(container, label, reason) {
    if (!container) return;
    const prior = container.querySelector('.dash-note');
    if (prior) prior.remove();
    const stale = container.querySelector('.table-wrap');
    // No last-good table — a first-load "Loading …" placeholder must not
    // stay on screen next to the failure note.
    if (!stale) container.querySelectorAll('.loading, .loading-text').forEach(el => el.remove());
    const p = document.createElement('p');
    p.className = 'endpoint-note dash-note';
    const retry = /^Credential rejected/.test(reason)
        ? ''
        : ' <button type="button" class="bridge-retry dash-retry">Try again</button>';
    p.innerHTML = stale
        ? `Stale — last good ${escapeHtml(label)} shown (${escapeHtml(reason)}).` + retry
        : `${escapeHtml(label)} unavailable: ${escapeHtml(reason)}.` + retry;
    if (stale) container.prepend(p); else container.appendChild(p);
}

// A note that coexists with rendered content (e.g. "credential rejected —
// showing public network data"): written once, removed on next render.
function panelNote(containerId, html) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const prior = container.querySelector('.dash-note');
    if (prior) prior.remove();
    if (!html) return;
    const p = document.createElement('p');
    p.className = 'endpoint-note dash-note';
    p.innerHTML = html;
    container.prepend(p);
}

function renderTable(containerId, rows, columns, failReason, label) {
    const container = document.getElementById(containerId);
    if (failReason) {
        renderFailure(container, label || 'Data', failReason);
        return;
    }
    if (!rows || rows.length === 0) {
        container.innerHTML = '<p class="endpoint-note">No data.</p>';
        return;
    }
    const ariaLabel = label || 'data table';
    let html = `<div class="table-wrap" role="region" tabindex="0" aria-label="${escapeHtml(ariaLabel)}"><table class="block-list-table data-table" aria-label="${escapeHtml(ariaLabel)}">`;
    html += '<tr>' + columns.map(c => `<th scope="col">${escapeHtml(c.label)}</th>`).join('') + '</tr>';
    rows.forEach(row => {
        html += '<tr>' + columns.map(c => {
            const v = row[c.key];
            if (c.html) return `<td>${v != null ? v : 'N/A'}</td>`;
            return `<td>${v != null ? escapeHtml(v) : 'N/A'}</td>`;
        }).join('') + '</tr>';
    });
    html += '</table></div>';
    container.innerHTML = html;
}

/**
 * Per-source status dot. `state` is 'up' (endpoint answered), 'down'
 * (fetch failed / auth rejected), or 'loading' (not queried — e.g. the
 * panel is credential-gated and no credential was supplied).
 */
function setDot(id, state) {
    const el = document.getElementById(id);
    if (el) el.className = `health-status ${state}`;
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
    const r = await readApi(`${explorerBase}/api/analytics/top-addresses?chain_id=${AITBC.chainId}&limit=${limit}`);
    if (!r.ok) return { ok: false, err: r.err };
    const entries = pickList(r.data, ['addresses']);
    if (entries === null) return { ok: false, err: 'reply was not the expected shape' };
    // Balances are independent reads, so fetch them together instead of one
    // after another (was ~limit x round-trip). Promise.all keeps input order;
    // readApi never rejects (failures come back as { ok: false }).
    const picked = entries.slice(0, limit).filter(entry => entry && typeof entry === 'object');
    const accts = await Promise.all(picked.map(entry => {
        const address = entry.address || 'N/A';
        return address !== 'N/A' ? readApi(`/rpc/account/${encodeURIComponent(address)}`) : Promise.resolve({ ok: false });
    }));
    const rows = picked.map((entry, i) => {
        const acct = accts[i];
        return {
            address: entry.address || 'N/A',
            balance: acct.ok && acct.data && acct.data.balance != null ? formatAit(acct.data.balance) : 'N/A',
            txs: entry.transaction_count != null ? entry.transaction_count : 'N/A',
        };
    });
    return { ok: true, rows: rows };
}

function shortHex(v, keep) {
    if (!v || typeof v !== 'string') return null;
    const n = keep || 12;
    return v.length > n ? `${v.slice(0, n)}…` : v;
}

function txLink(hash) {
    if (!hash || typeof hash !== 'string') return null;
    const esc = escapeHtml(hash);
    return `<a href="/tx.html?hash=${encodeURIComponent(esc)}" aria-label="Transaction ${esc}">${escapeHtml(shortHex(hash))}</a> ${aitbcCopyBtn(hash, 'transaction hash')}`;
}

const JOB_COLUMNS = [
    { label: 'Job ID', key: 'id' },
    { label: 'State', key: 'state' },
    { label: 'Payment', key: 'payment' },
    { label: 'Model', key: 'model' },
    { label: 'Escrow', key: 'escrow', html: true },
    { label: 'Settlement Tx', key: 'tx', html: true },
    { label: 'Created', key: 'created' },
];

function jobRow(job) {
    const payload = job.payload || {};
    const result = job.result || {};
    const model = job.model || result.model || payload.model || (result.result || {}).model || (result.receipt || {}).model || job.service_type || 'N/A';
    return {
        id: job.job_id || job.id || 'N/A',
        state: job.state || 'N/A',
        payment: job.payment_status ? humanize(job.payment_status) : 'N/A',
        model: model,
        escrow: job.escrow_contract_id
            ? `<span aria-hidden="true">${escapeHtml(shortHex(job.escrow_contract_id))}</span><span class="visually-hidden">${escapeHtml(job.escrow_contract_id)}</span> ${aitbcCopyBtn(job.escrow_contract_id, 'escrow contract id')}`
            : '—',
        tx: txLink(job.tx_hash || job.refund_tx_hash) || '—',
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
    let jobsFailed = null;   // null | named reason
    let keyedErr = null;     // why the keyed view fell back (null = not tried)
    if (cred) {
        const r = await readApi('/v1/jobs?limit=20', { auth: true });
        if (r.ok) {
            const list = pickList(r.data, ['items', 'jobs']);
            if (list === null) {
                keyedErr = 'reply was not the expected shape';
            } else {
                jobs = list;
                // An approved credential with zero jobs is honestly empty —
                // scope stays "your account"; only failures fall back.
                scopedView = !lastAuthStatus;
            }
        } else {
            keyedErr = r.err;
        }
    }
    if (!scopedView) {
        const r = await readApi('/v1/market/jobs?limit=20');
        if (r.ok) {
            const list = pickList(r.data, ['items', 'jobs']);
            if (list === null) {
                jobsFailed = 'reply was not the expected shape';
            } else {
                jobs = list;
            }
        } else {
            jobsFailed = r.err;
        }
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

    const jobsDot = jobsFailed ? 'down' : 'up';
    setDot('cust-dot-jobs', jobsDot);
    setDot('cust-dot-states', jobsDot);
    setDot('cust-dot-payments', jobsDot);
    setText('cust-total-jobs', jobsFailed ? 'unavailable' : jobs.length);
    setText('cust-job-states', Object.entries(states).map(([k, v]) => `${k}: ${v}`).join(', ') || '—');
    setText('cust-payment-statuses', Object.entries(payments).map(([k, v]) => `${humanize(k)}: ${v}`).join(', ') || '—');
    setText('cust-jobs-scope', scopedView ? 'your account' : 'market-wide');

    renderTable('cust-jobs-table', rows, JOB_COLUMNS, jobsFailed, 'Jobs');
    // When the keyed view failed but public data rendered, say so plainly —
    // a silent fallback would let the market list masquerade as yours.
    if (!jobsFailed && keyedErr) {
        const rejected = /^Credential rejected/.test(keyedErr);
        panelNote('cust-jobs-table', rejected
            ? `${escapeHtml(keyedErr)} — showing public network data. Check the key/token, then Clear and Apply.`
            : `Couldn't load your view (${escapeHtml(keyedErr)}) — showing public network data instead. <button type="button" class="bridge-retry dash-retry">Try again</button>`);
    }

    // Payments are reflected in the job payment_status column. The wallet
    // daemon's routes are admin-gated and loopback-only on the public vhost,
    // so the panel lists the most active on-chain addresses instead.
    const wallets = await loadAddressRows(10);
    setDot('cust-dot-wallets', wallets.ok ? 'up' : 'down');
    setText('cust-wallet-count', wallets.ok ? wallets.rows.length : 'unavailable');
    renderTable('cust-wallets-table', wallets.ok ? wallets.rows : [], [
        { label: 'Address', key: 'address' },
        { label: 'Balance', key: 'balance' },
        { label: 'Transactions', key: 'txs' },
    ], wallets.ok ? null : wallets.err, 'Wallets');
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
    // One note slot per card; every failed read appends its named reason.
    const panelNotes = { stats: [], earnings: [] };

    if (canQueryMiner) {
        const metrics = await readApi('/v1/monitoring/metrics', { auth: true });
        const metricsOk = metrics.ok && metrics.data && typeof metrics.data === 'object';
        const metricsReason = metrics.ok
            ? (metricsOk ? null : 'reply was not the expected shape')
            : metrics.err;
        const jobsMetrics = (metricsOk && metrics.data.jobs) || {};
        const minersMetrics = (metricsOk && metrics.data.miners) || {};
        const metricsDot = metricsReason ? 'down' : 'up';
        setDot('shop-dot-jobs', metricsDot);
        setDot('shop-dot-released', metricsDot);
        setDot('shop-dot-queued', metricsDot);
        setDot('shop-dot-refunded', metricsDot);
        setDot('shop-dot-miners', metricsDot);

        setText('shop-network-jobs', metricsReason ? 'unavailable' : (jobsMetrics.total != null ? jobsMetrics.total : '—'));
        setText('shop-network-released', metricsReason ? 'unavailable' : (jobsMetrics.completed != null ? jobsMetrics.completed : '—'));
        setText('shop-network-queued', metricsReason ? 'unavailable' : (jobsMetrics.pending != null ? jobsMetrics.pending : '—'));
        setText('shop-network-refunded', metricsReason ? 'unavailable' : (jobsMetrics.failed != null ? jobsMetrics.failed : '—'));
        setText('shop-miners-online', metricsReason ? 'unavailable'
            : (minersMetrics.online != null ? `${minersMetrics.online} / ${minersMetrics.total}` : '—'));
        if (metricsReason) panelNotes.stats.push(`Network stats: ${metricsReason}`);

        const jobsR = await readApiPostOrGet(`/v1/miners/${encodeURIComponent(minerId)}/jobs?limit=20`, {}, { auth: true });
        let jobsErr = null;
        let assignedJobs = null;
        if (jobsR.ok) {
            assignedJobs = pickList(jobsR.data, ['jobs', 'items']);
            if (assignedJobs === null) jobsErr = 'reply was not the expected shape';
        } else {
            jobsErr = jobsR.err;
        }
        const jobRows = (assignedJobs || []).map(jobRow);
        setText('shop-jobs-scope', jobsErr ? `unavailable — ${minerId}` : `${jobRows.length} jobs — ${minerId}`);
        renderTable('shop-jobs-table', jobRows, JOB_COLUMNS, jobsErr, 'Jobs');

        const earnings = await readApiPostOrGet(`/v1/miners/${encodeURIComponent(minerId)}/earnings`, {}, { auth: true });
        const earningsOk = earnings.ok && earnings.data && typeof earnings.data === 'object';
        const earningsReason = earnings.ok
            ? (earningsOk ? null : 'reply was not the expected shape')
            : earnings.err;
        setText('shop-earnings-total', earningsReason ? 'unavailable' : (earnings.data.total_earnings != null ? earnings.data.total_earnings : 'N/A'));
        setText('shop-earnings-paid', earningsReason ? 'unavailable' : (earnings.data.paid_earnings != null ? earnings.data.paid_earnings : 'N/A'));
        setText('shop-earnings-pending', earningsReason ? 'unavailable' : (earnings.data.pending_earnings != null ? earnings.data.pending_earnings : 'N/A'));
        if (earningsReason) panelNotes.earnings.push(`Earnings: ${earningsReason}`);
    } else {
        // Public network view: state counts over the open market-jobs feed plus
        // the explorer's network analytics — no credential needed. The market
        // service settles jobs to QUEUED/RELEASED/REFUNDED/CANCELED; counts
        // are over the fetched page only.
        const marketR = await readApi('/v1/market/jobs?limit=100');
        let jobsReason = null;
        let jobs = null;
        if (marketR.ok) {
            jobs = pickList(marketR.data, ['items', 'jobs']);
            if (jobs === null) jobsReason = 'reply was not the expected shape';
        } else {
            jobsReason = marketR.err;
        }
        const jobsDot = jobsReason ? 'down' : 'up';
        setDot('shop-dot-jobs', jobsDot);
        setDot('shop-dot-released', jobsDot);
        setDot('shop-dot-queued', jobsDot);
        setDot('shop-dot-refunded', jobsDot);

        if (jobsReason) {
            // A failed or shapeless feed must not render as real zeros.
            setText('shop-network-jobs', 'unavailable');
            setText('shop-network-released', 'unavailable');
            setText('shop-network-queued', 'unavailable');
            setText('shop-network-refunded', 'unavailable');
            panelNotes.stats.push(`Jobs feed: ${jobsReason}`);
        } else {
            const released = jobs.filter(j => j.state === 'RELEASED').length;
            const queued = jobs.filter(j => j.state === 'QUEUED').length;
            const refunded = jobs.filter(j => j.state === 'REFUNDED' || j.state === 'CANCELED').length;
            setText('shop-network-jobs', `${jobs.length} (latest)`);
            setText('shop-network-released', released);
            setText('shop-network-queued', queued);
            setText('shop-network-refunded', refunded);
        }

        const stats = await readApi(`${explorerBase}/api/analytics/network-stats?chain_id=${encodeURIComponent(AITBC.chainId)}`);
        const statsOk = stats.ok && stats.data && typeof stats.data === 'object';
        setDot('shop-dot-miners', statsOk ? 'up' : 'down');
        if (stats.ok && !statsOk) panelNotes.stats.push('Network stats: reply was not the expected shape');
        if (!stats.ok) panelNotes.stats.push(`Network stats: ${stats.err}`);
        setText('shop-miners-online', statsOk
            ? (stats.data.unique_providers != null ? stats.data.unique_providers : '—')
            : 'unavailable');
        setText('shop-earnings-total', '—');
        setText('shop-earnings-paid', '—');
        setText('shop-earnings-pending', '—');
        setText('shop-jobs-scope', cred ? 'awaiting miner ID' : 'credential required');
        showAuthHint('shop-jobs-table',
            cred ? 'Enter your miner ID above to load assigned jobs and earnings.'
                 : 'Public view: paste a miner API key and miner ID above to load assigned jobs and earnings.');
    }

    // Miner uptime: the pool-hub SLA feed is public and works without a
    // credential whenever a miner ID is entered.
    if (minerId) {
        const sla = await readApi(`/pool-hub/v1/sla/metrics/${encodeURIComponent(minerId)}`);
        if (!sla.ok) {
            setText('shop-miner-uptime', 'unavailable');
            panelNotes.earnings.push(`Miner uptime: ${sla.err}`);
        } else if (!Array.isArray(sla.data)) {
            setText('shop-miner-uptime', 'unavailable');
            panelNotes.earnings.push('Miner uptime: reply was not the expected shape');
        } else {
            const upRows = sla.data.filter(r => r && r.metric_type === 'uptime_pct');
            const latest = upRows.sort((a, b) => String(b.timestamp || '').localeCompare(String(a.timestamp || '')))[0];
            setText('shop-miner-uptime', latest && latest.metric_value != null ? `${latest.metric_value}%` : 'no SLA data');
        }
    } else {
        setText('shop-miner-uptime', 'enter a miner ID');
    }

    // GPUs: the coordinator's public gpu list carries miner_id, so it serves
    // both the anonymous view (all registered GPUs) and a miner-scoped view.
    const gpuR = await readApi('/v1/market/gpu/list');
    let gpuErr = null;
    let allGpus = null;
    if (gpuR.ok) {
        allGpus = Array.isArray(gpuR.data) ? gpuR.data.filter(g => g && typeof g === 'object') : null;
        if (allGpus === null) gpuErr = 'reply was not the expected shape';
    } else {
        gpuErr = gpuR.err;
    }
    const gpus = minerId && allGpus ? allGpus.filter(g => g.miner_id === minerId || (g.miner_id || '').includes(minerId)) : (allGpus || []);
    setDot('shop-dot-gpus', gpuErr ? 'down' : 'up');
    setText('shop-gpu-count', gpuErr ? 'unavailable' : gpus.length);
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
    ], gpuErr, 'GPUs');

    const offersR = await readApi('/v1/market/offer?limit=20');
    let offersErr = null;
    let allOffers = null;
    if (offersR.ok) {
        allOffers = pickList(offersR.data, ['offers']);
        if (allOffers === null) offersErr = 'reply was not the expected shape';
    } else {
        offersErr = offersR.err;
    }
    const shopOffers = minerId && allOffers
        ? allOffers.filter(o => (o.node_id || o.provider_address || '').includes(minerId))
        : (allOffers || []);
    setDot('shop-dot-offers', offersErr ? 'down' : 'up');
    setText('shop-offer-count', offersErr ? 'unavailable' : shopOffers.length);
    renderTable('shop-offers-table', shopOffers.map(o => ({
        plugin: o.plugin_id || 'N/A',
        model: o.model || 'N/A',
        price: `${o.price || 0} ${humanize(o.price_unit || 'units')}`,
        status: o.status || 'unknown',
        rating: `${(o.avg_rating || 0).toFixed(1)} (${o.rating_count || 0})`,
    })), [
        { label: 'Plugin', key: 'plugin' },
        { label: 'Model', key: 'model' },
        { label: 'Price', key: 'price' },
        { label: 'Status', key: 'status' },
        { label: 'Rating', key: 'rating' },
    ], offersErr, 'Offers');

    const shopWallets = await loadAddressRows(5);
    setDot('shop-dot-wallets', shopWallets.ok ? 'up' : 'down');
    setText('shop-wallet-count', shopWallets.ok ? shopWallets.rows.length : 'unavailable');
    renderTable('shop-wallets-table', shopWallets.ok ? shopWallets.rows : [], [
        { label: 'Address', key: 'address' },
        { label: 'Balance', key: 'balance' },
        { label: 'Transactions', key: 'txs' },
    ], shopWallets.ok ? null : shopWallets.err, 'Wallets');
    setText('shop-stats-note', panelNotes.stats.join('; '));
    setText('shop-earnings-note', panelNotes.earnings.join('; '));
    refreshCredentialStatus();
}

// ---------- Init ----------
// The two dashboard pages share this file; each is detected by a page-only
// table id (the same check reloadCurrentDashboard uses). Credential buttons
// carry data-cred-op/data-cred-input instead of inline onclick so the
// pages work under a script-src 'self' CSP.
function bindCredentialButtons() {
    document.querySelectorAll('[data-cred-op]').forEach(btn => {
        btn.addEventListener('click', () => {
            const inputId = btn.getAttribute('data-cred-input');
            if (btn.getAttribute('data-cred-op') === 'apply') applyCredential(inputId);
            else clearCredential(inputId);
        });
    });
}

// Try-again buttons rendered by renderFailure carry .dash-retry.
document.addEventListener('click', ev => {
    if (ev.target && ev.target.closest && ev.target.closest('.dash-retry')) {
        reloadCurrentDashboard();
    }
});

document.addEventListener('DOMContentLoaded', () => {
    bindCredentialButtons();
    if (document.getElementById('cust-jobs-table')) loadCustomerDashboard();
    if (document.getElementById('shop-jobs-table')) loadShopDashboard();
});
