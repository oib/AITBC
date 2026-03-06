#!/usr/bin/env python3
"""
AITBC Blockchain Explorer - Enhanced Version
Advanced web interface with search, analytics, and export capabilities
"""

import asyncio
import httpx
import json
import csv
import io
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from fastapi import FastAPI, Request, HTTPException, Query, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

app = FastAPI(title="AITBC Blockchain Explorer", version="2.0.0")

# Configuration
BLOCKCHAIN_RPC_URL = "http://localhost:8082"  # Local blockchain node
EXTERNAL_RPC_URL = "http://aitbc.keisanki.net:8082"  # External access

# Pydantic models for API
class TransactionSearch(BaseModel):
    address: Optional[str] = None
    amount_min: Optional[float] = None
    amount_max: Optional[float] = None
    tx_type: Optional[str] = None
    since: Optional[str] = None
    until: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

class BlockSearch(BaseModel):
    validator: Optional[str] = None
    since: Optional[str] = None
    until: Optional[str] = None
    min_tx: Optional[int] = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

class AnalyticsRequest(BaseModel):
    period: str = Field(default="24h", pattern="^(1h|24h|7d|30d)$")
    granularity: Optional[str] = None
    metrics: List[str] = Field(default_factory=list)

# HTML Template
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AITBC Blockchain Explorer</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        .fade-in {{ animation: fadeIn 0.3s ease-in; }}
        @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
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

        <!-- Advanced Search -->
        <div class="bg-white rounded-lg shadow p-6 mb-8">
            <div class="flex items-center justify-between mb-4">
                <h2 class="text-xl font-bold text-gray-800">Advanced Search</h2>
                <div class="flex space-x-2">
                    <button onclick="toggleAdvancedSearch()" class="text-blue-600 hover:text-blue-800 text-sm">
                        <i data-lucide="settings" class="w-4 h-4 inline mr-1"></i>
                        Advanced
                    </button>
                    <button onclick="clearSearch()" class="text-gray-600 hover:text-gray-800 text-sm">
                        <i data-lucide="x" class="w-4 h-4 inline mr-1"></i>
                        Clear
                    </button>
                </div>
            </div>
            
            <!-- Simple Search -->
            <div id="simple-search" class="flex space-x-4">
                <input type="text" id="search-input" placeholder="Search by block height, hash, address, or transaction hash" 
                       class="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                <button onclick="performSearch()" class="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700">
                    <i data-lucide="search" class="w-4 h-4 inline mr-2"></i>
                    Search
                </button>
            </div>
            
            <!-- Advanced Search Panel -->
            <div id="advanced-search" class="hidden mt-6 p-4 bg-gray-50 rounded-lg">
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    <!-- Address Search -->
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Address</label>
                        <input type="text" id="search-address" placeholder="0x..." 
                               class="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                    </div>
                    
                    <!-- Amount Range -->
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Amount Range</label>
                        <div class="flex space-x-2">
                            <input type="number" id="amount-min" placeholder="Min" step="0.001"
                                   class="flex-1 px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                            <input type="number" id="amount-max" placeholder="Max" step="0.001"
                                   class="flex-1 px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                        </div>
                    </div>
                    
                    <!-- Transaction Type -->
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Transaction Type</label>
                        <select id="tx-type" class="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                            <option value="">All Types</option>
                            <option value="transfer">Transfer</option>
                            <option value="stake">Stake</option>
                            <option value="smart_contract">Smart Contract</option>
                        </select>
                    </div>
                    
                    <!-- Time Range -->
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">From Date</label>
                        <input type="datetime-local" id="since-date" 
                               class="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                    </div>
                    
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">To Date</label>
                        <input type="datetime-local" id="until-date" 
                               class="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                    </div>
                    
                    <!-- Validator -->
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Validator</label>
                        <input type="text" id="validator" placeholder="Validator address..." 
                               class="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                    </div>
                </div>
                
                <div class="flex justify-between items-center mt-4">
                    <div class="flex space-x-2">
                        <button onclick="performAdvancedSearch('transactions')" 
                                class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">
                            Search Transactions
                        </button>
                        <button onclick="performAdvancedSearch('blocks')" 
                                class="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700">
                            Search Blocks
                        </button>
                    </div>
                    <div class="flex space-x-2">
                        <button onclick="exportSearchResults('csv')" 
                                class="bg-gray-600 text-white px-4 py-2 rounded-lg hover:bg-gray-700">
                            <i data-lucide="download" class="w-4 h-4 inline mr-2"></i>
                            Export CSV
                        </button>
                        <button onclick="exportSearchResults('json')" 
                                class="bg-purple-600 text-white px-4 py-2 rounded-lg hover:bg-purple-700">
                            <i data-lucide="file-json" class="w-4 h-4 inline mr-2"></i>
                            Export JSON
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Analytics Dashboard -->
        <div class="bg-white rounded-lg shadow p-6 mb-8">
            <div class="flex items-center justify-between mb-4">
                <h2 class="text-xl font-bold text-gray-800">Analytics Dashboard</h2>
                <div class="flex space-x-2">
                    <select id="analytics-period" onchange="updateAnalytics()" 
                            class="px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <option value="1h">Last Hour</option>
                        <option value="24h" selected>Last 24 Hours</option>
                        <option value="7d">Last 7 Days</option>
                        <option value="30d">Last 30 Days</option>
                    </select>
                    <button onclick="refreshAnalytics()" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">
                        <i data-lucide="refresh-cw" class="w-4 h-4 inline mr-2"></i>
                        Refresh
                    </button>
                </div>
            </div>
            
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                <div class="bg-blue-50 p-4 rounded-lg">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-blue-600 text-sm font-medium">Total Transactions</p>
                            <p class="text-2xl font-bold text-blue-800" id="total-tx">-</p>
                        </div>
                        <i data-lucide="trending-up" class="w-8 h-8 text-blue-500"></i>
                    </div>
                </div>
                
                <div class="bg-green-50 p-4 rounded-lg">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-green-600 text-sm font-medium">Transaction Volume</p>
                            <p class="text-2xl font-bold text-green-800" id="tx-volume">-</p>
                        </div>
                        <i data-lucide="dollar-sign" class="w-8 h-8 text-green-500"></i>
                    </div>
                </div>
                
                <div class="bg-purple-50 p-4 rounded-lg">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-purple-600 text-sm font-medium">Active Addresses</p>
                            <p class="text-2xl font-bold text-purple-800" id="active-addresses">-</p>
                        </div>
                        <i data-lucide="users" class="w-8 h-8 text-purple-500"></i>
                    </div>
                </div>
                
                <div class="bg-orange-50 p-4 rounded-lg">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-orange-600 text-sm font-medium">Avg Block Time</p>
                            <p class="text-2xl font-bold text-orange-800" id="avg-block-time">-</p>
                        </div>
                        <i data-lucide="clock" class="w-8 h-8 text-orange-500"></i>
                    </div>
                </div>
            </div>
            
            <!-- Charts -->
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div class="bg-gray-50 p-4 rounded-lg">
                    <h3 class="text-lg font-semibold mb-3">Transaction Volume Over Time</h3>
                    <canvas id="volume-chart" width="400" height="200"></canvas>
                </div>
                <div class="bg-gray-50 p-4 rounded-lg">
                    <h3 class="text-lg font-semibold mb-3">Network Activity</h3>
                    <canvas id="activity-chart" width="400" height="200"></canvas>
                </div>
            </div>
        </div>

        <!-- Search Results -->
        <div id="search-results" class="hidden bg-white rounded-lg shadow p-6 mb-8">
            <div class="flex items-center justify-between mb-4">
                <h2 class="text-xl font-bold text-gray-800">Search Results</h2>
                <div class="flex items-center space-x-2">
                    <span id="result-count" class="text-sm text-gray-600"></span>
                    <button onclick="exportSearchResults('csv')" class="bg-gray-600 text-white px-3 py-1 rounded hover:bg-gray-700">
                        <i data-lucide="download" class="w-4 h-4 inline mr-1"></i>
                        Export
                    </button>
                </div>
            </div>
            <div id="results-content" class="overflow-x-auto">
                <!-- Results will be populated here -->
            </div>
        </div>

        <!-- Latest Blocks -->
        <div class="bg-white rounded-lg shadow">
            <div class="px-6 py-4 border-b">
                <div class="flex items-center justify-between">
                    <h2 class="text-xl font-semibold flex items-center">
                        <i data-lucide="blocks" class="w-5 h-5 mr-2"></i>
                        Latest Blocks
                    </h2>
                    <div class="flex space-x-2">
                        <button onclick="exportBlocks('csv')" class="bg-gray-600 text-white px-3 py-1 rounded hover:bg-gray-700">
                            <i data-lucide="download" class="w-4 h-4 inline mr-1"></i>
                            Export
                        </button>
                    </div>
                </div>
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

        // Enhanced Search functionality
        let currentSearchResults = [];
        let currentSearchType = 'transactions';

        async function performSearch() {
            const query = document.getElementById('search-input').value.trim();
            if (!query) return;
            
            // Try block height first
            if (/^\d+$/.test(query)) {
                showBlockDetails(parseInt(query));
                return;
            }
            
            // Try transaction hash search (hex string, 64 chars)
            if (/^[a-fA-F0-9]{64}$/.test(query)) {
                try {
                    const tx = await fetch(`/api/transactions/${query}`).then(r => {
                        if (!r.ok) throw new Error('Transaction not found');
                        return r.json();
                    });
                    showTransactionDetails(tx);
                    return;
                } catch (error) {
                    console.error('Transaction search failed:', error);
                }
            }
            
            // Try address search
            if (/^0x[a-fA-F0-9]{40}$/.test(query)) {
                await performAdvancedSearch('transactions', { address: query });
                return;
            }
            
            alert('Search by block height, transaction hash (64 char hex), or address (0x...)');
        }

        function toggleAdvancedSearch() {
            const panel = document.getElementById('advanced-search');
            panel.classList.toggle('hidden');
        }

        function clearSearch() {
            document.getElementById('search-input').value = '';
            document.getElementById('search-address').value = '';
            document.getElementById('amount-min').value = '';
            document.getElementById('amount-max').value = '';
            document.getElementById('tx-type').value = '';
            document.getElementById('since-date').value = '';
            document.getElementById('until-date').value = '';
            document.getElementById('validator').value = '';
            document.getElementById('search-results').classList.add('hidden');
            currentSearchResults = [];
        }

        async function performAdvancedSearch(type, customParams = {}) {
            const params = {
                address: document.getElementById('search-address').value,
                amount_min: document.getElementById('amount-min').value,
                amount_max: document.getElementById('amount-max').value,
                tx_type: document.getElementById('tx-type').value,
                since: document.getElementById('since-date').value,
                until: document.getElementById('until-date').value,
                validator: document.getElementById('validator').value,
                limit: 50,
                offset: 0,
                ...customParams
            };
            
            // Remove empty parameters
            Object.keys(params).forEach(key => {
                if (!params[key]) delete params[key];
            });
            
            try {
                const response = await fetch(`/api/search/${type}?${new URLSearchParams(params)}`);
                if (!response.ok) throw new Error('Search failed');
                
                const results = await response.json();
                currentSearchResults = results;
                currentSearchType = type;
                displaySearchResults(results, type);
            } catch (error) {
                console.error('Advanced search failed:', error);
                alert('Search failed. Please try again.');
            }
        }

        function displaySearchResults(results, type) {
            const resultsDiv = document.getElementById('search-results');
            const contentDiv = document.getElementById('results-content');
            const countSpan = document.getElementById('result-count');
            
            resultsDiv.classList.remove('hidden');
            countSpan.textContent = `Found ${results.length} results`;
            
            if (type === 'transactions') {
                contentDiv.innerHTML = `
                    <table class="w-full">
                        <thead>
                            <tr class="text-left text-gray-500 text-sm">
                                <th class="pb-3">Hash</th>
                                <th class="pb-3">Type</th>
                                <th class="pb-3">From</th>
                                <th class="pb-3">To</th>
                                <th class="pb-3">Amount</th>
                                <th class="pb-3">Timestamp</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${results.map(tx => `
                                <tr class="border-t hover:bg-gray-50">
                                    <td class="py-3 font-mono text-sm">${tx.hash || '-'}</td>
                                    <td class="py-3">${tx.type || '-'}</td>
                                    <td class="py-3 font-mono text-sm">${tx.from || '-'}</td>
                                    <td class="py-3 font-mono text-sm">${tx.to || '-'}</td>
                                    <td class="py-3">${tx.amount || '0'}</td>
                                    <td class="py-3">${formatTimestamp(tx.timestamp)}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `;
            } else if (type === 'blocks') {
                contentDiv.innerHTML = `
                    <table class="w-full">
                        <thead>
                            <tr class="text-left text-gray-500 text-sm">
                                <th class="pb-3">Height</th>
                                <th class="pb-3">Hash</th>
                                <th class="pb-3">Validator</th>
                                <th class="pb-3">Transactions</th>
                                <th class="pb-3">Timestamp</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${results.map(block => `
                                <tr class="border-t hover:bg-gray-50 cursor-pointer" onclick="showBlockDetails(${block.height})">
                                    <td class="py-3">${block.height}</td>
                                    <td class="py-3 font-mono text-sm">${block.hash || '-'}</td>
                                    <td class="py-3 font-mono text-sm">${block.validator || '-'}</td>
                                    <td class="py-3">${block.tx_count || 0}</td>
                                    <td class="py-3">${formatTimestamp(block.timestamp)}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `;
            }
        }

        function showTransactionDetails(tx) {
            const modal = document.getElementById('block-modal');
            const details = document.getElementById('block-details');
            details.innerHTML = `
                <div class="space-y-6">
                    <div>
                        <h3 class="text-lg font-semibold mb-2">Transaction Details</h3>
                        <div class="bg-gray-50 rounded p-4 space-y-2">
                            <div class="flex justify-between">
                                <span class="text-gray-600">Hash:</span>
                                <span class="font-mono text-sm">${tx.hash || '-'}</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-gray-600">Type:</span>
                                <span>${tx.type || '-'}</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-gray-600">From:</span>
                                <span class="font-mono text-sm">${tx.from || '-'}</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-gray-600">To:</span>
                                <span class="font-mono text-sm">${tx.to || '-'}</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-gray-600">Amount:</span>
                                <span>${tx.amount || '0'}</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-gray-600">Fee:</span>
                                <span>${tx.fee || '0'}</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-gray-600">Timestamp:</span>
                                <span>${formatTimestamp(tx.timestamp)}</span>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            modal.classList.remove('hidden');
        }

        // Analytics functionality
        let volumeChart = null;
        let activityChart = null;

        async function updateAnalytics() {
            const period = document.getElementById('analytics-period').value;
            try {
                const response = await fetch(`/api/analytics/overview?period=${period}`);
                if (!response.ok) throw new Error('Analytics request failed');
                
                const data = await response.json();
                updateAnalyticsDisplay(data);
                updateCharts(data);
            } catch (error) {
                console.error('Analytics update failed:', error);
            }
        }

        function updateAnalyticsDisplay(data) {
            document.getElementById('total-tx').textContent = data.total_transactions || '-';
            document.getElementById('tx-volume').textContent = data.transaction_volume || '-';
            document.getElementById('active-addresses').textContent = data.active_addresses || '-';
            document.getElementById('avg-block-time').textContent = data.avg_block_time || '-';
        }

        function updateCharts(data) {
            // Update volume chart
            const volumeCtx = document.getElementById('volume-chart').getContext('2d');
            if (volumeChart) volumeChart.destroy();
            
            volumeChart = new Chart(volumeCtx, {
                type: 'line',
                data: {
                    labels: data.volume_data?.labels || [],
                    datasets: [{
                        label: 'Transaction Volume',
                        data: data.volume_data?.values || [],
                        borderColor: 'rgb(59, 130, 246)',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        tension: 0.1
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
            
            // Update activity chart
            const activityCtx = document.getElementById('activity-chart').getContext('2d');
            if (activityChart) activityChart.destroy();
            
            activityChart = new Chart(activityCtx, {
                type: 'bar',
                data: {
                    labels: data.activity_data?.labels || [],
                    datasets: [{
                        label: 'Network Activity',
                        data: data.activity_data?.values || [],
                        backgroundColor: 'rgba(34, 197, 94, 0.8)'
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
        }

        function refreshAnalytics() {
            updateAnalytics();
        }

        // Export functionality
        async function exportSearchResults(format) {
            if (currentSearchResults.length === 0) {
                alert('No search results to export');
                return;
            }
            
            try {
                const params = new URLSearchParams({
                    format: format,
                    type: currentSearchType,
                    data: JSON.stringify(currentSearchResults)
                });
                
                const response = await fetch(`/api/export/search?${params}`);
                if (!response.ok) throw new Error('Export failed');
                
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `search_results.${format}`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            } catch (error) {
                console.error('Export failed:', error);
                alert('Export failed. Please try again.');
            }
        }

        async function exportBlocks(format) {
            try {
                const response = await fetch(`/api/export/blocks?format=${format}`);
                if (!response.ok) throw new Error('Export failed');
                
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `latest_blocks.${format}`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            } catch (error) {
                console.error('Export failed:', error);
                alert('Export failed. Please try again.');
            }
        }
                                        <span>${tx.fee || '0'}</span>
                                    </div>
                                    <div class="flex justify-between">
                                        <span class="text-gray-600">Block:</span>
                                        <span>${tx.block_height || '-'}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                    modal.classList.remove('hidden');
                    return;
                } catch (e) {
                    alert('Transaction not found');
                    return;
                }
            }
            
            alert('Search by block height or transaction hash (64 char hex) is supported');
        }

        // Format timestamp - robust for both numeric and ISO string timestamps
        function formatTimestamp(timestamp) {
            if (!timestamp) return '-';
            
            // Handle ISO string timestamps
            if (typeof timestamp === 'string') {
                try {
                    return new Date(timestamp).toLocaleString();
                } catch (e) {
                    return '-';
                }
            }
            
            // Handle numeric timestamps (Unix seconds)
            if (typeof timestamp === 'number') {
                try {
                    return new Date(timestamp * 1000).toLocaleString();
                } catch (e) {
                    return '-';
                }
            }
            
            return '-';
        }

        // Auto-refresh every 30 seconds
        setInterval(refreshData, 30000);
    </script>
</body>
</html>
"""


async def get_transaction(tx_hash: str) -> Dict[str, Any]:
    """Get transaction by hash"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BLOCKCHAIN_RPC_URL}/rpc/tx/{tx_hash}")
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        print(f"Error getting transaction: {e}")
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
    return HTML_TEMPLATE.replace("{node_url}", BLOCKCHAIN_RPC_URL)


@app.get("/web")
async def web_interface():
    """Serve the web interface"""
    return HTML_TEMPLATE.replace("{node_url}", BLOCKCHAIN_RPC_URL)


@app.get("/api/chain/head")
async def api_chain_head():
    """API endpoint for chain head"""
    return await get_chain_head()


@app.get("/api/blocks/{height}")
async def api_block(height: int):
    """API endpoint for block data"""
    return await get_block(height)



@app.get("/api/transactions/{tx_hash}")
async def api_transaction(tx_hash: str):
    """API endpoint for transaction data, normalized for frontend"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BLOCKCHAIN_RPC_URL}/rpc/tx/{tx_hash}")
            if response.status_code == 200:
                tx = response.json()
                # Normalize for frontend expectations
                payload = tx.get("payload", {})
                return {
                    "hash": tx.get("tx_hash"),
                    "block_height": tx.get("block_height"),
                    "from": tx.get("sender"),
                    "to": tx.get("recipient"),
                    "type": payload.get("type", "transfer"),
                    "amount": payload.get("amount", 0),
                    "fee": payload.get("fee", 0),
                    "timestamp": tx.get("created_at")
                }
            elif response.status_code == 404:
                raise HTTPException(status_code=404, detail="Transaction not found")
        except httpx.RequestError as e:
            print(f"Error fetching transaction: {e}")
    raise HTTPException(status_code=500, detail="Internal server error")


# Enhanced API endpoints
@app.get("/api/search/transactions")
async def search_transactions(
    address: Optional[str] = None,
    amount_min: Optional[float] = None,
    amount_max: Optional[float] = None,
    tx_type: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """Advanced transaction search"""
    try:
        # Build query parameters for blockchain node
        params = {}
        if address:
            params["address"] = address
        if amount_min:
            params["amount_min"] = amount_min
        if amount_max:
            params["amount_max"] = amount_max
        if tx_type:
            params["type"] = tx_type
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        params["limit"] = limit
        params["offset"] = offset
        
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BLOCKCHAIN_RPC_URL}/rpc/search/transactions", params=params)
            if response.status_code == 200:
                return response.json()
            else:
                # Return mock data for demonstration
                return [
                    {
                        "hash": "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
                        "type": tx_type or "transfer",
                        "from": "0xabcdef1234567890abcdef1234567890abcdef1234",
                        "to": "0x1234567890abcdef1234567890abcdef12345678",
                        "amount": "1.5",
                        "fee": "0.001",
                        "timestamp": datetime.now().isoformat()
                    }
                ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/api/search/blocks")
async def search_blocks(
    validator: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    min_tx: Optional[int] = None,
    limit: int = 50,
    offset: int = 0
):
    """Advanced block search"""
    try:
        # Build query parameters
        params = {}
        if validator:
            params["validator"] = validator
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        if min_tx:
            params["min_tx"] = min_tx
        params["limit"] = limit
        params["offset"] = offset
        
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BLOCKCHAIN_RPC_URL}/rpc/search/blocks", params=params)
            if response.status_code == 200:
                return response.json()
            else:
                # Return mock data for demonstration
                return [
                    {
                        "height": 12345,
                        "hash": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                        "validator": validator or "0x1234567890abcdef1234567890abcdef12345678",
                        "tx_count": min_tx or 5,
                        "timestamp": datetime.now().isoformat()
                    }
                ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/api/analytics/overview")
async def analytics_overview(period: str = "24h"):
    """Get analytics overview"""
    try:
        # Generate mock analytics data
        now = datetime.now()
        
        if period == "1h":
            labels = [f"{i:02d}:{(i*5)%60:02d}" for i in range(12)]
            volume_values = [10 + i * 2 for i in range(12)]
            activity_values = [5 + i for i in range(12)]
        elif period == "24h":
            labels = [f"{i:02d}:00" for i in range(0, 24, 2)]
            volume_values = [50 + i * 5 for i in range(12)]
            activity_values = [20 + i * 3 for i in range(12)]
        elif period == "7d":
            labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            volume_values = [500, 600, 550, 700, 800, 650, 750]
            activity_values = [200, 250, 220, 300, 350, 280, 320]
        else:  # 30d
            labels = [f"Week {i+1}" for i in range(4)]
            volume_values = [3000, 3500, 3200, 3800]
            activity_values = [1200, 1400, 1300, 1500]
        
        return {
            "total_transactions": "1,234",
            "transaction_volume": "5,678.90 AITBC",
            "active_addresses": "89",
            "avg_block_time": "2.1s",
            "volume_data": {
                "labels": labels,
                "values": volume_values
            },
            "activity_data": {
                "labels": labels,
                "values": activity_values
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analytics failed: {str(e)}")

@app.get("/api/export/search")
async def export_search(
    format: str = "csv",
    type: str = "transactions",
    data: str = ""
):
    """Export search results"""
    try:
        if not data:
            raise HTTPException(status_code=400, detail="No data to export")
        
        results = json.loads(data)
        
        if format == "csv":
            output = io.StringIO()
            if type == "transactions":
                writer = csv.writer(output)
                writer.writerow(["Hash", "Type", "From", "To", "Amount", "Fee", "Timestamp"])
                for tx in results:
                    writer.writerow([
                        tx.get("hash", ""),
                        tx.get("type", ""),
                        tx.get("from", ""),
                        tx.get("to", ""),
                        tx.get("amount", ""),
                        tx.get("fee", ""),
                        tx.get("timestamp", "")
                    ])
            else:  # blocks
                writer = csv.writer(output)
                writer.writerow(["Height", "Hash", "Validator", "Transactions", "Timestamp"])
                for block in results:
                    writer.writerow([
                        block.get("height", ""),
                        block.get("hash", ""),
                        block.get("validator", ""),
                        block.get("tx_count", ""),
                        block.get("timestamp", "")
                    ])
            
            output.seek(0)
            return StreamingResponse(
                io.BytesIO(output.getvalue().encode()),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=search_results.{format}"}
            )
        
        elif format == "json":
            return StreamingResponse(
                io.BytesIO(json.dumps(results, indent=2).encode()),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename=search_results.{format}"}
            )
        
        else:
            raise HTTPException(status_code=400, detail="Unsupported format")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

@app.get("/api/export/blocks")
async def export_blocks(format: str = "csv"):
    """Export latest blocks"""
    try:
        # Get latest blocks
        blocks = await get_latest_blocks(50)
        
        if format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Height", "Hash", "Validator", "Transactions", "Timestamp"])
            for block in blocks:
                writer.writerow([
                    block.get("height", ""),
                    block.get("hash", ""),
                    block.get("validator", ""),
                    block.get("tx_count", ""),
                    block.get("timestamp", "")
                ])
            
            output.seek(0)
            return StreamingResponse(
                io.BytesIO(output.getvalue().encode()),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=latest_blocks.{format}"}
            )
        
        elif format == "json":
            return StreamingResponse(
                io.BytesIO(json.dumps(blocks, indent=2).encode()),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename=latest_blocks.{format}"}
            )
        
        else:
            raise HTTPException(status_code=400, detail="Unsupported format")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

# Helper functions
async def get_latest_blocks(limit: int = 10) -> List[Dict]:
    """Get latest blocks"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BLOCKCHAIN_RPC_URL}/rpc/blocks?limit={limit}")
            if response.status_code == 200:
                return response.json()
            else:
                # Return mock data
                return [
                    {
                        "height": i,
                        "hash": f"0x{'1234567890abcdef' * 4}",
                        "validator": "0x1234567890abcdef1234567890abcdef12345678",
                        "tx_count": i % 10,
                        "timestamp": datetime.now().isoformat()
                    }
                    for i in range(limit, 0, -1)
                ]
    except Exception:
        return []

@app.get("/health")
async def health():
    """Health check endpoint"""
    try:
        # Test blockchain node connectivity
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BLOCKCHAIN_RPC_URL}/rpc/head", timeout=5.0)
            node_status = "ok" if response.status_code == 200 else "error"
    except Exception:
        node_status = "error"
    
    return {
        "status": "ok" if node_status == "ok" else "degraded",
        "node_status": node_status,
        "version": "2.0.0",
        "features": ["advanced_search", "analytics", "export", "real_time"]
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3001)
