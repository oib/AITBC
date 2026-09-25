async function loadNetworkInfo() {
    try {
        const response = await fetch('/rpc/network-info');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();

        const role = data.is_hub ? 'HUB' : (data.role || 'FOLLOWER');

        // Update Join the Network section
        document.getElementById('node-id').textContent = data.p2p_node_id || 'unknown';
        document.getElementById('chain-id').textContent = data.chain_id || 'unknown';
        document.getElementById('role-name').textContent = role;

        // Update meta section
        document.getElementById('meta-node-id').textContent = data.p2p_node_id || 'unknown';
        document.getElementById('meta-chain-id').textContent = data.chain_id || 'unknown';
        document.getElementById('meta-role').textContent = role;

        // Update contact email
        if (data.contact_email) {
            document.getElementById('contact-email').textContent = data.contact_email;
            document.getElementById('contact-email-link').href = 'mailto:' + data.contact_email;
        }
    } catch (error) {
        console.error('Failed to load network info:', error);
        document.getElementById('node-id').textContent = 'unknown';
        document.getElementById('chain-id').textContent = 'unknown';
        document.getElementById('role-name').textContent = 'NODE';
        document.getElementById('meta-node-id').textContent = 'unknown';
        document.getElementById('meta-chain-id').textContent = 'unknown';
        document.getElementById('meta-role').textContent = 'unknown';
        document.getElementById('contact-email').textContent = 'unknown';
    }
}

// Load network info on page load
document.addEventListener('DOMContentLoaded', loadNetworkInfo);

// ── Island join form ──────────────────────────────────────────────────
// POSTs to /rpc/join, which issues a peer key bound to the node_id. The key
// is returned once and only its hash is stored server-side, so it is rendered
// here once — the page never keeps it.

function escapeHtml(s) {
    return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function handleJoinSubmit(event) {
    event.preventDefault();
    const nodeId = document.getElementById('join-node-id').value.trim();
    const contact = document.getElementById('join-contact').value.trim();
    const result = document.getElementById('join-result');
    const button = document.getElementById('join-submit');

    if (!/^[a-zA-Z0-9][a-zA-Z0-9._-]{2,63}$/.test(nodeId)) {
        result.innerHTML = '<p class="join-error">Node ID must be 3-64 characters: letters, digits, dots, hyphens, underscores.</p>';
        return;
    }

    button.disabled = true;
    result.innerHTML = '<p class="endpoint-note-sm">Requesting key…</p>';
    try {
        const response = await fetch('/rpc/join', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({node_id: nodeId, contact: contact || undefined}),
        });
        const data = await response.json();
        if (!response.ok) {
            const detail = data.detail || `HTTP ${response.status}`;
            result.innerHTML = `<p class="join-error">${escapeHtml(String(detail))}</p>`;
            return;
        }
        result.innerHTML =
            `<div class="join-success">` +
            `<p><strong>Peer key issued — shown once, store it now:</strong></p>` +
            `<code class="join-key">${escapeHtml(data.peer_key)}</code>` +
            `<button type="button" class="copy-btn" data-copy="${escapeHtml(data.peer_key)}" onclick="navigator.clipboard.writeText(this.dataset.copy)">copy</button>` +
            `<p class="endpoint-note-sm">Add to your node's <code>/etc/aitbc/blockchain-secrets.env</code> (or <code>node.env</code>):<br>` +
            `<code>${escapeHtml(data.env_snippet)}</code></p>` +
            `<p class="endpoint-note-sm">Bound to <code>${escapeHtml(data.node_id)}</code>. If you lose it, ask the operator to revoke so you can re-join.</p>` +
            `<p class="endpoint-note-sm">Welcome gift: once your node is up, claim <strong>3 AIT free</strong> with <code>aitbc coin-requests request</code> — first request auto-pays.</p>` +
            `</div>`;
    } catch (error) {
        result.innerHTML = `<p class="join-error">Request failed: ${escapeHtml(String(error))}</p>`;
    } finally {
        button.disabled = false;
    }
}

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('join-form');
    if (form) form.addEventListener('submit', handleJoinSubmit);
});
