// ── Network facts + join-sentence/meta fill ───────────────────────────
// One shared path: applyNetworkInfo writes the join sentence ("This node
// (…) is the … for the … island") and the meta block from a proven
// network-info reply. networkInfoGood gates the first-failure "unknown"
// writes so a later failed re-read never overwrites good values (the
// site's stale-note rule). loadFacts() is the single reader — it polls
// every 60 s and drives both the sentence and the strip, so nothing is
// fetched twice per cycle.

let networkInfoGood = false;

function applyNetworkInfo(data) {
    const role = data.is_hub ? 'HUB' : (data.role || 'FOLLOWER');

    // Join the Network section
    document.getElementById('node-id').textContent = data.p2p_node_id || 'unknown';
    document.getElementById('chain-id').textContent = data.chain_id || 'unknown';
    document.getElementById('role-name').textContent = role;

    // Meta section
    document.getElementById('meta-node-id').textContent = data.p2p_node_id || 'unknown';
    document.getElementById('meta-chain-id').textContent = data.chain_id || 'unknown';
    document.getElementById('meta-role').textContent = role;

    // Contact email
    if (data.contact_email) {
        document.getElementById('contact-email').textContent = data.contact_email;
        document.getElementById('contact-email-link').href = 'mailto:' + data.contact_email;
    }
}

function markNetworkInfoUnknown() {
    document.getElementById('node-id').textContent = 'unknown';
    document.getElementById('chain-id').textContent = 'unknown';
    document.getElementById('role-name').textContent = 'NODE';
    document.getElementById('meta-node-id').textContent = 'unknown';
    document.getElementById('meta-chain-id').textContent = 'unknown';
    document.getElementById('meta-role').textContent = 'unknown';
    document.getElementById('contact-email').textContent = 'unknown';
}

// ── Live network facts strip ──────────────────────────────────────────
// One strip, three states: loading → live (green, proven reply) → unknown
// (amber, reason in words, Try again). A failed or unreadable reply never
// reads as loading or empty — the strip says unknown and re-checks every
// 60 s. "Proven" = network-info carries chain_id + p2p_node_id + a
// validators array AND /rpc/head carries a numeric height.

function renderFactsState(state, detailText) {
    const strip = document.getElementById('facts-strip');
    if (!strip) return;
    const titles = {
        'loading': 'Reading network facts…',
        'live': 'Live network facts',
        'unknown': 'Network facts unknown',
    };
    strip.className = 'facts-strip is-' + (state in titles ? state : 'unknown');
    const title = strip.querySelector('.facts-strip-title');
    if (title) title.textContent = titles[state] || titles.unknown;
    const detail = document.getElementById('facts-detail');
    if (detail) detail.textContent = detailText || '';
    const retry = document.getElementById('facts-retry-btn');
    if (retry) retry.hidden = state !== 'unknown';
}

function setFact(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

async function loadFacts() {
    let info = null, infoErr = null;
    try {
        const r = await fetch('/rpc/network-info');
        if (!r.ok) {
            infoErr = 'HTTP ' + r.status;
        } else {
            try { info = await r.json(); } catch (e) { infoErr = 'reply was not readable'; }
        }
    } catch (e) {
        infoErr = 'network request failed';
    }
    let head = null, headErr = null;
    try {
        const r = await fetch('/rpc/head');
        if (!r.ok) {
            headErr = 'HTTP ' + r.status;
        } else {
            try { head = await r.json(); } catch (e) { headErr = 'reply was not readable'; }
        }
    } catch (e) {
        headErr = 'network request failed';
    }

    const infoProven = info && typeof info === 'object'
        && typeof info.chain_id === 'string' && info.chain_id
        && typeof info.p2p_node_id === 'string' && info.p2p_node_id
        && Array.isArray(info.validators);
    const headProven = head && typeof head === 'object' && Number.isFinite(Number(head.height));

    if (infoProven) {
        applyNetworkInfo(info);
        networkInfoGood = true;
    } else if (!networkInfoGood) {
        markNetworkInfoUnknown();
    }

    if (infoProven && headProven) {
        setFact('fact-node', info.p2p_node_id);
        setFact('fact-island', info.chain_id);
        setFact('fact-height', String(head.height));
        setFact('fact-validators', String(info.validators.length));
        renderFactsState('live', 'read ' + new Date().toUTCString().slice(17, 22) + ' UTC');
        return;
    }

    if (!infoErr && !infoProven) infoErr = 'reply was not the expected shape';
    if (!headErr && !headProven) headErr = 'reply was not the expected shape';
    const reason = infoErr ? 'network info: ' + infoErr : 'chain head: ' + headErr;
    renderFactsState('unknown', reason + ' — checks again every 60 s');
}

document.addEventListener('DOMContentLoaded', function() {
    loadFacts();
    setInterval(loadFacts, 60000);
    const retry = document.getElementById('facts-retry-btn');
    if (retry) retry.addEventListener('click', loadFacts);
});

// ── Island join form ──────────────────────────────────────────────────
// POSTs to /rpc/join, which issues a peer key bound to the node_id. The key
// is returned once and only its hash is stored server-side, so it is rendered
// here once — the page never keeps it.

function escapeHtml(s) {
    return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function setJoinRetry(visible) {
    const retry = document.getElementById('join-retry-btn');
    if (retry) retry.hidden = !visible;
}

function joinFailed(reason, detail) {
    const result = document.getElementById('join-result');
    result.innerHTML =
        `<div class="join-failed" role="alert">` +
        `<p class="join-failed-title">Could not request a key (${escapeHtml(reason)})</p>` +
        (detail ? `<p class="join-failed-detail">${escapeHtml(detail)}</p>` : '') +
        `</div>`;
    setJoinRetry(true);
}

async function handleJoinSubmit(event) {
    event.preventDefault();
    const nodeId = document.getElementById('join-node-id').value.trim();
    const contact = document.getElementById('join-contact').value.trim();
    const result = document.getElementById('join-result');
    const button = document.getElementById('join-submit');

    setJoinRetry(false);
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
        let data = null;
        try { data = await response.json(); } catch (e) { data = null; }
        if (!response.ok) {
            // 409 is a server answer, not a failure: the node id already
            // holds a key and nothing new was issued. Everything else —
            // HTTP error or unreadable body — is could-not-request.
            if (response.status === 409) {
                result.innerHTML =
                    `<p class="join-neutral">` +
                    `<strong>Node ID already has a key</strong> — the server answered; nothing new was issued.<br>` +
                    `<span class="endpoint-note-sm">If the key is lost, contact the operator to revoke and re-join.</span>` +
                    `</p>`;
                return;
            }
            joinFailed(
                `HTTP ${response.status}`,
                data && data.detail ? String(data.detail) : 'nothing was issued',
            );
            return;
        }
        if (!data || typeof data !== 'object' || typeof data.peer_key !== 'string' || !data.peer_key) {
            joinFailed(response.ok ? 'reply was not the expected shape' : `HTTP ${response.status}`, 'nothing was issued');
            return;
        }
        result.innerHTML =
            `<div class="join-success">` +
            `<p><strong>Peer key issued — shown once, store it now:</strong></p>` +
            `<code class="join-key">${escapeHtml(data.peer_key)}</code>` +
            aitbcCopyBtn(data.peer_key, 'peer key') +
            `<p class="endpoint-note-sm">Add to your node's <code>/etc/aitbc/blockchain-secrets.env</code> (or <code>node.env</code>):<br>` +
            `<code>${escapeHtml(data.env_snippet)}</code></p>` +
            `<p class="endpoint-note-sm">Bound to <code>${escapeHtml(data.node_id)}</code>. If you lose it, ask the operator to revoke so you can re-join.</p>` +
            `<p class="endpoint-note-sm">Welcome gift: once your node is up, request the one-time <strong>3 AIT</strong> grant with <code>aitbc coin-requests request</code> — paid once the hub faucet resumes.</p>` +
            `</div>`;
    } catch (error) {
        joinFailed('network request failed', 'nothing was issued');
    } finally {
        button.disabled = false;
    }
}

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('join-form');
    if (form) form.addEventListener('submit', handleJoinSubmit);
    const retry = document.getElementById('join-retry-btn');
    if (retry) retry.addEventListener('click', function() { if (form) form.requestSubmit(); });
});
