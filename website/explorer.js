function formatHash(hash) {
    if (!hash) return 'N/A';
    return hash;
}

function copyToClipboard(text, btnEl) {
    if (!text || text === 'N/A') return;
    navigator.clipboard.writeText(text).then(() => {
        const original = btnEl.innerHTML;
        btnEl.innerHTML = '<span style="color:var(--success)">Copied!</span>';
        setTimeout(() => { btnEl.innerHTML = original; }, 1200);
    }).catch(() => {
        // Fallback for older browsers or permissions issues
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        const original = btnEl.innerHTML;
        btnEl.innerHTML = '<span style="color:var(--success)">Copied!</span>';
        setTimeout(() => { btnEl.innerHTML = original; }, 1200);
    });
}

function copyBtn(text) {
    return `<button class="copy-btn" onclick="event.stopPropagation(); copyToClipboard('${text}', this)" title="Copy to clipboard">📋</button>`;
}

function renderBlockTransactions(block) {
    const txs = block.transactions || [];
    if (txs.length === 0) {
        return '<div class="no-transactions">No transactions in this block</div>';
    }
    return txs.map(tx => {
        let txDetails = '';
        try {
            const payload = typeof tx.payload === 'string' ? JSON.parse(tx.payload) : tx.payload;
            if (typeof payload === 'object' && payload !== null) {
                const rows = Object.entries(payload)
                    .filter(([key]) => key !== 'chain_id' && key !== 'island_id')
                    .map(([key, value]) => {
                        let displayValue = value;
                        if (typeof value === 'object') displayValue = JSON.stringify(value);
                        if (String(displayValue).length > 60) displayValue = String(displayValue).substring(0, 57) + '...';
                        return `<div class="tx-detail-item"><span class="tx-detail-label">${key}:</span><span class="tx-detail-value">${displayValue}</span></div>`;
                    }).join('');
                if (rows) txDetails = `<div class="tx-marketplace-details">${rows}</div>`;
            }
        } catch (e) {
            if (tx.payload) {
                txDetails = `<div class="tx-marketplace-details"><div class="tx-detail-item"><span class="tx-detail-label">Payload:</span><span class="tx-detail-value">${tx.payload}</span></div></div>`;
            }
        }
        const txHash = tx.tx_hash || 'N/A';
        return `
            <div class="transaction-item">
                <div class="tx-header">
                    <span class="tx-type">${tx.type || 'Unknown'}</span>
                    <span class="tx-hash">${formatHash(txHash)} ${copyBtn(txHash)}</span>
                </div>
                <div class="tx-status ${tx.status === 'confirmed' ? 'confirmed' : 'pending'}">${tx.status || 'Unknown'}</div>
                <div class="result-detail">From: ${tx.sender || 'N/A'} ${copyBtn(tx.sender || '')}</div>
                <div class="result-detail">To: ${tx.recipient || 'N/A'} ${copyBtn(tx.recipient || '')}</div>
                ${txDetails}
            </div>
        `;
    }).join('');
}

async function toggleBlockDetail(height, cardEl) {
    event.stopPropagation();
    const panel = cardEl.querySelector('.block-detail-panel');
    const indicator = cardEl.querySelector('.expand-indicator');
    if (panel.style.display === 'block') {
        panel.style.display = 'none';
        indicator.textContent = '▼';
        cardEl.classList.add('block-collapsed');
        cardEl.classList.remove('block-expanded');
        return;
    }
    // Show loading
    panel.innerHTML = '<p class="loading-text">Loading transactions...</p>';
    panel.style.display = 'block';
    indicator.textContent = '▲';
    cardEl.classList.remove('block-collapsed');
    cardEl.classList.add('block-expanded');
    try {
        const res = await fetch(`${EXPLORER_API_URL}/api/blocks/${height}?chain_id=${currentChain}`);
        const block = await res.json();
        const txsHtml = renderBlockTransactions(block);
        panel.innerHTML = `
            <div class="block-transactions">
                <div class="transactions-header">Transactions (${block.transactions ? block.transactions.length : 0}):</div>
                ${txsHtml}
            </div>
        `;
    } catch (err) {
        panel.innerHTML = '<p class="error-text">Failed to load block details</p>';
    }
}

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', function() {
    // Initialize icons
    lucide.createIcons();

    // Configuration - API endpoint
    const EXPLORER_API_URL = '/explorer-api'; // Use nginx proxy
    let currentChain = 'ait-hub.aitbc.bubuit.net';

    // Toggle state: skip empty (heartbeat) blocks
    let skipEmptyBlocks = false;

    // Refresh data
    async function refreshData() {
        await updateChainStats();
        await loadActivityChart();
        await loadLatestBlocks();
        await updateLiveFeed();
        await loadTopAddresses();
    }

    // Load activity timeline chart
    async function loadActivityChart() {
        try {
            const response = await fetch(`${EXPLORER_API_URL}/api/analytics/activity?chain_id=${currentChain}&days=30`);
            const data = await response.json();
            const canvas = document.getElementById('activity-chart');
            if (!canvas || !data.labels || data.labels.length === 0) return;

            const ctx = canvas.getContext('2d');
            // Destroy existing chart if any
            if (window.activityChartInstance) {
                window.activityChartInstance.destroy();
            }
            window.activityChartInstance = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.labels,
                    datasets: data.datasets,
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { stacked: true, ticks: { color: '#71717a' } },
                        y: { stacked: true, ticks: { color: '#71717a' }, grid: { color: '#27272a' } },
                    },
                    plugins: {
                        legend: { labels: { color: '#e4e4e7' } },
                    },
                },
            });
        } catch (error) {
            console.error('Error loading activity chart:', error);
        }
    }

    // Live feed
    let liveFeedItems = [];
    async function updateLiveFeed() {
        try {
            const [blocksResp, txsResp] = await Promise.all([
                fetch(`${EXPLORER_API_URL}/api/blocks/latest?chain_id=${currentChain}&limit=5`),
                fetch(`${EXPLORER_API_URL}/api/transactions/search?chain_id=${currentChain}&limit=5`),
            ]);
            const blocksData = await blocksResp.json();
            const txsData = await txsResp.json();

            const newItems = [];
            (blocksData.blocks || []).forEach(b => {
                newItems.push({
                    type: 'BLOCK',
                    label: `#${b.height}`,
                    hash: b.hash,
                    time: b.timestamp,
                    url: `/block.html?height=${b.height}`,
                });
            });
            (txsData.transactions || []).forEach(t => {
                newItems.push({
                    type: t.type || 'TX',
                    label: (t.tx_hash || t.hash || '').substring(0, 16) + '...',
                    hash: t.tx_hash || t.hash,
                    time: t.created_at,
                    url: `/tx.html?hash=${encodeURIComponent(t.tx_hash || t.hash || '')}`,
                });
            });

            // Sort by time descending
            newItems.sort((a, b) => {
                const ta = a.time ? new Date(a.time).getTime() : 0;
                const tb = b.time ? new Date(b.time).getTime() : 0;
                return tb - ta;
            });

            // Keep only top 10
            liveFeedItems = newItems.slice(0, 10);
            renderLiveFeed();
        } catch (error) {
            console.error('Error updating live feed:', error);
        }
    }

    function renderLiveFeed() {
        const container = document.getElementById('live-feed-list');
        if (!container) return;
        if (liveFeedItems.length === 0) {
            container.innerHTML = '<p class="loading-text">Waiting for activity...</p>';
            return;
        }
        container.innerHTML = liveFeedItems.map(item => {
            const timeStr = item.time ? new Date(item.time).toLocaleTimeString() : '';
            return `
                <div class="live-feed-item" onclick="location.href='${item.url}'">
                    <span class="live-feed-type">${item.type}</span>
                    <span class="live-feed-hash">${item.label}</span>
                    <span class="live-feed-time">${timeStr}</span>
                </div>
            `;
        }).join('');
    }

    // Top addresses leaderboard
    async function loadTopAddresses() {
        try {
            const resp = await fetch(`${EXPLORER_API_URL}/api/analytics/top-addresses?chain_id=${currentChain}&limit=20`);
            const data = await resp.json();
            const container = document.getElementById('top-addresses-container');
            if (!container) return;
            const addresses = data.addresses || [];
            if (addresses.length === 0) {
                container.innerHTML = '<p class="loading-text">No address data yet.</p>';
                return;
            }
            container.innerHTML = `
                <table>
                    <thead><tr><th>#</th><th>Address</th><th>TXs</th><th>Volume (AIT)</th></tr></thead>
                    <tbody>
                        ${addresses.map((a, i) => `
                            <tr onclick="location.href='/search.html?query=${encodeURIComponent(a.address)}'" style="cursor:pointer;">
                                <td>${i + 1}</td>
                                <td>${a.address}</td>
                                <td>${a.transaction_count}</td>
                                <td>${a.volume.toLocaleString()}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        } catch (error) {
            console.error('Error loading top addresses:', error);
        }
    }

    // Update chain stats
    async function updateChainStats() {
        try {
            const response = await fetch(`${EXPLORER_API_URL}/api/chain/head?chain_id=${currentChain}`);
            const data = await response.json();
            
            if (data.height) {
                document.getElementById('chain-height').textContent = data.height;
            }
            
            document.getElementById('node-status').textContent = 'Connected';
            document.getElementById('node-status').style.color = 'var(--success)';
        } catch (error) {
            console.error('Error updating chain stats:', error);
            document.getElementById('node-status').textContent = 'Disconnected';
            document.getElementById('node-status').style.color = 'var(--error-color)';
        }
    }

    // Auto-refresh every 30 seconds to recover from temporary disconnections
    setInterval(() => {
        if (document.getElementById('node-status').textContent === 'Disconnected') {
            console.log('Auto-retrying connection...');
            refreshData();
        }
    }, 30000);

    // Block list pagination state
    let blocksOffset = 0;

    function renderBlockCard(block) {
        let timestamp = 'N/A';
        if (block.timestamp) {
            if (typeof block.timestamp === 'string') {
                timestamp = new Date(block.timestamp).toLocaleString();
            } else if (typeof block.timestamp === 'number') {
                timestamp = new Date(block.timestamp * 1000).toLocaleString();
            }
        }
        const txCount = block.txCount || 0;
        const blockHash = block.hash || 'N/A';
        const proposer = block.proposer || 'N/A';
        return `
            <div class="endpoint fade-in block-item" data-height="${block.height}" style="cursor:pointer;padding:0;" onclick="location.href='/block.html?height=${block.height}'">
                <table class="block-list-table">
                    <tr><td>Height</td><td><span class="badge badge-primary">BLOCK</span> #${block.height}</td></tr>
                    <tr><td>Hash</td><td>${blockHash} ${copyBtn(blockHash)}</td></tr>
                    <tr><td>Proposer</td><td>${proposer}</td></tr>
                    <tr><td>Transactions</td><td>${txCount}</td></tr>
                    <tr><td>Timestamp</td><td>${timestamp} UTC</td></tr>
                </table>
            </div>
        `;
    }

    // Load latest blocks
    async function loadLatestBlocks(reset = true) {
        try {
            if (reset) {
                blocksOffset = 0;
            }
            const limit = 10;
            const endpoint = skipEmptyBlocks
                ? `${EXPLORER_API_URL}/api/blocks/non-empty?chain_id=${currentChain}&limit=${limit}&offset=${blocksOffset}`
                : `${EXPLORER_API_URL}/api/blocks/latest?chain_id=${currentChain}&limit=${limit}&offset=${blocksOffset}`;

            const response = await fetch(endpoint);
            const data = await response.json();
            const blocks = data.blocks || [];

            const container = document.getElementById('blocks-container');
            const loadMoreContainer = document.getElementById('load-more-container');

            if (blocks.length > 0) {
                const html = blocks.map(renderBlockCard).join('');
                if (reset) {
                    container.innerHTML = html;
                } else {
                    container.insertAdjacentHTML('beforeend', html);
                }
                blocksOffset += blocks.length;
                loadMoreContainer.style.display = 'block';
            } else if (reset) {
                container.innerHTML = '<p class="loading-text">No blocks available</p>';
                loadMoreContainer.style.display = 'none';
            } else {
                // No more blocks to load
                loadMoreContainer.style.display = 'none';
            }
        } catch (error) {
            console.error('Error loading blocks:', error);
            if (reset) {
                document.getElementById('blocks-container').innerHTML = '<p class="error-text">Error loading blocks</p>';
            }
        }
    }

    // Clear search
    function clearSearch() {
        document.getElementById('search-input').value = '';
        document.getElementById('results-section').style.display = 'none';
    }

    // Perform simple search
    async function performSearch() {
        let query = document.getElementById('search-input').value.trim();
        console.log('Search query:', query);
        if (!query) {
            console.log('Empty query, returning');
            return;
        }

        // Strip # prefix if present (e.g., user enters "#27381")
        query = query.replace(/^#/, '');
        console.log('Query after stripping #:', query);

        // Try to determine if it's a block height, hash, or address
        const isNumber = /^\d+$/.test(query);
        const isHash = /^(0x)?[a-fA-F0-9]{64}$/.test(query);

        console.log('Is number:', isNumber, 'Is hash:', isHash);

        if (isNumber) {
            // Go directly to block detail
            location.href = `/block.html?height=${query}`;
        } else if (isHash) {
            // Try hash as transaction first, then block
            location.href = `/tx.html?hash=${encodeURIComponent(query)}`;
        } else {
            // Address or other search -> dedicated search page
            location.href = `/search.html?query=${encodeURIComponent(query)}`;
        }
    }

    // Search by hash (could be block or transaction)
    async function searchByHash(hash) {
        console.log('searchByHash called with:', hash);
        // Strip 0x prefix if present for API calls
        const cleanHash = hash.startsWith('0x') ? hash.slice(2) : hash;
        console.log('Clean hash for API:', cleanHash);
        
        // First try to search as block
        const blockResponse = await fetch(`${EXPLORER_API_URL}/api/blocks/by-hash/${cleanHash}?chain_id=${currentChain}`);
        console.log('Block by hash response status:', blockResponse.status);
        if (blockResponse.ok) {
            const blockData = await blockResponse.json();
            console.log('Block by hash data:', blockData);
            if (blockData && blockData.height) {
                displayResults([blockData], 'block');
                return;
            }
        }
        
        console.log('Block not found by hash, trying transaction search');
        // If block not found, try to search as transaction
        const txResponse = await fetch(`${EXPLORER_API_URL}/api/transactions/by-hash/${cleanHash}?chain_id=${currentChain}`);
        console.log('Transaction by hash response status:', txResponse.status);
        if (txResponse.ok) {
            const txData = await txResponse.json();
            console.log('Transaction by hash data:', txData);
            if (txData && txData.tx_hash) {
                displayResults([txData], 'transaction');
                return;
            }
        }
        
        console.log('Neither block nor transaction found by hash, trying address search');
        // If no block or transaction found, the "hash" might actually be a node ID or address
        await searchByAddress(hash);
    }

    // Search block by height
    async function searchBlock(height) {
        console.log('searchBlock called with height:', height);
        try {
            const response = await fetch(`${EXPLORER_API_URL}/api/blocks/${height}?chain_id=${currentChain}`);
            console.log('Response status:', response.status);
            const data = await response.json();
            console.log('Response data:', data);
            if (data && data.height) {
                displayResults([data], 'block');
            } else {
                console.log('No valid block data in response');
                displayResults([], 'block');
            }
        } catch (error) {
            console.error('Error searching block:', error);
            displayError('Block not found');
        }
    }

    // Search transaction by hash
    async function searchTransaction(hash) {
        console.log('searchTransaction called with:', hash);
        // Strip 0x prefix if present for API calls
        const cleanHash = hash.startsWith('0x') ? hash.slice(2) : hash;
        try {
            const response = await fetch(`${EXPLORER_API_URL}/api/transactions/${cleanHash}?chain_id=${currentChain}`);
            console.log('Transaction response status:', response.status);
            const data = await response.json();
            console.log('Transaction data:', data);
            if (data && data.hash) {
                displayResults([data], 'transaction');
            } else {
                console.log('No valid transaction data');
                displayResults([], 'transaction');
            }
        } catch (error) {
            console.error('Error searching transaction:', error);
            displayError('Transaction not found');
        }
    }

    // Search by address
    async function searchByAddress(address) {
        try {
            const [txResp, blockResp] = await Promise.all([
                fetch(`${EXPLORER_API_URL}/api/transactions/search?address=${encodeURIComponent(address)}&chain_id=${currentChain}`),
                fetch(`${EXPLORER_API_URL}/api/blocks/by-address/${encodeURIComponent(address)}?chain_id=${currentChain}`),
            ]);
            const txData = await txResp.json();
            const blockData = await blockResp.json();
            const txs = txData.transactions || [];
            const blocks = blockData.blocks || [];
            if (txs.length === 0 && blocks.length === 0) {
                displayError('No transactions or blocks found for this address/node ID');
                return;
            }
            displayAddressResults(blocks, txs, address);
        } catch (error) {
            console.error('Error searching by address:', error);
            displayError('No transactions or blocks found for address');
        }
    }

    function displayAddressResults(blocks, txs, searchedAddress) {
        const section = document.getElementById('results-section');
        const container = document.getElementById('results-container');
        const count = document.getElementById('results-count');

        section.style.display = 'block';
        count.textContent = `${blocks.length} block${blocks.length !== 1 ? 's' : ''}, ${txs.length} transaction${txs.length !== 1 ? 's' : ''}`;

        let html = '';

        if (blocks.length > 0) {
            html += `<h3 style="margin:1.5rem 0 0.5rem;color:var(--text-muted);font-size:0.85rem;text-transform:uppercase;letter-spacing:0.05em;">Blocks (${blocks.length})</h3>`;
            html += blocks.map(block => renderBlockCard(block)).join('');
        }

        if (txs.length > 0) {
            html += `<h3 style="margin:1.5rem 0 0.5rem;color:var(--text-muted);font-size:0.85rem;text-transform:uppercase;letter-spacing:0.05em;">Transactions (${txs.length})</h3>`;
            html += displayResultsHtml(txs, 'transaction', searchedAddress);
        }

        container.innerHTML = html || '<p class="loading-text">No results found.</p>';
    }

    function displayResultsHtml(results, type, searchedAddress) {
        const validResults = results.filter(item => {
            if (type === 'block') {
                return item && item.height;
            } else {
                return item && (item.hash || item.tx_hash);
            }
        });

        if (validResults.length === 0) {
            return '<p class="loading-text">No valid results found.</p>';
        }

        return validResults.map(item => {
            let timestamp = '-';
            if (item.timestamp) {
                if (typeof item.timestamp === 'string') {
                    timestamp = new Date(item.timestamp).toLocaleString();
                } else if (typeof item.timestamp === 'number') {
                    timestamp = new Date(item.timestamp * 1000).toLocaleString();
                }
            }
            if (item.created_at) {
                timestamp = new Date(item.created_at).toLocaleString();
            }

            let details = '';
            if (type === 'block') {
                details = `
                    <div class="result-hash">
                        Hash: ${item.hash || 'N/A'} ${copyBtn(item.hash || '')}
                    </div>
                    <div class="result-detail">
                        Proposer: ${item.proposer || 'N/A'}
                    </div>
                    <div class="result-detail">
                        Transactions: ${item.txCount || 0}
                    </div>
                `;
            } else {
                let payloadDetails = '';
                try {
                    if (item.payload) {
                        const payload = typeof item.payload === 'string' ? JSON.parse(item.payload) : item.payload;
                        if (payload && typeof payload === 'object') {
                            const rows = Object.entries(payload).map(([key, value]) => {
                                let displayValue = value;
                                if (typeof value === 'object') displayValue = JSON.stringify(value);
                                if (String(displayValue).length > 60) displayValue = String(displayValue).substring(0, 57) + '...';
                                return `<div class="tx-detail-item"><span class="tx-detail-label">${key}:</span><span class="tx-detail-value">${displayValue}</span></div>`;
                            }).join('');
                            if (rows) payloadDetails = `<div class="tx-marketplace-details">${rows}</div>`;
                        }
                    }
                } catch (e) {
                    if (item.payload) {
                        payloadDetails = `<div class="tx-marketplace-details"><div class="tx-detail-item"><span class="tx-detail-label">Payload:</span><span class="tx-detail-value">${item.payload}</span></div></div>`;
                    }
                }

                const txHashVal = item.tx_hash || item.hash || 'N/A';
                const fromAddr = item.from || item.sender || 'N/A';
                const toAddr = item.to || item.recipient || 'N/A';
                details = `
                    <div class="result-hash">
                        Hash: ${txHashVal} ${copyBtn(txHashVal)}
                    </div>
                    <div class="result-detail">
                        Type: ${item.type || 'Unknown'}
                    </div>
                    <div class="result-detail">
                        Block: ${item.block_height || 'N/A'}
                    </div>
                    <div class="result-detail">
                        From: ${fromAddr} ${copyBtn(fromAddr)}
                    </div>
                    <div class="result-detail">
                        To: ${toAddr} ${copyBtn(toAddr)}
                    </div>
                    ${payloadDetails}
                `;
            }

            const dir = type === 'transaction' ? getTxDirection(item, searchedAddress) : '';
            const clickTarget = type === 'block'
                ? `/block.html?height=${item.height}`
                : `/tx.html?hash=${encodeURIComponent(item.tx_hash || item.hash || '')}`;
            const isBlock = type === 'block';
            return `
            <div class="endpoint fade-in block-item" style="cursor:pointer;" onclick="location.href='${clickTarget}'">
                <div class="block-header">
                    <div class="flex-center">
                        <span class="badge badge-primary">${isBlock ? 'BLOCK' : (item.type || 'TX')}</span>
                        ${directionBadge(dir)}
                    </div>
                    <div class="result-timestamp">
                        ${timestamp}
                    </div>
                </div>
                ${details}
                ${item.note ? `<div class="result-note">${item.note}</div>` : ''}
            </div>
        `;
        }).join('');
    }

    // Compute transaction direction relative to searched address
    function getTxDirection(tx, searchedAddr) {
        if (!searchedAddr) return '';
        const s = (tx.sender || '').toLowerCase();
        const r = (tx.recipient || '').toLowerCase();
        const addr = searchedAddr.toLowerCase();
        if (s === addr && r === addr) return 'self';
        if (s === addr) return 'out';
        if (r === addr) return 'in';
        try {
            const payload = typeof tx.payload === 'string' ? JSON.parse(tx.payload) : tx.payload;
            if (payload && payload.provider_node_id && payload.provider_node_id.toLowerCase() === addr) return 'self';
            if (payload && payload.node_id && payload.node_id.toLowerCase() === addr) return 'self';
        } catch (e) {}
        return '';
    }

    function directionBadge(direction) {
        if (!direction) return '';
        const labels = { out: 'OUT →', in: 'IN ←', self: 'SELF ↻' };
        return `<span class="dir-badge dir-${direction}">${labels[direction]}</span>`;
    }

    // Display results
    function displayResults(results, type, searchedAddress = '') {
        console.log('displayResults called with:', results.length, 'results of type:', type);
        const section = document.getElementById('results-section');
        const container = document.getElementById('results-container');
        const count = document.getElementById('results-count');

        section.style.display = 'block';
        count.textContent = `${results.length} ${type}${results.length !== 1 ? 's' : ''} found`;

        if (results.length === 0) {
            container.innerHTML = '<p class="loading-text">No results found.</p>';
            return;
        }

        // Filter out results that don't have the required data
        const validResults = results.filter(item => {
            if (type === 'block') {
                return item && item.height;
            } else {
                return item && (item.hash || item.tx_hash);
            }
        });

        console.log('Valid results after filtering:', validResults.length);

        if (validResults.length === 0) {
            container.innerHTML = '<p class="loading-text">No valid results found.</p>';
            return;
        }

        container.innerHTML = validResults.map(item => {
            // Handle both timestamp formats
            let timestamp = '-';
            if (item.timestamp) {
                if (typeof item.timestamp === 'string') {
                    timestamp = new Date(item.timestamp).toLocaleString();
                } else if (typeof item.timestamp === 'number') {
                    timestamp = new Date(item.timestamp * 1000).toLocaleString();
                }
            }

            // Build details based on type
            let details = '';
            if (type === 'block') {
                // Build transactions list if available
                let transactionsHtml = '';
                if (item.transactions && item.transactions.length > 0) {
                    transactionsHtml = `
                        <div class="block-transactions">
                            <div class="transactions-header">Transactions (${item.transactions.length}):</div>
                            ${item.transactions.map(tx => {
                                let txDetails = '';
                                try {
                                    const payload = typeof tx.payload === 'string' ? JSON.parse(tx.payload) : tx.payload;
                                    if (typeof payload === 'object' && payload !== null) {
                                        const detailRows = Object.entries(payload)
                                            .filter(([key]) => key !== 'chain_id' && key !== 'island_id')
                                            .map(([key, value]) => {
                                                let displayValue = value;
                                                if (typeof value === 'object') {
                                                    displayValue = JSON.stringify(value);
                                                }
                                                if (String(displayValue).length > 60) {
                                                    displayValue = String(displayValue).substring(0, 57) + '...';
                                                }
                                                return `
                                                    <div class="tx-detail-item">
                                                        <span class="tx-detail-label">${key}:</span>
                                                        <span class="tx-detail-value">${displayValue}</span>
                                                    </div>
                                                `;
                                            }).join('');
                                        if (detailRows) {
                                            txDetails = `<div class="tx-marketplace-details">${detailRows}</div>`;
                                        }
                                    }
                                } catch (e) {
                                    if (tx.payload) {
                                        txDetails = `<div class="tx-marketplace-details"><div class="tx-detail-item"><span class="tx-detail-label">Payload:</span><span class="tx-detail-value">${tx.payload}</span></div></div>`;
                                    }
                                }
                                
                                const innerTxHash = tx.tx_hash || 'N/A';
                                return `
                                    <div class="transaction-item">
                                        <div class="tx-header">
                                            <span class="tx-type">${tx.type || 'Unknown'}</span>
                                            <span class="tx-hash">${formatHash(innerTxHash)} ${copyBtn(innerTxHash)}</span>
                                        </div>
                                        <div class="tx-status ${tx.status === 'confirmed' ? 'confirmed' : 'pending'}">
                                            ${tx.status || 'Unknown'}
                                        </div>
                                        ${txDetails}
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    `;
                } else {
                    transactionsHtml = `
                        <div class="block-transactions">
                            <div class="transactions-header">Transactions: ${item.txCount || 0}</div>
                            <div class="no-transactions">No transactions in this block</div>
                        </div>
                    `;
                }
                
                const blockHashVal = item.hash || 'N/A';
                details = `
                    <div class="result-hash">
                        Hash: ${blockHashVal} ${copyBtn(blockHashVal)}
                    </div>
                    <div class="result-detail">
                        Validator: ${item.proposer || item.validator || 'unknown'}
                    </div>
                    <div class="result-detail">
                        Height: ${item.height || 'N/A'}
                    </div>
                    ${transactionsHtml}
                `;
            } else {
                // Parse payload for transaction details
                let payloadDetails = '';
                try {
                    const payload = typeof item.payload === 'string' ? JSON.parse(item.payload) : item.payload;
                    if (typeof payload === 'object' && payload !== null) {
                        const rows = Object.entries(payload)
                            .filter(([key]) => key !== 'chain_id' && key !== 'island_id')
                            .map(([key, value]) => {
                                let displayValue = value;
                                if (typeof value === 'object') displayValue = JSON.stringify(value);
                                if (String(displayValue).length > 60) displayValue = String(displayValue).substring(0, 57) + '...';
                                return `<div class="tx-detail-item"><span class="tx-detail-label">${key}:</span><span class="tx-detail-value">${displayValue}</span></div>`;
                            }).join('');
                        if (rows) payloadDetails = `<div class="tx-marketplace-details">${rows}</div>`;
                    }
                } catch (e) {
                    if (item.payload) {
                        payloadDetails = `<div class="tx-marketplace-details"><div class="tx-detail-item"><span class="tx-detail-label">Payload:</span><span class="tx-detail-value">${item.payload}</span></div></div>`;
                    }
                }
                
                const txHashVal = item.tx_hash || item.hash || 'N/A';
                const fromAddr = item.from || item.sender || 'N/A';
                const toAddr = item.to || item.recipient || 'N/A';
                details = `
                    <div class="result-hash">
                        Hash: ${txHashVal} ${copyBtn(txHashVal)}
                    </div>
                    <div class="result-detail">
                        Type: ${item.type || 'Unknown'}
                    </div>
                    <div class="result-detail">
                        Block: ${item.block_height || 'N/A'}
                    </div>
                    <div class="result-detail">
                        From: ${fromAddr} ${copyBtn(fromAddr)}
                    </div>
                    <div class="result-detail">
                        To: ${toAddr} ${copyBtn(toAddr)}
                    </div>
                    ${payloadDetails}
                `;
            }

            const dir = type === 'transaction' ? getTxDirection(item, searchedAddress) : '';
            const clickTarget = type === 'block'
                ? `/block.html?height=${item.height}`
                : `/tx.html?hash=${encodeURIComponent(item.tx_hash || item.hash || '')}`;
            const isBlock = type === 'block';
            return `
            <div class="endpoint fade-in block-item" style="cursor:pointer;" onclick="location.href='${clickTarget}'">
                <div class="block-header">
                    <div class="flex-center">
                        <span class="badge badge-primary">${isBlock ? 'BLOCK' : (item.type || 'TX')}</span>
                        ${directionBadge(dir)}
                    </div>
                    <div class="result-timestamp">
                        ${timestamp}
                    </div>
                </div>
                ${details}
                ${item.note ? `<div class="result-note">${item.note}</div>` : ''}
            </div>
        `;
        }).join('');
    }

    // Display error
    function displayError(message) {
        const section = document.getElementById('results-section');
        const container = document.getElementById('results-container');
        const count = document.getElementById('results-count');

        section.style.display = 'block';
        count.textContent = '';
        container.innerHTML = `<p class="error-text">${message}</p>`;
    }

    // Export blockchain
    async function exportBlockchain() {
        try {
            // Get current block height first
            const headResponse = await fetch(`${EXPLORER_API_URL}/api/chain/head?chain_id=${currentChain}`);
            const headData = await headResponse.json();

            if (!headData.height) {
                alert('Unable to get blockchain height');
                return;
            }

            const maxHeight = headData.height;
            const exportCount = prompt(`Blockchain height: ${maxHeight}\n\nHow many recent blocks to export? (max 1000)`, '100');
            const count = Math.min(parseInt(exportCount) || 100, 1000);

            if (count <= 0) {
                alert('Invalid block count');
                return;
            }

            // Ask for format
            const format = prompt('Export format: "csv" or "json"?', 'csv');
            if (format !== 'csv' && format !== 'json') {
                alert('Invalid format');
                return;
            }

            // Fetch blocks
            const blocks = [];
            const startHeight = Math.max(maxHeight - count + 1, 1);
            for (let height = startHeight; height <= maxHeight; height++) {
                try {
                    const response = await fetch(`${EXPLORER_API_URL}/api/blocks/${height}?chain_id=${currentChain}`);
                    if (response.ok) {
                        const block = await response.json();
                        if (block.height) {
                            blocks.push(block);
                        }
                    }
                } catch (error) {
                    console.error(`Error fetching block ${height}:`, error);
                }
            }

            if (blocks.length === 0) {
                alert('No blocks to export');
                return;
            }

            alert(`Exported ${blocks.length} blocks`);

        } catch (error) {
            console.error('Error exporting blockchain:', error);
            alert('Error exporting blockchain');
        }
    }

    function exportBlocksAsCSV(blocks) {
        const headers = ['Height', 'Hash', 'Validator', 'Transaction Count', 'Timestamp'];
        const rows = blocks.map(block => [
            block.height,
            block.hash,
            block.validator,
            block.txCount,
            block.timestamp
        ]);

        const csvContent = [
            headers.join(','),
            ...rows.map(row => row.join(','))
        ].join('\n');

        downloadFile(csvContent, 'latest_blocks.csv', 'text/csv');
    }

    function exportBlocksAsJSON(blocks) {
        const jsonContent = JSON.stringify(blocks, null, 2);
        downloadFile(jsonContent, 'latest_blocks.json', 'application/json');
    }

    function downloadFile(content, filename, mimeType) {
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // Auto-refresh every 30 seconds
    setInterval(refreshData, 30000);
    // Live feed refreshes more frequently
    setInterval(updateLiveFeed, 10000);

    // Event listeners
    document.getElementById('clear-search-btn').addEventListener('click', clearSearch);
    document.getElementById('export-blockchain-btn').addEventListener('click', exportBlockchain);
    document.getElementById('search-input').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            performSearch();
        }
    });

    // Skip empty blocks toggle
    const skipEmptyToggle = document.getElementById('skip-empty-blocks');
    if (skipEmptyToggle) {
        skipEmptyToggle.addEventListener('change', function() {
            skipEmptyBlocks = this.checked;
            loadLatestBlocks(true);
        });
    }

    // Load more blocks
    const loadMoreBtn = document.getElementById('load-more-btn');
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', function() {
            loadLatestBlocks(false);
        });
    }

    // Initial load
    refreshData();

    // Redirect old ?search= param to dedicated search page
    const urlSearch = new URL(window.location.href).searchParams.get('search');
    if (urlSearch) {
        location.replace(`/search.html?query=${encodeURIComponent(urlSearch)}`);
    }
});
