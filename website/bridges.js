// Bridge deposits page — shows recent ETH→AIT bridge transactions

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function statusBadge(status) {
    const cls = status === 'completed' ? 'status-ok'
        : status === 'failed' ? 'status-bad'
        : 'status-pending';
    return `<span class="status-badge ${cls}">${escapeHtml(status.toUpperCase())}</span>`;
}

async function loadRecentBridges() {
    const loading = document.getElementById('recent-bridges-loading');
    const empty = document.getElementById('recent-bridges-empty');
    const container = document.getElementById('recent-bridges-container');
    try {
        const resp = await fetch('/v1/bridge/deposits?status=completed&limit=20');
        if (!resp.ok) {
            if (loading) loading.style.display = 'none';
            if (empty) empty.style.display = 'block';
            return;
        }
        const data = await resp.json();
        const deposits = data.deposits || [];
        if (loading) loading.style.display = 'none';
        if (deposits.length === 0) {
            if (empty) empty.style.display = 'block';
            return;
        }
        if (empty) empty.style.display = 'none';
        if (!container) return;
        container.innerHTML = deposits.map(d => {
            const d2 = d.dict ? d.dict() : d;
            const time = d2.created_at ? new Date(d2.created_at).toLocaleString() : '-';
            const eth = d2.eth_amount || '-';
            const ait = d2.ait_amount || '-';
            const fromShort = d2.eth_from_address
                ? `${escapeHtml(d2.eth_from_address.slice(0, 6))}...${escapeHtml(d2.eth_from_address.slice(-4))}`
                : '-';
            const aitTx = d2.ait_tx_hash
                ? `<a href="/tx.html?hash=${encodeURIComponent(d2.ait_tx_hash)}" target="_blank" rel="noopener">${escapeHtml(d2.ait_tx_hash.slice(0, 18))}...</a>`
                : '—';
            const note = d2.error_message && d2.status === 'completed'
                ? d2.error_message
                : '';
            const status = statusBadge(d2.status || 'completed');
            const noteRow = note
                ? `<tr><td>Note</td><td><span class="muted-text" style="font-size:0.8rem;">${escapeHtml(note)}</span></td></tr>`
                : '';
            return `
                <div class="endpoint fade-in" style="padding:0;margin-bottom:0.75rem;">
                    <table class="block-list-table">
                        <tr><td>Time</td><td>${escapeHtml(time)} UTC</td></tr>
                        <tr><td>ETH</td><td>${escapeHtml(eth)}</td></tr>
                        <tr><td>From</td><td>${fromShort}</td></tr>
                        <tr><td>AIT</td><td>${escapeHtml(ait)}</td></tr>
                        <tr><td>AIT Tx</td><td>${aitTx}</td></tr>
                        <tr><td>Status</td><td>${status}</td></tr>
                        ${noteRow}
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
