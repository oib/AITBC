// Bridge transfers page — shows cross_chain_transfer history from the chain.
// Source: GET /rpc/bridge/transfers (public, served by aitbc-blockchain-rpc).

const AIT_UNITS = 36000000;

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

const BRIDGE_STATUS_BADGES = {
    pending:   { cls: 'bridge-status-pending',   icon: '◷' },
    confirmed: { cls: 'bridge-status-confirmed', icon: '✓' },
    completed: { cls: 'bridge-status-completed', icon: '✓✓' },
    refunded:  { cls: 'bridge-status-refunded',  icon: '↩' },
    failed:    { cls: 'bridge-status-failed',    icon: '✕' },
};

function statusBadge(status) {
    const raw = String(status || '').trim();
    const key = raw.toLowerCase();
    const entry = Object.prototype.hasOwnProperty.call(BRIDGE_STATUS_BADGES, key)
        ? BRIDGE_STATUS_BADGES[key] : null;
    if (!entry) {
        return `<span class="status-badge bridge-status-unknown"><span class="bridge-badge-icon" aria-hidden="true">?</span> ${escapeHtml(raw || 'unknown')}</span>`;
    }
    return `<span class="status-badge ${escapeHtml(entry.cls)}"><span class="bridge-badge-icon" aria-hidden="true">${escapeHtml(entry.icon)}</span> ${escapeHtml(raw.toUpperCase())}</span>`;
}

function shortAddr(a) {
    if (!a) return '-';
    const e = escapeHtml(a);
    if (a.length <= 14) return e;
    // Address halves and the copy button are separate spans so the table
    // can stack them on three short lines; cards keep them on one line.
    return `<span aria-hidden="true"><span class="bridge-addr-a">${escapeHtml(a.slice(0, 8))}</span><span class="bridge-addr-b">...${escapeHtml(a.slice(-6))}</span></span><span class="visually-hidden">${e}</span> <span class="bridge-copy">${aitbcCopyBtn(a, 'address')}</span>`;
}

function fmtAit(units) {
    if (units === null || units === undefined) return '-';
    const ait = Number(units) / AIT_UNITS;
    return Number.isFinite(ait) ? aitbcFmt.num(ait, 6) : '-';
}

let lastTransfersReadAt = 0;
let renderedTransfers = 0;
let lastHealthReadAt = 0;

function showTransfersFailure(reason) {
    const loading = document.getElementById('recent-bridges-loading');
    const empty = document.getElementById('recent-bridges-empty');
    const failed = document.getElementById('recent-bridges-failed');
    const reasonEl = document.getElementById('recent-bridges-failed-reason');
    const note = document.getElementById('recent-bridges-fail-note');
    if (loading) loading.style.display = 'none';
    if (empty) empty.style.display = 'none';
    if (renderedTransfers > 0) {
        if (failed) failed.style.display = 'none';
        if (note) {
            note.style.display = 'block';
            note.textContent = `Could not refresh: ${reason} Showing transfers last loaded ${aitbcFmt.time(lastTransfersReadAt)}.`;
        }
        return;
    }
    if (note) note.style.display = 'none';
    if (reasonEl) reasonEl.textContent = reason;
    if (failed) failed.style.display = 'block';
}

async function loadRecentBridges() {
    const loading = document.getElementById('recent-bridges-loading');
    const empty = document.getElementById('recent-bridges-empty');
    const failed = document.getElementById('recent-bridges-failed');
    const note = document.getElementById('recent-bridges-fail-note');
    const container = document.getElementById('recent-bridges-container');
    let reason = '';
    let transfers = null;
    try {
        const resp = await fetch('/rpc/bridge/transfers?limit=20');
        if (!resp.ok) {
            reason = `HTTP ${resp.status}`;
        } else {
            let data = null;
            try {
                data = await resp.json();
            } catch (parseErr) {
                reason = 'the reply was not readable JSON';
            }
            if (!reason) {
                if (data && Array.isArray(data.transfers)) {
                    transfers = data.transfers;
                } else {
                    reason = 'the reply was not a transfers list';
                }
            }
        }
    } catch (error) {
        console.error('Error loading recent bridges:', error);
        reason = reason || 'network request failed';
    }
    if (transfers === null) {
        showTransfersFailure(reason);
        return;
    }
    if (loading) loading.style.display = 'none';
    if (failed) failed.style.display = 'none';
    if (note) note.style.display = 'none';
    lastTransfersReadAt = Date.now();
    const visible = transfers.filter(d => d && typeof d === 'object' && !Array.isArray(d));
    const skipped = transfers.length - visible.length;
    renderedTransfers = visible.length;
    if (visible.length === 0) {
        if (container) container.innerHTML = '';
        if (empty) empty.style.display = transfers.length === 0 ? 'block' : 'none';
    } else {
        if (empty) empty.style.display = 'none';
    }
    if (skipped > 0 && note) {
        note.style.display = 'block';
        note.textContent = `${skipped} item${skipped === 1 ? '' : 's'} in the reply could not be shown.`;
    }
    if (visible.length === 0 || !container) return;
    const rows = visible.map(transferRow).join('');
    const cards = visible.map(transferCard).join('');
    container.innerHTML = `<div class="table-wrap" id="bridge-table-wrap" role="region" tabindex="0" aria-label="Bridge transfers">
        <table class="bridge-table">
            <thead><tr>
                <th scope="col">When</th>
                <th scope="col">Route</th>
                <th scope="col">Sender</th>
                <th scope="col">Recipient</th>
                <th scope="col" class="bridge-col-amt">Amount</th>
                <th scope="col">Status</th>
                <th scope="col">Transfer</th>
            </tr></thead>
            <tbody>${rows}</tbody>
        </table>
    </div>
    <div class="bridge-cards">${cards}</div>`;
}

function shortChain(c) {
    const s = String(c || '').replace(/\.aitbc\.bubuit\.net$/, '');
    return s || '-';
}

function transferParts(d) {
    const time = d.confirm_time || d.lock_time;
    // Date and time are separate spans so the table can stack them on two
    // lines (aitbcFmt.date gives "YYYY-MM-DD HH:mm"); cards keep them inline.
    const whenParts = time ? aitbcFmt.date(time).split(' ') : ['-'];
    const when = whenParts.map((p, i) => `<span class="bridge-when-${i === 0 ? 'date' : 'time'}">${escapeHtml(p)}</span>`).join(' ');
    const whenNote = time ? (d.confirm_time ? 'confirmed' : 'locked') : '';
    const srcChain = String(d.source_chain || '-');
    const tgtChain = String(d.target_chain || '-');
    // Source and target are separate spans so the table can stack them
    // (source, then "→ target"); cards keep them on one line.
    const routeHtml = `<span title="${escapeHtml(srcChain)} &rarr; ${escapeHtml(tgtChain)}"><span class="bridge-route-src">${escapeHtml(shortChain(srcChain))}</span> <span class="bridge-route-tgt">&rarr; ${escapeHtml(shortChain(tgtChain))}</span></span>`;
    const senderHtml = shortAddr(d.sender);
    const sameAsSender = d.sender && d.recipient
        && String(d.sender).toLowerCase() === String(d.recipient).toLowerCase();
    const recipientHtml = sameAsSender ? '<span class="muted-text">same as sender</span>' : shortAddr(d.recipient);
    const amount = escapeHtml(fmtAit(d.release_amount !== null && d.release_amount !== undefined ? d.release_amount : d.amount));
    const tx = d.transfer_id
        ? `<a href="/tx.html?hash=${encodeURIComponent(d.transfer_id)}" target="_blank" rel="noopener noreferrer" aria-label="Transaction ${escapeHtml(d.transfer_id)}"><span class="bridge-tx-a">${escapeHtml(d.transfer_id.slice(0, 8))}</span><span class="bridge-tx-b">${escapeHtml(d.transfer_id.slice(8, 18))}...</span></a> <span class="bridge-copy">${aitbcCopyBtn(d.transfer_id, 'transaction hash')}</span>`
        : '—';
    return { when, whenNote, routeHtml, senderHtml, recipientHtml, amount, tx };
}

function transferRow(d) {
    const parts = transferParts(d);
    return `<tr>
        <td class="bridge-when"><span class="bridge-when-main">${parts.when}</span><span class="bridge-when-note">${parts.whenNote}</span></td>
        <td class="bridge-route">${parts.routeHtml}</td>
        <td>${parts.senderHtml}</td>
        <td>${parts.recipientHtml}</td>
        <td class="bridge-amt">${parts.amount} AIT</td>
        <td>${statusBadge(d.status)}</td>
        <td>${parts.tx}</td>
    </tr>`;
}

function transferCard(d) {
    const parts = transferParts(d);
    return `<div class="bridge-card-item">
        <div class="bridge-card-top"><span class="bridge-when-main">${parts.when}</span>${statusBadge(d.status)}</div>
        <div class="bridge-card-line"><span class="bridge-card-k">Route</span>${parts.routeHtml}</div>
        <div class="bridge-card-line"><span class="bridge-card-k">From</span>${parts.senderHtml}</div>
        <div class="bridge-card-line"><span class="bridge-card-k">To</span>${parts.recipientHtml}</div>
        <div class="bridge-card-line"><span class="bridge-card-k">Amount</span><span class="bridge-amt">${parts.amount} AIT</span></div>
        <div class="bridge-card-line">${parts.tx}</div>
    </div>`;
}

function healthBits(data) {
    const bits = [];
    bits.push(data.release_enabled ? 'Releases on' : 'Releases off');
    const pending = Number(data.pending_transfer_count);
    if (Number.isFinite(pending)) bits.push(`${pending} pending`);
    const maxLock = fmtAit(data.bridge_max_lock_amount);
    if (maxLock !== '-') bits.push(`max lock ${maxLock} AIT`);
    return bits;
}

function renderBridgeHealth(data, reason) {
    const banner = document.getElementById('bridge-health');
    if (!banner) return;
    const title = banner.querySelector('.bridge-health-title');
    const detail = banner.querySelector('.bridge-health-detail');
    const ago = lastHealthReadAt ? `read ${aitbcFmt.time(lastHealthReadAt)}` : '';
    let cls;
    let titleText;
    let detailText;
    if (!data) {
        cls = 'is-unknown';
        titleText = 'Bridge state unknown';
        detailText = reason || 'The bridge health endpoint did not answer.';
    } else if (data.success === true && data.status === 'healthy' && data.bridge_initialized === true) {
        cls = 'is-healthy';
        titleText = 'Bridge healthy';
        detailText = healthBits(data).concat(ago ? [ago] : []).join(' · ');
    } else if (data.bridge_initialized === false) {
        cls = 'is-attention';
        titleText = 'Bridge needs attention';
        detailText = ['The bridge reported it is not initialized.'].concat(healthBits(data), ago ? [ago] : []).join(' · ');
    } else if (typeof data.status === 'string' && data.status) {
        cls = 'is-attention';
        titleText = 'Bridge needs attention';
        detailText = [`Status: ${data.status}`].concat(healthBits(data), ago ? [ago] : []).join(' · ');
    } else if (data.success === false) {
        cls = 'is-attention';
        titleText = 'Bridge needs attention';
        detailText = ['The bridge reported it is not ready.'].concat(healthBits(data), ago ? [ago] : []).join(' · ');
    } else {
        cls = 'is-unknown';
        titleText = 'Bridge state unknown';
        detailText = 'The bridge health endpoint gave an unexpected answer.';
    }
    banner.className = `bridge-health ${cls}`;
    if (title) title.textContent = titleText;
    if (detail) detail.textContent = detailText;
}

async function loadBridgeHealth() {
    try {
        const resp = await fetch('/rpc/bridge/health');
        if (!resp.ok) {
            renderBridgeHealth(null, `HTTP ${resp.status}`);
            return;
        }
        let data = null;
        try {
            data = await resp.json();
        } catch (parseErr) {
            renderBridgeHealth(null, 'the reply was not readable JSON');
            return;
        }
        lastHealthReadAt = Date.now();
        renderBridgeHealth(data);
    } catch (error) {
        console.error('Error loading bridge health:', error);
        renderBridgeHealth(null, 'network request failed');
    }
}

document.addEventListener('DOMContentLoaded', function() {
    const retry = document.getElementById('recent-bridges-retry');
    if (retry) retry.addEventListener('click', loadRecentBridges);
    loadBridgeHealth();
    loadRecentBridges();
    setInterval(loadRecentBridges, 60000);
    setInterval(loadBridgeHealth, 60000);
});
