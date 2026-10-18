const EXPLORER_API_URL = '/explorer-api';

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function getParam(name) {
    const url = new URL(window.location.href);
    return url.searchParams.get(name);
}


function plainHash(hash) {
    if (!hash || hash === 'N/A') return 'N/A';
    return `<span class="mono-value">${escapeHtml(hash)}</span>`;
}

function addrLink(addr) {
    if (!addr || addr === 'N/A') return 'N/A';
    return `<a href="/search.html?query=${encodeURIComponent(addr)}" class="clickable-value" title="Search address">${escapeHtml(addr)}</a>`;
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

async function loadTransaction() {
    const hash = getParam('hash');

    if (!hash) {
        document.getElementById('loading').hidden = true;
        showError('Missing transaction hash parameter');
        return;
    }

    document.getElementById('loading').hidden = false;
    try {
        const resp = await fetch(`${EXPLORER_API_URL}/api/transactions/${hash}`);
        // A failed reply is not "not found" — only a 404 or a proven
        // non-transaction reply falls through to the block-hash probe.
        if (!resp.ok && resp.status !== 404) {
            throw new Error(`Transaction could not be loaded (HTTP ${resp.status}). This is not a "not found".`);
        }
        let data = null;
        if (resp.ok) {
            try {
                data = await resp.json();
            } catch (e) {
                throw new Error('Transaction reply was not readable JSON');
            }
            // The route answers a real 404 for a missing tx — an ok
            // body without a hash is a shape failure, not a probe
            // candidate.
            if (!data || !data.hash) {
                throw new Error('Transaction could not be loaded (reply was not the expected shape). This is not a "not found".');
            }
        }

        if (!data) {
            // 404 — not a tx hash; try as block hash and redirect if found
            const blockResp = await fetch(`${EXPLORER_API_URL}/api/blocks/by-hash/${hash}`);
            if (!blockResp.ok && blockResp.status !== 404) {
                throw new Error(`Transaction could not be loaded (HTTP ${blockResp.status}). This is not a "not found".`);
            }
            let blockData = null;
            if (blockResp.ok) {
                try {
                    blockData = await blockResp.json();
                } catch (e) {
                    throw new Error('Transaction reply was not readable JSON');
                }
            }
            if (blockResp.ok && (!blockData || blockData.height == null)) {
                throw new Error('Transaction could not be loaded (reply was not the expected shape). This is not a "not found".');
            }
            if (blockData && blockData.height != null) {
                location.href = `/block.html?height=${blockData.height}`;
                return;
            }
            throw new Error('No transaction or block found for this hash');
        }

        document.title = `AITBC TX ${data.hash.substring(0, 16)}...`;
        document.getElementById('tx-type-badge').textContent = aitbcFmt.type(data.type || 'TX');
        document.getElementById('tx-hash-display').textContent = data.hash;

        const details = [
            { label: 'Type', value: `<span class="badge badge-primary">${escapeHtml(aitbcFmt.type(data.type || 'TX'))}</span>` },
            { label: 'Hash', value: plainHash(data.hash) + ' ' + aitbcCopyBtn(data.hash, 'transaction hash') },
            { label: 'Status', value: escapeHtml(data.status || 'Unknown') },
            { label: 'Block', value: `<a href="/block.html?height=${encodeURIComponent(data.block_height)}">#${escapeHtml(data.block_height)}</a>` },
            { label: 'From', value: addrLink(data.from || data.sender) + ' ' + aitbcCopyBtn(data.from || data.sender || '', 'sender address') },
            { label: 'To', value: addrLink(data.to || data.recipient) + ' ' + aitbcCopyBtn(data.to || data.recipient || '', 'recipient address') },
            { label: 'Value', value: escapeHtml(data.value !== undefined ? data.value : 'N/A') },
            { label: 'Fee', value: escapeHtml(data.fee !== undefined ? data.fee : 'N/A') },
            { label: 'Nonce', value: escapeHtml(data.nonce !== undefined ? data.nonce : 'N/A') },
            { label: 'Timestamp', value: escapeHtml(data.created_at ? aitbcFmt.date(data.created_at) : 'N/A') },
        ];

        // MSG-4: forum posts surface a badge linking to their topic;
        // non-forum MESSAGE rows (e.g. bridge internals) show nothing.
        // The badge requires a plausible envelope shape, not merely the
        // namespace key — a stray {aitbc_msg: {...}} sibling stays inert.
        const msg = data.payload && typeof data.payload === 'object' ? data.payload.aitbc_msg : null;
        const forumLike = msg && typeof msg === 'object' && msg.v === 1
            && (msg.kind === 'post' || msg.kind === 'reply')
            && typeof msg.topic === 'string';
        if (data.type === 'MESSAGE' && forumLike) {
            // MSG-4b: the topic is chain text — make format/C1/tag
            // chars visible before it reaches the DOM (same rule as
            // messages.js).
            const NEUTRAL_RE = /[\u0080-\u009F\p{Cf}\u061C\u180E\u{E0000}-\u{E007F}]/gu;
            const cleanTopic = String(msg.topic).replace(NEUTRAL_RE, (ch) => `[U+${ch.codePointAt(0).toString(16).toUpperCase().padStart(4, '0')}]`);
            details.push({
                label: 'Forum',
                value: `<a class="badge badge-primary" href="/topic.html?t=${encodeURIComponent(cleanTopic)}" title="Open topic">${escapeHtml('forum ' + msg.kind + ': ' + cleanTopic)}</a>`,
            });
        }

        document.getElementById('tx-details').innerHTML = `
            <div class="endpoint table-card fade-in block-item">
                <div class="table-wrap"><table class="block-list-table" aria-label="Transaction details">
                    ${details.map(d => `<tr><th scope="row">${d.label}</th><td>${d.value}</td></tr>`).join('')}
                </table></div>
            </div>
        `;

        if (data.payload) {
            let payloadText;
            try {
                payloadText = JSON.stringify(typeof data.payload === 'string' ? JSON.parse(data.payload) : data.payload, null, 2);
            } catch (e) {
                payloadText = String(data.payload);
            }
            document.getElementById('payload-content').textContent = payloadText;
            document.getElementById('payload-card').hidden = false;
        }

        document.getElementById('loading').hidden = true;
        document.getElementById('content').hidden = false;
    } catch (err) {
        document.getElementById('loading').hidden = true;
        showError(err.message || 'Failed to load transaction', loadTransaction);
    }
}

document.addEventListener('DOMContentLoaded', loadTransaction);
