function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// Committed fallback; reference.json overrides it once loaded.
let refEur = 0.25;

async function fetchReference() {
    try {
        const response = await fetch('reference.json');
        if (!response.ok) return;
        renderReference(await response.json());
    } catch (error) {
        console.error('Error fetching reference breakdown:', error);
    }
}

function eurStr(v, digits) {
    const n = Number(v);
    return isFinite(n) ? `&euro;${n.toFixed(digits)}` : '-';
}

function renderReference(ref) {
    if (ref && ref.model && ref.model.reference_price_eur != null) {
        refEur = Number(ref.model.reference_price_eur);
    }
    const heroEur = document.getElementById('hero-eur-value');
    if (heroEur) heroEur.innerHTML = `&asymp; ${eurStr(refEur, 2)}`;

    const tbody = document.querySelector('#reference-table tbody');
    if (!tbody || !ref || !ref.per_hour) return;

    const m = ref.model || {};
    const ph = ref.per_hour;
    const hours = Number(m.bookable_hours).toLocaleString('en-US');
    const rows = [];
    for (const c of ref.components || []) {
        rows.push([escapeHtml(c.name), eurStr(c.cost_eur, 2)]);
    }
    rows.push(['Hardware total (BOM)', eurStr(ref.hardware_total_eur, 2)]);
    rows.push(['Amortization', `${escapeHtml(m.lifespan_years)} years × 8,760 h = ${hours} bookable h (fully booked)`]);
    rows.push(['Hardware wear', `${eurStr(ph.hardware_wear_eur, 4)} / h`]);
    rows.push(['Electricity', `${escapeHtml(String(m.wall_watts))} W × ${eurStr(m.eur_per_kwh, 2)}/kWh = ${eurStr(ph.electricity_eur, 4)} / h`]);
    rows.push(['Cost per compute-hour', eurStr(ph.cost_eur, 4)]);
    const margin = ph.margin_on_cost_pct != null ? ` (margin ${eurStr(ph.margin_eur, 4)} / h, +${Number(ph.margin_on_cost_pct).toFixed(1)}%)` : '';
    rows.push(['Reference price', `${eurStr(ph.price_eur, 2)}${margin} — ${escapeHtml(m.ait_per_eur)} AIT/EUR`]);

    tbody.innerHTML = rows
        .map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`)
        .join('');
}

// A read that fails must never leave the HTML placeholder ("...",
// "loading...") on screen — it reads as "still loading" forever. Track the
// last good read per widget: first failure says unavailable; a failure
// after a good read keeps the value and marks it stale.
let heroLastGoodAt = null;
let tickerLastGoodAt = null;

function markStale(el, lastGoodAt, unavailableText) {
    if (!el) return;
    if (lastGoodAt) {
        // Render from the recorded good text — appending to textContent
        // would pile one "(stale …)" on the element per failed poll.
        el.textContent = `${el.dataset.lastGood || el.textContent} (stale, last read ${aitbcFmt.time(lastGoodAt)})`;
    } else {
        el.textContent = unavailableText;
    }
}

async function fetchPrices() {
    try {
        const response = await fetch('/v1/exchange/history');
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'Failed to fetch prices');
        updateHeroPrice(data);
        heroLastGoodAt = Date.now();
    } catch (error) {
        console.error('Error fetching prices:', error);
        const reason = 'price unavailable (' + errReason(error) + ')';
        markStale(document.getElementById('hero-eth-equivalent'), heroLastGoodAt, reason);
        markStale(document.getElementById('hero-eth-rate'), heroLastGoodAt, reason);
    }
}

function updateHeroPrice(data) {
    const c = data.current;

    // Reference value: 1 AIT = refEur (compute-backed, from reference.json)
    const REF_EUR = refEur;
    const ethEur = c.eth_eur != null ? Number(c.eth_eur) : null;
    const ethUsd = c.eth_usd != null ? Number(c.eth_usd) : null;

    // Derive USD and ETH from the €0.25 reference using live ETH prices
    const aitUsd = (ethEur && ethUsd) ? REF_EUR * ethUsd / ethEur : null;
    const aitEth = ethEur ? REF_EUR / ethEur : null;

    // Update hero card: ETH equivalent of the €0.25 reference value
    const heroEth = document.getElementById('hero-eth-equivalent');
    if (heroEth && aitEth != null) {
        heroEth.dataset.lastGood = `≈ ${aitEth.toFixed(6)} ETH`;
        heroEth.textContent = heroEth.dataset.lastGood;
    }

    // And the inverse: how many AIT 1 ETH buys (eth_eur / 0.25)
    const heroRate = document.getElementById('hero-eth-rate');
    if (heroRate && ethEur) {
        const aitPerEth = ethEur / REF_EUR;
        heroRate.dataset.lastGood = `1 ETH ≈ ${Math.round(aitPerEth).toLocaleString('en-US')} AIT`;
        heroRate.textContent = heroRate.dataset.lastGood;
    }
}

async function updatePriceTicker() {
    const ticker = document.getElementById('price-ticker');
    try {
        const response = await fetch('/exchange/price.json');
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const data = await response.json();
        if (!ticker) return;
        if (data.error) {
            ticker.textContent = 'price unavailable' + (data.error ? ' — ' + String(data.error) : '');
            return;
        }
        const usd = data.price_usd != null ? `$${Number(data.price_usd).toFixed(4)}` : null;
        const eur = data.price_eur != null ? `&euro;${Number(data.price_eur).toFixed(2)}` : null;
        const eth = data.price_eth != null ? `${Number(data.price_eth).toFixed(6)} ETH` : null;
        const parts = [eur, usd, eth].filter(p => p !== null);
        ticker.dataset.lastGood = parts.join(' | ');
        ticker.innerHTML = parts.join(' &nbsp;|&nbsp; ');
        tickerLastGoodAt = Date.now();
    } catch (error) {
        console.error('Error fetching price ticker:', error);
        markStale(ticker, tickerLastGoodAt, 'price unavailable (' + errReason(error) + ')');
    }
}

function bridgeFailReason(resp, err) {
    if (resp) return 'HTTP ' + resp.status;
    if (err && err.name === 'SyntaxError') return 'reply was not readable';
    return 'network request failed';
}

// Failure wording shared by the page's reads: status codes as "HTTP n",
// broken connections as "network request failed", unreadable bodies named
// as such — never raw upstream text injected verbatim into markup.
function errReason(err) {
    if (err && /^HTTP \d+$/.test(err.message)) return err.message;
    if (err && err.name === 'SyntaxError') return 'reply was not readable';
    if (err && err.name === 'TypeError') return 'network request failed';
    return (err && err.message) ? String(err.message) : 'request failed';
}

// The page-level claim about the bridge: four states through one render
// path, re-read every 60 s. Green only on a proven "bridge is on" reply —
// a failed, unreadable or non-proving answer is unknown, never ready.
function renderBridgeBanner(state, detailText) {
    const banner = document.getElementById('bridge-health');
    if (!banner) return;
    const map = {
        loading: ['is-loading', 'Checking bridge...'],
        ready:   ['is-healthy', 'Bridge ready'],
        off:     ['is-attention', 'Bridge off'],
        unknown: ['is-unknown', 'Bridge state unknown'],
    };
    const [cls, titleText] = map[state] || map.unknown;
    banner.className = `bridge-health ${cls}`;
    const title = banner.querySelector('.bridge-health-title');
    const detail = banner.querySelector('.bridge-health-detail');
    if (title) title.textContent = titleText;
    if (detail) detail.textContent = detailText || '';
}

// The deposit form stays visible but inert when the bridge is not proven
// on: inputs and the primary button disabled, the reason beside the form
// (aria-describedby), and Try again re-reads the status.
function setDepositFormEnabled(enabled, reason) {
    for (const id of ['eth-amount', 'ait-address', 'calculate-deposit-btn']) {
        const ctrl = document.getElementById(id);
        if (!ctrl) continue;
        ctrl.disabled = !enabled;
        if (enabled) ctrl.removeAttribute('aria-describedby');
        else ctrl.setAttribute('aria-describedby', 'bridge-offline-note');
    }
    const noteEl = document.getElementById('bridge-offline-note');
    if (noteEl) {
        noteEl.style.display = enabled ? 'none' : 'block';
        noteEl.textContent = enabled ? '' : reason;
    }
    const retryEl = document.getElementById('bridge-retry-btn');
    if (retryEl) retryEl.style.display = enabled ? 'none' : '';
}

async function fetchBridgeStatus() {
    let resp = null;
    let data = null;
    let unreadable = false;
    try {
        resp = await fetch('/v1/bridge/status');
        if (resp.ok) {
            try { data = await resp.json(); } catch (e) { unreadable = true; }
        }
    } catch (error) {
        console.error('Error fetching bridge status:', error);
    }

    const el = document.getElementById('bridge-status-text');
    // The deposit form is offered only on a proven "bridge is on" reply —
    // the healthy shape carries status:"ready" + enabled:true (see Phase 0).
    const proven = !!(resp && resp.ok && data && typeof data === 'object' && data.status === 'ready' && data.enabled === true);
    const off = !!(resp && resp.ok && data && data.enabled === false);

    if (data && data.deposit_address) {
        const depositEl = document.getElementById('deposit-address');
        if (depositEl) {
            depositEl.textContent = data.deposit_address;
        }
    }

    if (proven) {
        const bits = [];
        if (data.fee_rate != null) bits.push(`fee ${(Number(data.fee_rate) * 100).toFixed(1)}%`);
        if (data.min_deposit != null) bits.push(`min ${data.min_deposit} ETH`);
        if (data.network != null) bits.push(String(data.network));
        renderBridgeBanner('ready', bits.join(' · '));
        if (el) el.textContent = `${data.status} — ${data.message || ''}`;
        setDepositFormEnabled(true, null);
    } else if (off) {
        const msg = data.message || 'The bridge reports deposits are disabled.';
        renderBridgeBanner('off', msg);
        if (el) el.textContent = `${data.status || 'unknown'} — ${data.message || ''}`;
        setDepositFormEnabled(false, 'The bridge reports deposits are disabled.');
    } else {
        const reason = !resp
            ? 'network request failed'
            : !resp.ok
                ? `HTTP ${resp.status}`
                : (unreadable || !data ? 'reply was not readable' : 'reply did not prove the bridge is on');
        renderBridgeBanner('unknown', `${reason} — checks again every 60 s`);
        if (el) el.textContent = `unknown — ${reason}`;
        setDepositFormEnabled(false, 'Deposits are unavailable while the bridge state is unknown.');
    }
}

// ─── Wallet integration (EIP-1193 / MetaMask) ───
let connectedAccount = null;
let lastEstimate = null;  // cached estimate for sendBridgeTransaction

async function connectWallet() {
    if (!window.ethereum) return;
    try {
        const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
        connectedAccount = accounts[0];
        showConnectedAccount(connectedAccount);
    } catch (error) {
        console.error('Wallet connection failed:', error);
        const errEl = document.getElementById('deposit-error');
        if (errEl) {
            errEl.style.display = 'block';
            errEl.textContent = 'Wallet connection rejected or failed';
        }
    }
}

function showConnectedAccount(account) {
    const span = document.getElementById('connected-account');
    if (span && account) {
        span.textContent = `${account.slice(0, 6)}...${account.slice(-4)}`;
        span.setAttribute('aria-label', account);
        const copyAccountBtn = document.getElementById('copy-account-btn');
        if (copyAccountBtn) copyAccountBtn.dataset.copy = account;
    }
    const buyBtn = document.getElementById('buy-with-eth-btn');
    if (buyBtn && lastEstimate) {
        buyBtn.style.display = 'block';
    }
}

async function sendBridgeTransaction() {
    if (!window.ethereum || !connectedAccount || !lastEstimate) return;
    const errEl = document.getElementById('deposit-error');
    if (errEl) errEl.style.display = 'none';

    const { instructions, estimate } = lastEstimate;
    const ethAmount = estimate.eth_amount;
    // Convert ETH to wei (hex string)
    const weiValue = BigInt(Math.floor(ethAmount * 1e18)).toString(16);

    const txParams = {
        from: connectedAccount,
        to: instructions.send_eth_to,
        value: '0x' + weiValue,
        data: instructions.transaction_data_hex,
    };

    try {
        const txHash = await window.ethereum.request({
            method: 'eth_sendTransaction',
            params: [txParams],
        });
        const resultEl = document.getElementById('deposit-tx-result');
        const hashEl = document.getElementById('eth-tx-hash');
        if (resultEl && hashEl) {
            hashEl.textContent = txHash;
            resultEl.style.display = 'block';
        }
    } catch (error) {
        console.error('Send transaction failed:', error);
        if (errEl) {
            errEl.style.display = 'block';
            errEl.textContent = error.message || 'Transaction rejected or failed';
        }
    }
}

async function calculateDeposit() {
    const ethAmount = document.getElementById('eth-amount').value;
    const aitAddress = document.getElementById('ait-address').value;

    document.getElementById('deposit-estimate').style.display = 'none';
    document.getElementById('deposit-error').style.display = 'none';
    document.getElementById('deposit-instructions').style.display = 'none';
    document.getElementById('deposit-tx-result').style.display = 'none';

    if (!ethAmount || !aitAddress) {
        const errEl = document.getElementById('deposit-error');
        errEl.style.display = 'block';
        errEl.textContent = 'Please enter both ETH amount and AIT address';
        return;
    }

    try {
        const response = await fetch('/v1/bridge/deposit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ eth_amount: parseFloat(ethAmount), ait_address: aitAddress })
        });

        const data = await response.json();

        if (response.ok && data.status === 'ready') {
            lastEstimate = data;
            document.getElementById('deposit-estimate').style.display = 'block';
            document.getElementById('estimated-ait').textContent = data.estimate.estimated_ait_amount || '-';
            document.getElementById('estimate-address').textContent = data.estimate.ait_recipient || '-';
            document.getElementById('est-eth').textContent = data.estimate.eth_amount || '-';
            document.getElementById('fee-eth').textContent = data.estimate.fee_eth || '-';
            document.getElementById('net-eth').textContent = data.estimate.net_eth || '-';
            document.getElementById('eth-usd').textContent = data.estimate.eth_usd_price || '-';
            document.getElementById('ait-usd').textContent = data.estimate.ait_usd_price || '-';

            // Show buy button if wallet connected, otherwise manual instructions
            if (window.ethereum && connectedAccount) {
                document.getElementById('buy-with-eth-btn').style.display = 'block';
            } else {
                document.getElementById('deposit-instructions').style.display = 'block';
                document.getElementById('deposit-address').textContent = data.instructions.send_eth_to;
                document.getElementById('instruction-eth-amount').textContent = data.instructions.amount_eth;
                document.getElementById('tx-data-hex').textContent = data.instructions.transaction_data_hex || '';
                document.getElementById('min-deposit').textContent = data.instructions.min_deposit;
            }
        } else {
            const errEl = document.getElementById('deposit-error');
            errEl.style.display = 'block';
            errEl.textContent = data.error || data.message || 'Failed to calculate deposit';
        }
    } catch (error) {
        console.error('Error calculating deposit:', error);
        const errEl = document.getElementById('deposit-error');
        errEl.style.display = 'block';
        errEl.textContent = 'Failed to connect to server';
    }
}

// ─── Deposit status tracking ───
let trackPollHandle = null;

function statusBadge(status) {
    const cls = status === 'completed' ? 'status-ok'
        : status === 'failed' ? 'status-bad'
        : 'status-pending';
    return `<span class="status-badge ${cls}">${escapeHtml(String(status).toUpperCase())}</span>`;
}

function renderDeposit(deposit) {
    const resultEl = document.getElementById('track-result');
    if (!resultEl) return;
    const aitTxLink = deposit.ait_tx_hash
        ? `<a href="/tx.html?hash=${encodeURIComponent(deposit.ait_tx_hash)}" class="deposit-address" target="_blank" rel="noopener noreferrer" aria-label="AIT transaction ${escapeHtml(deposit.ait_tx_hash)}">${escapeHtml(deposit.ait_tx_hash.slice(0, 18))}...</a> ${aitbcCopyBtn(deposit.ait_tx_hash, 'transaction hash')}`
        : '<span class="muted-text">pending</span>';
    const errLine = deposit.status === 'failed' && deposit.error_message
        ? `<p class="error-box" style="margin-top:0.5rem;">${escapeHtml(deposit.error_message)}</p>`
        : '';
    const fromShort = deposit.eth_from_address
        ? `<span aria-hidden="true">${escapeHtml(deposit.eth_from_address.slice(0, 6))}...${escapeHtml(deposit.eth_from_address.slice(-4))}</span><span class="visually-hidden">${escapeHtml(deposit.eth_from_address)}</span> ${aitbcCopyBtn(deposit.eth_from_address, 'sender address')}`
        : '-';
    resultEl.innerHTML = `
        <p><strong>Status:</strong> ${statusBadge(deposit.status)}</p>
        <p><strong>ETH amount:</strong> ${escapeHtml(deposit.eth_amount || '-')} ETH</p>
        <p><strong>AIT amount:</strong> ${escapeHtml(deposit.ait_amount || '-')} AIT</p>
        <p><strong>From:</strong> <span style="font-family:var(--font-mono);">${fromShort}</span></p>
        <p><strong>AIT recipient:</strong> <span style="font-family:var(--font-mono);">${escapeHtml(deposit.ait_recipient || '-')}</span></p>
        <p><strong>AIT tx:</strong> ${aitTxLink}</p>
        <p class="muted-text">Created: ${escapeHtml(deposit.created_at || '-')} &middot; Processed: ${escapeHtml(deposit.processed_at || '-')}</p>
        ${errLine}
    `;
    resultEl.style.display = 'block';
}

async function trackDeposit() {
    const input = document.getElementById('track-input').value.trim();
    const errEl = document.getElementById('track-error');
    const resultEl = document.getElementById('track-result');
    errEl.style.display = 'none';
    resultEl.style.display = 'none';
    setTrackRetry(false);

    if (trackPollHandle) { clearInterval(trackPollHandle); trackPollHandle = null; }

    if (!input) {
        errEl.style.display = 'block';
        errEl.textContent = 'Enter a 0x ETH tx hash (66 chars) or 0x AIT address (42 chars)';
        return;
    }

    // Kick the bridge monitor: on-demand burst (~3 polls over 60s) instead of
    // waiting for the slow background cadence. Fire-and-forget — tracking
    // works off the deposit records regardless of whether the kick lands.
    fetch('/v1/bridge/poll-request', { method: 'POST' }).catch(() => {});

    await lookupDeposit(input);

    // Poll if status is non-terminal
    const status = resultEl.dataset.status;
    if (status === 'pending' || status === 'processing') {
        trackPollHandle = setInterval(() => lookupDeposit(input), 10000);
    }
}

// The track card's Try again button belongs to a could-not-query answer
// only — it must not outlive its error line on later poll outcomes.
function setTrackRetry(visible) {
    const btn = document.getElementById('track-retry-btn');
    if (btn) btn.style.display = visible ? '' : 'none';
}

async function lookupDeposit(input) {
    const errEl = document.getElementById('track-error');
    const resultEl = document.getElementById('track-result');

    try {
        let deposit = null;
        const queryFailed = (resp) => {
            errEl.style.display = 'block';
            errEl.textContent = `Could not query deposit status (HTTP ${resp.status}). This is not a "not found".`;
            setTrackRetry(true);
            // A failed poll keeps the last shown deposit — hide the result
            // only when none was ever shown.
        };
        if (input.startsWith('0x') && input.length === 66) {
            // Lookup by ETH tx hash (0x + 64 hex)
            const resp = await fetch(`/v1/bridge/deposit/${encodeURIComponent(input)}`);
            if (resp.ok) {
                deposit = await resp.json();
            } else if (resp.status === 404) {
                errEl.style.display = 'block';
                errEl.textContent = 'Deposit not found for this tx hash';
                resultEl.style.display = 'none';
                setTrackRetry(false);
                return;
            } else {
                queryFailed(resp);
                return;
            }
        } else if (input.startsWith('0x') && input.length === 42) {
            // Lookup by AIT address (0x + 40 hex) — non-enumerable per-recipient
            // endpoint; the enumerable /v1/bridge/deposits index is loopback-only.
            const resp = await fetch(`/v1/bridge/deposit/by-recipient/${encodeURIComponent(input)}`);
            if (resp.ok) {
                const data = await resp.json();
                deposit = (data.deposits || [])[0] || null;
                if (!deposit) {
                    errEl.style.display = 'block';
                    errEl.textContent = 'No deposit found for this AIT address';
                    resultEl.style.display = 'none';
                    setTrackRetry(false);
                    return;
                }
            } else if (resp.status === 404) {
                errEl.style.display = 'block';
                errEl.textContent = 'No deposit found for this AIT address';
                resultEl.style.display = 'none';
                setTrackRetry(false);
                return;
            } else {
                queryFailed(resp);
                return;
            }
        } else {
            errEl.style.display = 'block';
            errEl.textContent = 'Enter a 0x ETH tx hash (66 chars) or 0x AIT address (42 chars)';
            resultEl.style.display = 'none';
            setTrackRetry(false);
            return;
        }

        if (deposit) {
            // Normalize: detail endpoint returns a Row dict, list returns plain dict
            const d = deposit.dict ? deposit.dict() : deposit;
            resultEl.dataset.status = d.status;
            errEl.style.display = 'none';   // a good poll clears a prior failure line
            setTrackRetry(false);
            renderDeposit(d);
            // Stop polling if terminal
            if (d.status === 'completed' || d.status === 'failed') {
                if (trackPollHandle) { clearInterval(trackPollHandle); trackPollHandle = null; }
            }
        }
    } catch (error) {
        console.error('Error tracking deposit:', error);
        errEl.style.display = 'block';
        errEl.textContent = `Could not query deposit status (${errReason(error)}). This is not a "not found".`;
        setTrackRetry(true);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    fetchReference().finally(fetchPrices);
    fetchBridgeStatus();
    // The banner says "checks again every 60 s" — keep that claim true.
    setInterval(fetchBridgeStatus, 60000);
    updatePriceTicker();
    setInterval(updatePriceTicker, 60000);

    // Wallet detection
    if (window.ethereum) {
        document.getElementById('wallet-connect-row').style.display = 'flex';
        // Auto-reconnect if already authorized
        window.ethereum.request({ method: 'eth_accounts' }).then(accounts => {
            if (accounts.length > 0) {
                connectedAccount = accounts[0];
                showConnectedAccount(connectedAccount);
            }
        }).catch(() => {});
        // Listen for account changes
        window.ethereum.on?.('accountsChanged', (accounts) => {
            connectedAccount = accounts[0] || null;
            showConnectedAccount(connectedAccount);
        });
    }

    const calcBtn = document.getElementById('calculate-deposit-btn');
    if (calcBtn) calcBtn.addEventListener('click', calculateDeposit);

    const connectBtn = document.getElementById('connect-wallet-btn');
    if (connectBtn) connectBtn.addEventListener('click', connectWallet);

    const buyBtn = document.getElementById('buy-with-eth-btn');
    if (buyBtn) buyBtn.addEventListener('click', sendBridgeTransaction);



    const trackBtn = document.getElementById('track-deposit-btn');
    if (trackBtn) trackBtn.addEventListener('click', trackDeposit);

    const retryBtn = document.getElementById('bridge-retry-btn');
    if (retryBtn) retryBtn.addEventListener('click', fetchBridgeStatus);

    const trackRetryBtn = document.getElementById('track-retry-btn');
    if (trackRetryBtn) trackRetryBtn.addEventListener('click', trackDeposit);
});
