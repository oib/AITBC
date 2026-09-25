// Bridge transfers page — shows cross_chain_transfer history from the chain.
// Source: GET /rpc/bridge/transfers (public, served by aitbc-blockchain-rpc).

const AIT_UNITS = 36000000;

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function statusBadge(status) {
    const s = String(status || '').toLowerCase();
    const cls = (s === 'completed' || s === 'confirmed') ? 'status-ok'
        : s === 'failed' ? 'status-bad'
        : 'status-pending';
    return `<span class="status-badge ${cls}">${escapeHtml(s.toUpperCase() || 'UNKNOWN')}</span>`;
}

function shortAddr(a) {
    if (!a) return '-';
    const e = escapeHtml(a);
    return a.length > 14 ? `${e.slice(0, 8)}...${e.slice(-6)}` : e;
}

function fmtAit(units) {
    if (units === null || units === undefined) return '-';
    const ait = Number(units) / AIT_UNITS;
    return Number.isFinite(ait) ? ait.toLocaleString(undefined, {maximumFractionDigits: 6}) : '-';
}

async function loadRecentBridges() {
    const loading = document.getElementById('recent-bridges-loading');
    const empty = document.getElementById('recent-bridges-empty');
    const container = document.getElementById('recent-bridges-container');
    try {
        const resp = await fetch('/rpc/bridge/transfers?limit=20');
        if (!resp.ok) {
            if (loading) loading.style.display = 'none';
            if (empty) empty.style.display = 'block';
            return;
        }
        const data = await resp.json();
        const transfers = data.transfers || [];
        if (loading) loading.style.display = 'none';
        if (transfers.length === 0) {
            if (empty) empty.style.display = 'block';
            return;
        }
        if (empty) empty.style.display = 'none';
        if (!container) return;
        container.innerHTML = transfers.map(d => {
            const time = d.confirm_time || d.lock_time;
            const when = time ? new Date(time).toLocaleString() : '-';
            const tx = d.transfer_id
                ? `<a href="/tx.html?hash=${encodeURIComponent(d.transfer_id)}" target="_blank" rel="noopener">${escapeHtml(d.transfer_id.slice(0, 18))}...</a>`
                : '—';
            const amount = fmtAit(d.release_amount !== null && d.release_amount !== undefined ? d.release_amount : d.amount);
            return `
                <div class="endpoint fade-in" style="padding:0;margin-bottom:0.75rem;">
                    <table class="block-list-table">
                        <tr><td>Time</td><td>${escapeHtml(when)}</td></tr>
                        <tr><td>Route</td><td>${escapeHtml(d.source_chain || '-')} &rarr; ${escapeHtml(d.target_chain || '-')}</td></tr>
                        <tr><td>Sender</td><td>${shortAddr(d.sender)}</td></tr>
                        <tr><td>Recipient</td><td>${shortAddr(d.recipient)}</td></tr>
                        <tr><td>Amount</td><td>${escapeHtml(amount)} AIT</td></tr>
                        <tr><td>Asset</td><td>${escapeHtml(d.asset || 'native')}</td></tr>
                        <tr><td>Tx</td><td>${tx}</td></tr>
                        <tr><td>Status</td><td>${statusBadge(d.status)}</td></tr>
                    </table>
                </div>
            `;
        }).join('');
    } catch (error) {
        console.error('Error loading recent bridges:', error);
        if (loading) loading.style.display = 'none';
    }
}

document.addEventListener('DOMContentLoaded', function() {
    loadRecentBridges();
    setInterval(loadRecentBridges, 60000);
});
