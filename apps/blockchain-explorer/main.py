#!/usr/bin/env python3
"""
AITBC Blockchain Explorer
A simple web interface to explore the blockchain
"""

import asyncio
import httpx
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI(title="AITBC Blockchain Explorer", version="1.0.0")

# Configuration
BLOCKCHAIN_RPC_URL = "http://localhost:8082"  # Local blockchain node
EXTERNAL_RPC_URL = "http://aitbc.keisanki.net:8082"  # External access

# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AITBC Blockchain Explorer</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        .fade-in { animation: fadeIn 0.3s ease-in; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
    </style>
</head>
<body class="bg-gray-50">
    <header class="bg-blue-600 text-white shadow-lg">
        <div class="container mx-auto px-4 py-4">
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-3">
                    <i data-lucide="cube" class="w-8 h-8"></i>
                    <h1 class="text-2xl font-bold">AITBC Blockchain Explorer</h1>
                </div>
                <div class="flex items-center space-x-4">
                    <span class="text-sm">Network: <span class="font-mono bg-blue-700 px-2 py-1 rounded">ait-devnet</span></span>
                    <button onclick="refreshData()" class="bg-blue-500 hover:bg-blue-400 px-3 py-1 rounded flex items-center space-x-1">
                        <i data-lucide="refresh-cw" class="w-4 h-4"></i>
                        <span>Refresh</span>
                    </button>
                </div>
            </div>
        </div>
    </header>

    <main class="container mx-auto px-4 py-8">
        <!-- Chain Stats -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div class="bg-white rounded-lg shadow p-6">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-gray-500 text-sm">Current Height</p>
                        <p class="text-2xl font-bold" id="chain-height">-</p>
                    </div>
                    <i data-lucide="trending-up" class="w-10 h-10 text-green-500"></i>
                </div>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-gray-500 text-sm">Latest Block</p>
                        <p class="text-lg font-mono" id="latest-hash">-</p>
                    </div>
                    <i data-lucide="hash" class="w-10 h-10 text-blue-500"></i>
                </div>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-gray-500 text-sm">Node Status</p>
                        <p class="text-lg font-semibold" id="node-status">-</p>
                    </div>
                    <i data-lucide="activity" class="w-10 h-10 text-purple-500"></i>
                </div>
            </div>
        </div>

        <!-- Search -->
        <div class="bg-white rounded-lg shadow p-6 mb-8">
            <div class="flex space-x-4">
                <input type="text" id="search-input" placeholder="Search by block height, hash, or transaction hash" 
                       class="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                <button onclick="search()" class="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700">
                    Search
                </button>
            </div>
        </div>

        <!-- Latest Blocks -->
        <div class="bg-white rounded-lg shadow">
            <div class="px-6 py-4 border-b">
                <h2 class="text-xl font-semibold flex items-center">
                    <i data-lucide="blocks" class="w-5 h-5 mr-2"></i>
                    Latest Blocks
                </h2>
            </div>
            <div class="p-6">
                <div class="overflow-x-auto">
                    <table class="w-full">
                        <thead>
                            <tr class="text-left text-gray-500 text-sm">
                                <th class="pb-3">Height</th>
                                <th class="pb-3">Hash</th>
                                <th class="pb-3">Timestamp</th>
                                <th class="pb-3">Transactions</th>
                                <th class="pb-3">Actions</th>
                            </tr>
                        </thead>
                        <tbody id="blocks-table">
                            <tr>
                                <td colspan="5" class="text-center py-8 text-gray-500">
                                    Loading blocks...
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Block Details Modal -->
        <div id="block-modal" class="fixed inset-0 bg-black bg-opacity-50 hidden z-50">
            <div class="flex items-center justify-center min-h-screen p-4">
                <div class="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto">
                    <div class="p-6 border-b">
                        <div class="flex justify-between items-center">
                            <h2 class="text-2xl font-bold">Block Details</h2>
                            <button onclick="closeModal()" class="text-gray-500 hover:text-gray-700">
                                <i data-lucide="x" class="w-6 h-6"></i>
                            </button>
                        </div>
                    </div>
                    <div class="p-6" id="block-details">
                        <!-- Block details will be loaded here -->
                    </div>
                </div>
            </div>
        </div>
    </main>

    <footer class="bg-gray-800 text-white mt-12">
        <div class="container mx-auto px-4 py-6 text-center">
            <p class="text-sm">AITBC Blockchain Explorer - Connected to node at {node_url}</p>
        </div>
    </footer>

    <script>
        // Initialize lucide icons
        lucide.createIcons();

        // Global state
        let currentData = {};

        // Load initial data
        document.addEventListener('DOMContentLoaded', () => {
            refreshData();
        });

        // Refresh all data
        async function refreshData() {
            try {
                await Promise.all([
                    loadChainStats(),
                    loadLatestBlocks()
                ]);
            } catch (error) {
                console.error('Error refreshing data:', error);
                document.getElementById('node-status').innerHTML = '<span class="text-red-500">Error</span>';
            }
        }

        // Load chain statistics
        async function loadChainStats() {
            const response = await fetch('/api/chain/head');
            const data = await response.json();
            
            document.getElementById('chain-height').textContent = data.height || '-';
            document.getElementById('latest-hash').textContent = data.hash ? data.hash.substring(0, 16) + '...' : '-';
            document.getElementById('node-status').innerHTML = '<span class="text-green-500">Online</span>';
            
            currentData.head = data;
        }

        // Load latest blocks
        async function loadLatestBlocks() {
            const tbody = document.getElementById('blocks-table');
            tbody.innerHTML = '<tr><td colspan="5" class="text-center py-8 text-gray-500">Loading blocks...</td></tr>';
            
            const head = await fetch('/api/chain/head').then(r => r.json());
            const blocks = [];
            
            // Load last 10 blocks
            for (let i = 0; i < 10 && head.height - i >= 0; i++) {
                const block = await fetch(`/api/blocks/${head.height - i}`).then(r => r.json());
                blocks.push(block);
            }
            
            tbody.innerHTML = blocks.map(block => `
                <tr class="border-t hover:bg-gray-50">
                    <td class="py-3 font-mono">${block.height}</td>
                    <td class="py-3 font-mono text-sm">${block.hash ? block.hash.substring(0, 16) + '...' : '-'}</td>
                    <td class="py-3 text-sm">${formatTimestamp(block.timestamp)}</td>
                    <td class="py-3">${block.transactions ? block.transactions.length : 0}</td>
                    <td class="py-3">
                        <button onclick="showBlockDetails(${block.height})" class="text-blue-600 hover:text-blue-800">
                            View Details
                        </button>
                    </td>
                </tr>
            `).join('');
        }

        // Show block details
        async function showBlockDetails(height) {
            const block = await fetch(`/api/blocks/${height}`).then(r => r.json());
            const modal = document.getElementById('block-modal');
            const details = document.getElementById('block-details');
            
            details.innerHTML = `
                <div class="space-y-6">
                    <div>
                        <h3 class="text-lg font-semibold mb-2">Block Header</h3>
                        <div class="bg-gray-50 rounded p-4 space-y-2">
                            <div class="flex justify-between">
                                <span class="text-gray-600">Height:</span>
                                <span class="font-mono">${block.height}</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-gray-600">Hash:</span>
                                <span class="font-mono text-sm">${block.hash || '-'}</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-gray-600">Parent Hash:</span>
                                <span class="font-mono text-sm">${block.parent_hash || '-'}</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-gray-600">Timestamp:</span>
                                <span>${formatTimestamp(block.timestamp)}</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-gray-600">Proposer:</span>
                                <span class="font-mono text-sm">${block.proposer || '-'}</span>
                            </div>
                        </div>
                    </div>
                    
                    ${block.transactions && block.transactions.length > 0 ? `
                    <div>
                        <h3 class="text-lg font-semibold mb-2">Transactions (${block.transactions.length})</h3>
                        <div class="space-y-2">
                            ${block.transactions.map(tx => `
                                <div class="bg-gray-50 rounded p-4">
                                    <div class="flex justify-between mb-2">
                                        <span class="text-gray-600">Hash:</span>
                                        <span class="font-mono text-sm">${tx.hash || '-'}</span>
                                    </div>
                                    <div class="flex justify-between mb-2">
                                        <span class="text-gray-600">Type:</span>
                                        <span>${tx.type || '-'}</span>
                                    </div>
                                    <div class="flex justify-between mb-2">
                                        <span class="text-gray-600">From:</span>
                                        <span class="font-mono text-sm">${tx.sender || '-'}</span>
                                    </div>
                                    <div class="flex justify-between">
                                        <span class="text-gray-600">Fee:</span>
                                        <span>${tx.fee || '0'}</span>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                    ` : '<p class="text-gray-500">No transactions in this block</p>'}
                </div>
            `;
            
            modal.classList.remove('hidden');
        }

        // Close modal
        function closeModal() {
            document.getElementById('block-modal').classList.add('hidden');
        }

        // Search functionality
        async function search() {
            const query = document.getElementById('search-input').value.trim();
            if (!query) return;
            
            // Try block height first
            if (/^\\d+$/.test(query)) {
                showBlockDetails(parseInt(query));
                return;
            }
            
            // TODO: Add transaction hash search
            alert('Search by block height is currently supported');
        }

        // Format timestamp
        function formatTimestamp(timestamp) {
            if (!timestamp) return '-';
            return new Date(timestamp * 1000).toLocaleString();
        }

        // Auto-refresh every 30 seconds
        setInterval(refreshData, 30000);
    </script>
</body>
</html>
"""

async def get_chain_head() -> Dict[str, Any]:
    """Get the current chain head"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BLOCKCHAIN_RPC_URL}/rpc/head")
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        print(f"Error getting chain head: {e}")
    return {}

async def get_block(height: int) -> Dict[str, Any]:
    """Get a specific block by height"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BLOCKCHAIN_RPC_URL}/rpc/blocks/{height}")
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        print(f"Error getting block {height}: {e}")
    return {}

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the explorer UI"""
    return HTML_TEMPLATE.format(node_url=BLOCKCHAIN_RPC_URL)

@app.get("/api/chain/head")
async def api_chain_head():
    """API endpoint for chain head"""
    return await get_chain_head()

@app.get("/api/blocks/{height}")
async def api_block(height: int):
    """API endpoint for block data"""
    return await get_block(height)

@app.get("/health")
async def health():
    """Health check endpoint"""
    head = await get_chain_head()
    return {
        "status": "ok" if head else "error",
        "node_url": BLOCKCHAIN_RPC_URL,
        "chain_height": head.get("height", 0)
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000)
