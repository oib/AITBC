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
        await loadLatestBlocks();
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

    // Load latest blocks
    async function loadLatestBlocks() {
        try {
            // Use dedicated non-empty endpoint when toggle is on
            const endpoint = skipEmptyBlocks
                ? `${EXPLORER_API_URL}/api/blocks/non-empty?chain_id=${currentChain}&limit=10`
                : `${EXPLORER_API_URL}/api/blocks/latest?chain_id=${currentChain}&limit=10`;

            const response = await fetch(endpoint);
            const data = await response.json();
            const blocks = data.blocks || [];

            const container = document.getElementById('blocks-container');
            if (blocks.length > 0) {
                container.innerHTML = blocks.map(block => {
                    // Handle both timestamp formats (ISO string and Unix timestamp)
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
                    return `
                    <div class="endpoint fade-in block-item block-collapsed" data-height="${block.height}" onclick="toggleBlockDetail(${block.height}, this)">
                        <div class="block-header">
                            <span class="badge badge-primary">#${block.height}</span>
                            <span class="block-hash">${blockHash}</span>
                            ${copyBtn(blockHash)}
                            <span class="expand-indicator">▼</span>
                        </div>
                        <div class="block-timestamp">
                            ${timestamp} UTC
                        </div>
                        <div class="block-meta">
                            Transactions: ${txCount}
                        </div>
                        <div class="block-detail-panel" style="display:none;"></div>
                    </div>
                `;
                }).join('');
            } else {
                container.innerHTML = '<p class="loading-text">No blocks available</p>';
            }
        } catch (error) {
            console.error('Error loading blocks:', error);
            document.getElementById('blocks-container').innerHTML = '<p class="error-text">Error loading blocks</p>';
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
            // Search by block height
            console.log('Searching by block height:', parseInt(query));
            await searchBlock(parseInt(query));
        } else if (isHash) {
            // Search by hash - try both block and transaction
            console.log('Searching by hash:', query);
            await searchByHash(query);
        } else {
            // Search by address or try as block height if it looks like a number with extra chars
            const cleanNumber = query.replace(/[^0-9]/g, '');
            if (cleanNumber && cleanNumber === query) {
                console.log('Searching by block height (cleaned):', parseInt(cleanNumber));
                await searchBlock(parseInt(cleanNumber));
            } else {
                console.log('Searching by address:', query);
                await searchByAddress(query);
            }
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
            const response = await fetch(`${EXPLORER_API_URL}/api/transactions/search?address=${encodeURIComponent(address)}&chain_id=${currentChain}`);
            const data = await response.json();
            const txs = data.transactions || [];
            if (txs.length === 0) {
                displayError('No transactions found for this address/node ID');
                return;
            }
            displayResults(txs, 'transaction');
        } catch (error) {
            console.error('Error searching by address:', error);
            displayError('No transactions found for address');
        }
    }

    // Display results
    function displayResults(results, type) {
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

            return `
            <div class="endpoint fade-in block-item">
                <div class="block-header">
                    <div class="flex-center">
                        <span class="badge badge-primary">${type === 'block' ? '#' + item.height : (item.type ? item.type + ' - ' : '') + (item.tx_hash || item.hash || 'N/A').substring(0, 16) + '...'}</span>
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
            loadLatestBlocks();
        });
    }

    // Initial load
    refreshData();
});
