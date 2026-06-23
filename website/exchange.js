async function fetchPrices() {
    try {
        const response = await fetch('/v1/exchange/history');
        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'Failed to fetch prices');
        updateHeroPrice(data);
    } catch (error) {
        console.error('Error fetching prices:', error);
    }
}

function updateHeroPrice(data) {
    const c = data.current;

    // Reference value: 1 AIT = €0.25 (compute-backed)
    const REF_EUR = 0.25;
    const ethEur = c.eth_eur != null ? Number(c.eth_eur) : null;
    const ethUsd = c.eth_usd != null ? Number(c.eth_usd) : null;

    // Derive USD and ETH from the €0.25 reference using live ETH prices
    const aitUsd = (ethEur && ethUsd) ? REF_EUR * ethUsd / ethEur : null;
    const aitEth = ethEur ? REF_EUR / ethEur : null;

    // Update hero card: ETH equivalent of the €0.25 reference value
    const heroEth = document.getElementById('hero-eth-equivalent');
    if (heroEth && aitEth != null) {
        heroEth.innerHTML = `&asymp; ${aitEth.toFixed(6)} ETH`;
    }
}

async function updatePriceTicker() {
    try {
        const response = await fetch('/exchange/price.json');
        if (!response.ok) return;
        const data = await response.json();
        const ticker = document.getElementById('price-ticker');
        if (!ticker) return;
        if (data.error) {
            ticker.textContent = 'price unavailable';
            return;
        }
        const usd = data.price_usd != null ? `$${Number(data.price_usd).toFixed(4)}` : null;
        const eur = data.price_eur != null ? `&euro;${Number(data.price_eur).toFixed(2)}` : null;
        const eth = data.price_eth != null ? `${Number(data.price_eth).toFixed(6)} ETH` : null;
        const parts = [eur, usd, eth].filter(p => p !== null);
        ticker.innerHTML = parts.join(' &nbsp;|&nbsp; ');
    } catch (error) {
        console.error('Error fetching price ticker:', error);
    }
}

async function fetchBridgeStatus() {
    try {
        const response = await fetch('/v1/bridge/status');
        const data = await response.json();
        const el = document.getElementById('bridge-status-text');
        if (el) {
            el.textContent = `${data.status || 'unknown'} — ${data.message || ''}`;
        }
        if (data.deposit_address) {
            const depositEl = document.getElementById('deposit-address');
            if (depositEl) {
                depositEl.textContent = data.deposit_address;
            }
        }
    } catch (error) {
        console.error('Error fetching bridge status:', error);
        const el = document.getElementById('bridge-status-text');
        if (el) el.textContent = 'Failed to load';
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

function copyAddress() {
    const addressElement = document.getElementById('deposit-address');
    const address = addressElement ? addressElement.textContent : '';
    if (!address || address === 'Loading...') return;
    navigator.clipboard.writeText(address).then(() => {
        const feedback = document.getElementById('copy-feedback');
        feedback.style.display = 'block';
        setTimeout(() => { feedback.style.display = 'none'; }, 2000);
    }).catch(err => console.error('Failed to copy:', err));
}

function copyTxDataHex() {
    const hexElement = document.getElementById('tx-data-hex');
    const hex = hexElement ? hexElement.textContent : '';
    if (!hex || hex === '-') return;
    navigator.clipboard.writeText(hex).then(() => {
        const feedback = document.getElementById('copy-feedback-hex');
        feedback.style.display = 'block';
        setTimeout(() => { feedback.style.display = 'none'; }, 2000);
    }).catch(err => console.error('Failed to copy hex:', err));
}

// ─── Deposit status tracking ───
let trackPollHandle = null;

function statusBadge(status) {
    const cls = status === 'completed' ? 'status-ok'
        : status === 'failed' ? 'status-bad'
        : 'status-pending';
    return `<span class="status-badge ${cls}">${status.toUpperCase()}</span>`;
}

function renderDeposit(deposit) {
    const resultEl = document.getElementById('track-result');
    if (!resultEl) return;
    const aitTxLink = deposit.ait_tx_hash
        ? `<a href="/tx.html?hash=${encodeURIComponent(deposit.ait_tx_hash)}" class="deposit-address" target="_blank" rel="noopener">${deposit.ait_tx_hash.slice(0, 18)}...</a>`
        : '<span class="muted-text">pending</span>';
    const errLine = deposit.status === 'failed' && deposit.error_message
        ? `<p class="error-box" style="margin-top:0.5rem;">${deposit.error_message}</p>`
        : '';
    const fromShort = deposit.eth_from_address
        ? `${deposit.eth_from_address.slice(0, 6)}...${deposit.eth_from_address.slice(-4)}`
        : '-';
    resultEl.innerHTML = `
        <p><strong>Status:</strong> ${statusBadge(deposit.status)}</p>
        <p><strong>ETH amount:</strong> ${deposit.eth_amount || '-'} ETH</p>
        <p><strong>AIT amount:</strong> ${deposit.ait_amount || '-'} AIT</p>
        <p><strong>From:</strong> <span style="font-family:var(--font-mono);">${fromShort}</span></p>
        <p><strong>AIT recipient:</strong> <span style="font-family:var(--font-mono);">${deposit.ait_recipient || '-'}</span></p>
        <p><strong>AIT tx:</strong> ${aitTxLink}</p>
        <p class="muted-text">Created: ${deposit.created_at || '-'} &middot; Processed: ${deposit.processed_at || '-'}</p>
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

    if (trackPollHandle) { clearInterval(trackPollHandle); trackPollHandle = null; }

    if (!input) {
        errEl.style.display = 'block';
        errEl.textContent = 'Enter an ETH tx hash or AIT address';
        return;
    }

    await lookupDeposit(input);

    // Poll if status is non-terminal
    const status = resultEl.dataset.status;
    if (status === 'pending' || status === 'processing') {
        trackPollHandle = setInterval(() => lookupDeposit(input), 10000);
    }
}

async function lookupDeposit(input) {
    const errEl = document.getElementById('track-error');
    const resultEl = document.getElementById('track-result');

    try {
        let deposit = null;
        if (input.startsWith('0x')) {
            // Lookup by ETH tx hash
            const resp = await fetch(`/v1/bridge/deposit/${encodeURIComponent(input)}`);
            if (resp.ok) {
                deposit = await resp.json();
            } else if (resp.status === 404) {
                errEl.style.display = 'block';
                errEl.textContent = 'Deposit not found for this tx hash';
                resultEl.style.display = 'none';
                return;
            }
        } else {
            // Lookup by AIT address — filter deposits list
            const resp = await fetch('/v1/bridge/deposits?limit=50');
            if (resp.ok) {
                const data = await resp.json();
                deposit = (data.deposits || []).find(d => d.ait_recipient === input) || null;
            }
            if (!deposit) {
                errEl.style.display = 'block';
                errEl.textContent = 'No deposit found for this AIT address';
                resultEl.style.display = 'none';
                return;
            }
        }

        if (deposit) {
            // Normalize: detail endpoint returns a Row dict, list returns plain dict
            const d = deposit.dict ? deposit.dict() : deposit;
            resultEl.dataset.status = d.status;
            renderDeposit(d);
            // Stop polling if terminal
            if (d.status === 'completed' || d.status === 'failed') {
                if (trackPollHandle) { clearInterval(trackPollHandle); trackPollHandle = null; }
            }
        }
    } catch (error) {
        console.error('Error tracking deposit:', error);
        errEl.style.display = 'block';
        errEl.textContent = 'Failed to query deposit status';
    }
}

document.addEventListener('DOMContentLoaded', function() {
    fetchPrices();
    fetchBridgeStatus();
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

    const depositBox = document.getElementById('deposit-address-box');
    if (depositBox) depositBox.addEventListener('click', copyAddress);

    const hexBox = document.getElementById('tx-data-hex-box');
    if (hexBox) hexBox.addEventListener('click', copyTxDataHex);

    const trackBtn = document.getElementById('track-deposit-btn');
    if (trackBtn) trackBtn.addEventListener('click', trackDeposit);
});
