async function fetchPrices() {
    try {
        const response = await fetch('http://hub.aitbc.bubuit.net/v1/exchange/history');
        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || 'Failed to fetch prices');
        }

        updatePrices(data);
    } catch (error) {
        console.error('Error fetching prices:', error);
        document.getElementById('usd-prices').innerHTML = '<p class="error">Failed to load prices</p>';
        document.getElementById('eur-prices').innerHTML = '<p class="error">Failed to load prices</p>';
    }
}

async function fetchBridgeStatus() {
    try {
        const response = await fetch('http://hub.aitbc.bubuit.net/v1/bridge/status');
        const data = await response.json();

        updateBridgeStatus(data);

        // Update deposit address if available
        if (data.deposit_address) {
            const depositEl = document.getElementById('deposit-address');
            if (depositEl) {
                depositEl.textContent = data.deposit_address;
            }
        }
    } catch (error) {
        console.error('Error fetching bridge status:', error);
        document.getElementById('bridge-status').innerHTML = '<p class="error">Failed to load bridge status</p>';
    }
}

function updatePrices(data) {
    const current = data.current;
    const averages = data.averages;
    const change = data.change_vs_average;

    // Update USD prices
    let usdHtml = '';
    if (current.eth_usd) {
        usdHtml += `<p><strong>ETH Price:</strong> $${current.eth_usd.toFixed(2)} USD</p>`;
    }
    if (current.ait_usd) {
        usdHtml += `<p><strong>AIT Price:</strong> $${current.ait_usd.toFixed(6)} USD</p>`;
    }

    if (averages) {
        const changeClass = change.eth_usd_percent >= 0 ? 'price-up' : 'price-down';
        const arrow = change.eth_usd_percent >= 0 ? '↑' : '↓';
        usdHtml += `<p><strong>All-Time Average:</strong> $${averages.eth_usd.toFixed(2)} USD</p>`;
        usdHtml += `<p><strong>vs Average:</strong> <span class="${changeClass}">${Math.abs(change.eth_usd_percent).toFixed(2)}% ${arrow}</span></p>`;
    }

    document.getElementById('usd-prices').innerHTML = usdHtml;

    // Update EUR prices
    let eurHtml = '';
    if (current.eth_eur) {
        eurHtml += `<p><strong>ETH Price:</strong> €${current.eth_eur.toFixed(2)} EUR</p>`;
    }
    if (current.ait_eur) {
        eurHtml += `<p><strong>AIT Price:</strong> €${current.ait_eur.toFixed(6)} EUR</p>`;
    }

    if (averages) {
        const changeClass = change.eth_eur_percent >= 0 ? 'price-up' : 'price-down';
        const arrow = change.eth_eur_percent >= 0 ? '↑' : '↓';
        eurHtml += `<p><strong>All-Time Average:</strong> €${averages.eth_eur.toFixed(2)} EUR</p>`;
        eurHtml += `<p><strong>vs Average:</strong> <span class="${changeClass}">${Math.abs(change.eth_eur_percent).toFixed(2)}% ${arrow}</span></p>`;
    }

    document.getElementById('eur-prices').innerHTML = eurHtml;

    // Update exchange rate (top section)
    const exchangeRateElement = document.getElementById('exchange-rate');
    if (exchangeRateElement && current.eth_ait_rate_usd) {
        exchangeRateElement.innerHTML = `<p><strong>1 ETH = ${current.eth_ait_rate_usd.toFixed(2)} AIT</strong></p>`;
    }

    // Update timestamp
    if (current.timestamp) {
        document.getElementById('last-updated').textContent = `Last updated: ${new Date(current.timestamp * 1000).toLocaleString()}`;
    }
}

function updateBridgeStatus(data) {
    let statusHtml = '';
    statusHtml += `<p><strong>Bridge:</strong> ${data.bridge}</p>`;
    statusHtml += `<p><strong>Status:</strong> ${data.status}</p>`;
    statusHtml += `<p><strong>Contract:</strong> ${data.contract_address || 'N/A'}</p>`;
    statusHtml += `<p><strong>Message:</strong> ${data.message}</p>`;

    document.getElementById('bridge-status').innerHTML = statusHtml;
}

async function calculateDeposit() {
    const ethAmount = document.getElementById('eth-amount').value;
    const aitAddress = document.getElementById('ait-address').value;

    // Hide previous results
    document.getElementById('deposit-estimate').style.display = 'none';
    document.getElementById('deposit-error').style.display = 'none';
    document.getElementById('deposit-instructions').style.display = 'none';

    if (!ethAmount || !aitAddress) {
        document.getElementById('deposit-error').style.display = 'block';
        document.getElementById('deposit-error').textContent = 'Please enter both ETH amount and AIT address';
        return;
    }

    try {
        const response = await fetch('/v1/bridge/deposit', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                eth_amount: parseFloat(ethAmount),
                ait_address: aitAddress
            })
        });

        const data = await response.json();

        if (response.ok && data.status === 'ready') {
            // Show estimates
            document.getElementById('deposit-estimate').style.display = 'block';
            document.getElementById('estimated-ait').textContent = data.estimate.estimated_ait_amount || '-';
            document.getElementById('fee-eth').textContent = data.estimate.fee_eth || '-';
            document.getElementById('net-eth').textContent = data.estimate.net_eth || '-';
            document.getElementById('eth-usd').textContent = data.estimate.eth_usd_price || '-';
            document.getElementById('ait-usd').textContent = data.estimate.ait_usd_price || '-';

            // Show instructions
            document.getElementById('deposit-instructions').style.display = 'block';
            document.getElementById('deposit-address').textContent = data.instructions.send_eth_to;
            document.getElementById('instruction-eth-amount').textContent = data.instructions.amount_eth;
            document.getElementById('instruction-ait-address').textContent = data.instructions.transaction_data;
            document.getElementById('min-deposit').textContent = data.instructions.min_deposit;
        } else {
            // Show error
            document.getElementById('deposit-error').style.display = 'block';
            document.getElementById('deposit-error').textContent = data.error || data.message || 'Failed to calculate deposit';
        }
    } catch (error) {
        console.error('Error calculating deposit:', error);
        document.getElementById('deposit-error').style.display = 'block';
        document.getElementById('deposit-error').textContent = 'Failed to connect to server';
    }
}

function copyAddress() {
    const addressElement = document.getElementById('deposit-address');
    const address = addressElement ? addressElement.textContent : '';
    if (!address || address === 'Loading...') return;
    navigator.clipboard.writeText(address).then(() => {
        const feedback = document.getElementById('copy-feedback');
        feedback.style.display = 'block';
        setTimeout(() => {
            feedback.style.display = 'none';
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
}

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', function() {
    fetchPrices();
    fetchBridgeStatus();

    // Event listeners
    document.getElementById('calculate-deposit-btn').addEventListener('click', calculateDeposit);
    document.getElementById('deposit-address-box').addEventListener('click', copyAddress);
});
