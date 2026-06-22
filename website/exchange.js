async function fetchPrices() {
    try {
        const response = await fetch('/v1/exchange/history');
        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'Failed to fetch prices');
        updatePrices(data);
    } catch (error) {
        console.error('Error fetching prices:', error);
        const el = document.getElementById('live-prices');
        if (el) el.innerHTML = '<p class="error">Failed to load prices</p>';
    }
}

function updatePrices(data) {
    const c = data.current;

    // Reference value: 1 AIT = €0.25 (compute-backed)
    const REF_EUR = 0.25;
    const ethEur = c.eth_eur != null ? Number(c.eth_eur) : null;
    const ethUsd = c.eth_usd != null ? Number(c.eth_usd) : null;

    // Derive USD and ETH from the €0.25 reference using live ETH prices
    const aitUsd = (ethEur && ethUsd) ? REF_EUR * ethUsd / ethEur : null;
    const aitEth = ethEur ? REF_EUR / ethEur : null;
    const ethPerAit = aitEth ? (1 / aitEth) : null;  // 1 ETH = X AIT

    // Update hero card: ETH equivalent of the €0.25 reference value
    const heroEth = document.getElementById('hero-eth-equivalent');
    if (heroEth && aitEth != null) {
        heroEth.innerHTML = `&asymp; ${aitEth.toFixed(6)} ETH`;
    }

    // Update live-prices section if present
    const el = document.getElementById('live-prices');
    if (!el) return;

    let html = '<div class="price-grid-3">';

    // AIT/EUR (reference)
    html += `<div class="price-cell">
        <p class="price-label">1 AIT</p>
        <p class="price-value">&euro;${REF_EUR.toFixed(2)}</p>
        <p class="price-unit">EUR (reference)</p>
    </div>`;

    // AIT/USD (derived)
    if (aitUsd != null) {
        html += `<div class="price-cell">
            <p class="price-label">1 AIT</p>
            <p class="price-value">$${aitUsd.toFixed(4)}</p>
            <p class="price-unit">USD (derived)</p>
        </div>`;
    }

    // AIT/ETH (derived)
    if (aitEth != null) {
        html += `<div class="price-cell">
            <p class="price-label">1 AIT</p>
            <p class="price-value">${aitEth.toFixed(6)}</p>
            <p class="price-unit">ETH (derived)</p>
        </div>`;
    }

    html += '</div>';

    // ETH/AIT rate
    if (ethPerAit != null) {
        html += `<p class="muted-text" style="margin-top:1rem;">1 ETH &asymp; ${Math.round(ethPerAit).toLocaleString()} AIT</p>`;
    }

    // ETH prices for context
    html += '<div class="grid" style="margin-top:0.5rem;">';
    if (ethUsd != null) {
        html += `<p class="muted-text">ETH: $${ethUsd.toFixed(2)} USD</p>`;
    }
    if (ethEur != null) {
        html += `<p class="muted-text">ETH: &euro;${ethEur.toFixed(2)} EUR</p>`;
    }
    html += '</div>';

    el.innerHTML = html;

    if (c.timestamp) {
        const tsEl = document.getElementById('price-last-updated');
        if (tsEl) tsEl.textContent = `Last updated: ${new Date(c.timestamp * 1000).toLocaleString()}`;
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

async function calculateDeposit() {
    const ethAmount = document.getElementById('eth-amount').value;
    const aitAddress = document.getElementById('ait-address').value;

    document.getElementById('deposit-estimate').style.display = 'none';
    document.getElementById('deposit-error').style.display = 'none';
    document.getElementById('deposit-instructions').style.display = 'none';

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
            document.getElementById('deposit-estimate').style.display = 'block';
            document.getElementById('estimated-ait').textContent = data.estimate.estimated_ait_amount || '-';
            document.getElementById('estimate-address').textContent = data.estimate.ait_recipient || '-';
            document.getElementById('est-eth').textContent = data.estimate.eth_amount || '-';
            document.getElementById('fee-eth').textContent = data.estimate.fee_eth || '-';
            document.getElementById('net-eth').textContent = data.estimate.net_eth || '-';
            document.getElementById('eth-usd').textContent = data.estimate.eth_usd_price || '-';
            document.getElementById('ait-usd').textContent = data.estimate.ait_usd_price || '-';

            document.getElementById('deposit-instructions').style.display = 'block';
            document.getElementById('deposit-address').textContent = data.instructions.send_eth_to;
            document.getElementById('instruction-eth-amount').textContent = data.instructions.amount_eth;
            document.getElementById('instruction-ait-address').textContent = data.instructions.transaction_data || aitAddress;
            document.getElementById('min-deposit').textContent = data.instructions.min_deposit;
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

document.addEventListener('DOMContentLoaded', function() {
    fetchPrices();
    fetchBridgeStatus();

    const calcBtn = document.getElementById('calculate-deposit-btn');
    if (calcBtn) calcBtn.addEventListener('click', calculateDeposit);

    const depositBox = document.getElementById('deposit-address-box');
    if (depositBox) depositBox.addEventListener('click', copyAddress);
});
