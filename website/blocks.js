// Latest Blocks page — dedicated to browsing blocks
// Reuses global helpers (copyBtn, copyToClipboard, renderBlockCard,
// blockContentHtml) from explorer.js

document.addEventListener('DOMContentLoaded', function() {
    lucide.createIcons();

    const EXPLORER_API_URL = window.AITBC_CONFIG.explorerApiUrl;
    const currentChain = window.AITBC_CONFIG.chainId;

    let skipEmptyBlocks = false;
    let blocksOffset = 0;
    let blocksLastGoodAt = 0;

    function ageAgo(ts) {
        const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
        if (s < 5) return 'just now';
        if (s < 90) return `${s} s ago`;
        return `${Math.round(s / 60)} min ago`;
    }

    // One read, one outcome object: ok only for status-ok AND parseable JSON.
    async function readJson(url) {
        try {
            const resp = await fetch(url);
            if (!resp.ok) return { ok: false, status: resp.status };
            try {
                return { ok: true, status: resp.status, data: await resp.json() };
            } catch (e) {
                return { ok: false, status: resp.status, err: 'reply was not readable' };
            }
        } catch (e) {
            return { ok: false, status: 0, err: 'network request failed' };
        }
    }

    // The single read-state note for the block list — one element, never
    // one line per poll.
    function renderReadState(container, state, detail, retry) {
        const prev = [...container.children].find(c => c.classList && c.classList.contains('blocks-read-note'));
        if (prev) prev.remove();
        if (state === 'live') return;
        const note = document.createElement('div');
        note.className = state === 'failed' ? 'msg-state blocks-read-note' : 'msg-state-note blocks-read-note';
        note.setAttribute('role', state === 'failed' ? 'alert' : 'status');
        const line = document.createElement(state === 'failed' ? 'p' : 'span');
        if (state === 'failed') line.className = 'msg-state-title';
        line.textContent = detail;
        note.appendChild(line);
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'bridge-retry';
        btn.textContent = 'Try again';
        btn.addEventListener('click', retry);
        note.appendChild(btn);
        container.prepend(note);
    }

    async function loadLatestBlocks(reset = true) {
        if (reset) {
            blocksOffset = 0;
        }
        const limit = 10;
        const endpoint = skipEmptyBlocks
            ? `${EXPLORER_API_URL}/api/blocks/non-empty?chain_id=${currentChain}&limit=${limit}&offset=${blocksOffset}`
            : `${EXPLORER_API_URL}/api/blocks/latest?chain_id=${currentChain}&limit=${limit}&offset=${blocksOffset}`;

        const container = document.getElementById('blocks-container');
        const loadMoreContainer = document.getElementById('load-more-container');
        const r = await readJson(endpoint);
        const blocks = r.ok && r.data && Array.isArray(r.data.blocks) ? r.data.blocks : null;
        if (blocks === null) {
            const reason = r.ok ? 'reply was not the expected shape' : (r.err || `HTTP ${r.status}`);
            const feedStatus = document.getElementById('sr-announcer');
            if (feedStatus) feedStatus.textContent = `Blocks failed to load: ${reason}`;
            if (blocksLastGoodAt) {
                // Last-good rows stay; ONE note names the last good read.
                renderReadState(container, 'stale', `Stale, last read ${ageAgo(blocksLastGoodAt)} — could not refresh (${reason})`, () => loadLatestBlocks(true));
            } else {
                container.textContent = '';
                renderReadState(container, 'failed', `Blocks could not be loaded. (${reason})`, () => loadLatestBlocks(true));
            }
            return;
        }
        blocksLastGoodAt = Date.now();

        if (blocks.length > 0) {
            // A throw while drawing cards is a named failure, never a page
            // that reads as still loading.
            try {
                const html = blocks.map(renderBlockCard).join('');
                if (reset) {
                    const feedStatus = document.getElementById('sr-announcer');
                    const topHash = blocks[0] && blocks[0].hash;
                    if (feedStatus && topHash && topHash !== window.__lastAnnouncedBlock) {
                        window.__lastAnnouncedBlock = topHash;
                        feedStatus.textContent = `Blocks updated — latest height ${blocks[0].height}`;
                    }
                    container.innerHTML = html;
                } else {
                    container.insertAdjacentHTML('beforeend', html);
                }
            } catch (e) {
                const reason = `display error: ${e.message}`;
                const feedStatus = document.getElementById('sr-announcer');
                if (feedStatus) feedStatus.textContent = `Blocks failed to load: ${reason}`;
                if (container.querySelector('.endpoint')) {
                    renderReadState(container, 'stale', `Stale, last read ${ageAgo(blocksLastGoodAt)} — could not refresh (${reason})`, () => loadLatestBlocks(true));
                } else {
                    container.textContent = '';
                    renderReadState(container, 'failed', `Blocks could not be loaded. (${reason})`, () => loadLatestBlocks(true));
                }
                return;
            }
            blocksOffset += blocks.length;
            loadMoreContainer.style.display = 'block';
        } else if (reset) {
            container.innerHTML = '<p class="loading-text">No blocks available</p>';
            loadMoreContainer.style.display = 'none';
        } else {
            loadMoreContainer.style.display = 'none';
        }
        renderReadState(container, 'live');
    }

    async function exportBlockchain() {
        try {
            const headResponse = await fetch(`${EXPLORER_API_URL}/api/chain/head?chain_id=${currentChain}`);
            const headData = headResponse.ok ? await headResponse.json() : null;
            if (!headData || headData.height == null) {
                alert(headResponse.ok
                    ? 'Unable to get blockchain height (reply was not the expected shape)'
                    : `Unable to get blockchain height (HTTP ${headResponse.status})`);
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
            let failedReads = 0;
            const startHeight = Math.max(maxHeight - count + 1, 1);
            for (let height = startHeight; height <= maxHeight; height++) {
                try {
                    const response = await fetch(`${EXPLORER_API_URL}/api/blocks/${height}?chain_id=${currentChain}`);
                    if (response.ok) {
                        const block = await response.json();
                        if (block.height) {
                            blocks.push(block);
                        } else {
                            failedReads++;
                        }
                    } else {
                        failedReads++;
                    }
                } catch (error) {
                    failedReads++;
                    console.error(`Error fetching block ${height}:`, error);
                }
            }
            if (blocks.length === 0) {
                alert(failedReads
                    ? `No blocks could be read (${failedReads} block reads failed)`
                    : 'No blocks to export');
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
