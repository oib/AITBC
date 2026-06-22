// Latest Blocks page — dedicated to browsing blocks
// Reuses global helpers (copyBtn, copyToClipboard) from explorer.js

document.addEventListener('DOMContentLoaded', function() {
    lucide.createIcons();

    const EXPLORER_API_URL = window.AITBC_CONFIG.explorerApiUrl;
    const currentChain = window.AITBC_CONFIG.chainId;

    let skipEmptyBlocks = false;
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
                loadMoreContainer.style.display = 'none';
            }
        } catch (error) {
            console.error('Error loading blocks:', error);
            if (reset) {
                document.getElementById('blocks-container').innerHTML = '<p class="error-text">Error loading blocks</p>';
            }
        }
    }

    async function exportBlockchain() {
        try {
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
            const format = prompt('Export format: "csv" or "json"?', 'csv');
            if (format !== 'csv' && format !== 'json') {
                alert('Invalid format');
                return;
            }
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
            if (format === 'csv') {
                const headers = ['Height', 'Hash', 'Validator', 'Transaction Count', 'Timestamp'];
                const rows = blocks.map(block => [block.height, block.hash, block.validator, block.txCount, block.timestamp]);
                const csvContent = [headers.join(','), ...rows.map(row => row.join(','))].join('\n');
                downloadFile(csvContent, 'latest_blocks.csv', 'text/csv');
            } else {
                const jsonContent = JSON.stringify(blocks, null, 2);
                downloadFile(jsonContent, 'latest_blocks.json', 'application/json');
            }
            alert(`Exported ${blocks.length} blocks`);
        } catch (error) {
            console.error('Error exporting blockchain:', error);
            alert('Error exporting blockchain');
        }
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

    // Event listeners
    const skipEmptyToggle = document.getElementById('skip-empty-blocks');
    if (skipEmptyToggle) {
        skipEmptyToggle.addEventListener('change', function() {
            skipEmptyBlocks = this.checked;
            loadLatestBlocks(true);
        });
    }

    const loadMoreBtn = document.getElementById('load-more-btn');
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', function() {
            loadLatestBlocks(false);
        });
    }

    const exportBtn = document.getElementById('export-blockchain-btn');
    if (exportBtn) {
        exportBtn.addEventListener('click', exportBlockchain);
    }

    // Initial load
    loadLatestBlocks(true);

    // Auto-refresh every 30 seconds
    setInterval(() => loadLatestBlocks(true), 30000);
});
