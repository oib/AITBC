const EXPLORER_API_URL = '/explorer-api';

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function getParam(name) {
    const url = new URL(window.location.href);
    return url.searchParams.get(name);
}


function showError(msg, retry) {
    const errEl = document.getElementById('error');
    errEl.textContent = msg;
    if (retry) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'bridge-retry detail-retry';
        btn.textContent = 'Try again';
        btn.addEventListener('click', retry);
        errEl.appendChild(btn);
    }
    errEl.hidden = false;
}

async function loadBlock() {
    const height = getParam('height');
    const hash = getParam('hash');

    if (!height && !hash) {
        document.getElementById('loading').hidden = true;
        showError('Missing block height or hash parameter');
        return;
    }

    document.getElementById('loading').hidden = false;
    try {
        let data;
        let resp;
        if (height) {
            resp = await fetch(`${EXPLORER_API_URL}/api/blocks/${height}`);
        } else {
            resp = await fetch(`${EXPLORER_API_URL}/api/blocks/by-hash/${hash}`);
        }
        // A failed reply is not "not found" — only a 404 or a proven
        // body without a block is.
        if (!resp.ok) {
            throw new Error(resp.status === 404
                ? 'Block not found'
                : `Block could not be loaded (HTTP ${resp.status}). This is not a "not found".`);
        }
        try {
            data = await resp.json();
        } catch (e) {
            throw new Error('Block reply was not readable JSON');
        }

        // The route answers a real 404 for a missing block — an ok
        // body without a height is a shape failure, not a not-found.
        if (!data || data.height == null) {
            throw new Error('Block could not be loaded (reply was not the expected shape). This is not a "not found".');
        }

        document.title = `AITBC Block #${data.height}`;
        document.getElementById('block-kind-badge').textContent = aitbcFmt.type('BLOCK');
        document.getElementById('block-height-badge').textContent = `#${data.height}`;
        document.getElementById('block-hash-display').textContent = data.hash || '';

        function plainHash(hash) {
            if (!hash || hash === 'N/A') return 'N/A';
            return `<span class="mono-value">${escapeHtml(hash)}</span>`;
        }
        function addrLink(addr) {
            if (!addr || addr === 'N/A') return 'N/A';
            return `<a href="/search.html?query=${encodeURIComponent(addr)}" class="clickable-value" title="Search address">${escapeHtml(addr)}</a>`;
        }

        document.getElementById('block-details').innerHTML = `
            <div class="endpoint table-card fade-in block-item">
                <div class="table-wrap"><table class="block-list-table" aria-label="Block details">
                    <tr><th scope="row">Height</th><td><span class="badge badge-primary">${escapeHtml(aitbcFmt.type('BLOCK'))}</span> #${escapeHtml(data.height)}</td></tr>
                    <tr><th scope="row">Hash</th><td>${plainHash(data.hash)} ${aitbcCopyBtn(data.hash || '', 'block hash')}</td></tr>
                    <tr><th scope="row">Proposer</th><td>${addrLink(data.proposer)} ${aitbcCopyBtn(data.proposer || '', 'proposer address')}</td></tr>
                    <tr><th scope="row">Timestamp</th><td>${escapeHtml(data.timestamp ? aitbcFmt.date(data.timestamp) : 'N/A')}</td></tr>
                    <tr><th scope="row">Transactions</th><td>${escapeHtml(data.txCount ?? data.transactions?.length ?? 0)}</td></tr>
                    <tr><th scope="row">State Root</th><td>${plainHash(data.stateRoot)} ${aitbcCopyBtn(data.stateRoot || '', 'state root')}</td></tr>
                </table></div>
            </div>
        `;

        const txs = data.transactions || [];
        document.getElementById('tx-count').textContent = `(${txs.length})`;
        document.getElementById('tx-list').innerHTML = txs.map(tx => {
            // One malformed payload must not blank the whole block.
            let payloadAmount = 'N/A';
            try {
                payloadAmount = tx.payload ? (JSON.parse(tx.payload).amount || 'N/A') : 'N/A';
            } catch (e) { payloadAmount = 'N/A'; }
            const amount = tx.amount != null ? tx.amount : payloadAmount;
            return `
            <div class="endpoint table-card fade-in block-item" tabindex="0" role="link" data-href="/tx.html?hash=${encodeURIComponent(tx.tx_hash)}">
                <div class="table-wrap"><table class="block-list-table" aria-label="Block details">
                    <tr><th scope="row">Type</th><td><span class="badge badge-primary">${escapeHtml(aitbcFmt.type(tx.type || 'TX'))}</span></td></tr>
                    <tr><th scope="row">Hash</th><td>${escapeHtml(tx.tx_hash)} ${aitbcCopyBtn(tx.tx_hash, 'transaction hash')}</td></tr>
                    <tr><th scope="row">From</th><td>${addrLink(tx.sender)}</td></tr>
                    <tr><th scope="row">To</th><td>${addrLink(tx.recipient)}</td></tr>
                    <tr><th scope="row">Amount</th><td><strong>${escapeHtml(amount)}</strong> AIT</td></tr>
                    <tr><th scope="row">Fee</th><td>${escapeHtml(tx.fee != null ? tx.fee : 'N/A')}</td></tr>
                    <tr><th scope="row">Nonce</th><td>${escapeHtml(tx.nonce != null ? tx.nonce : 'N/A')}</td></tr>
                    <tr><th scope="row">Status</th><td>${escapeHtml(tx.status || 'N/A')}</td></tr>
                    <tr><th scope="row">Time</th><td>${escapeHtml(tx.created_at ? aitbcFmt.date(tx.created_at) : 'N/A')}</td></tr>
                </table></div>
            </div>
            `;
        }).join('') || '<p class="loading-text">No transactions in this block.</p>';

        document.getElementById('loading').hidden = true;
        document.getElementById('content').hidden = false;
    } catch (err) {
        document.getElementById('loading').hidden = true;
        showError(err.message || 'Failed to load block', loadBlock);
    }
}

document.addEventListener('DOMContentLoaded', loadBlock);
