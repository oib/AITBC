#!/usr/bin/env python3
"""
Simple AITBC Blockchain Explorer - Demonstrating the issues described in the analysis
"""

import asyncio
import httpx
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="Simple AITBC Explorer", version="0.1.0")

# Configuration
BLOCKCHAIN_RPC_URL = "http://localhost:8025"

# HTML Template with the problematic frontend
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Simple AITBC Explorer</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50">
    <div class="container mx-auto px-4 py-8">
        <h1 class="text-3xl font-bold mb-8">AITBC Blockchain Explorer</h1>
        
        <!-- Search -->
        <div class="bg-white rounded-lg shadow p-6 mb-8">
            <h2 class="text-xl font-semibold mb-4">Search</h2>
            <div class="flex space-x-4">
                <input type="text" id="search-input" placeholder="Search by transaction hash (64 chars)" 
                       class="flex-1 px-4 py-2 border rounded-lg">
                <button onclick="performSearch()" class="bg-blue-600 text-white px-6 py-2 rounded-lg">
                    Search
                </button>
            </div>
        </div>
        
        <!-- Results -->
        <div id="results" class="hidden bg-white rounded-lg shadow p-6">
            <h2 class="text-xl font-semibold mb-4">Transaction Details</h2>
            <div id="tx-details"></div>
        </div>
        
        <!-- Latest Blocks -->
        <div class="bg-white rounded-lg shadow p-6">
            <h2 class="text-xl font-semibold mb-4">Latest Blocks</h2>
            <div id="blocks-list"></div>
        </div>
    </div>

    <script>
        // Problem 1: Frontend calls /api/transactions/{hash} but backend doesn't have it
        async function performSearch() {
            const query = document.getElementById('search-input').value.trim();
            if (!query) return;
            
            if (/^[a-fA-F0-9]{64}$/.test(query)) {
                try {
                    const tx = await fetch(`/api/transactions/${query}`).then(r => {
                        if (!r.ok) throw new Error('Transaction not found');
                        return r.json();
                    });
                    showTransactionDetails(tx);
                } catch (error) {
                    alert('Transaction not found');
                }
            } else {
                alert('Please enter a valid 64-character hex transaction hash');
            }
        }
        
        // Problem 2: UI expects tx.hash, tx.from, tx.to, tx.amount, tx.fee
        // But RPC returns tx_hash, sender, recipient, payload, created_at
        function showTransactionDetails(tx) {
            const resultsDiv = document.getElementById('results');
            const detailsDiv = document.getElementById('tx-details');
            
            detailsDiv.innerHTML = `
                <div class="space-y-4">
                    <div><strong>Hash:</strong> ${tx.hash || 'N/A'}</div>
                    <div><strong>From:</strong> ${tx.from || 'N/A'}</div>
                    <div><strong>To:</strong> ${tx.to || 'N/A'}</div>
                    <div><strong>Amount:</strong> ${tx.amount || 'N/A'}</div>
                    <div><strong>Fee:</strong> ${tx.fee || 'N/A'}</div>
                    <div><strong>Timestamp:</strong> ${formatTimestamp(tx.timestamp)}</div>
                </div>
            `;
            
            resultsDiv.classList.remove('hidden');
        }
        
        // Problem 3: formatTimestamp now handles both numeric and ISO string timestamps
        function formatTimestamp(timestamp) {
            if (!timestamp) return 'N/A';
            
            // Handle ISO string timestamps
            if (typeof timestamp === 'string') {
                try {
                    return new Date(timestamp).toLocaleString();
                } catch (e) {
                    return 'Invalid timestamp';
                }
            }
            
            // Handle numeric timestamps (Unix seconds)
            if (typeof timestamp === 'number') {
                try {
                    return new Date(timestamp * 1000).toLocaleString();
                } catch (e) {
                    return 'Invalid timestamp';
                }
            }
            
            return 'Invalid timestamp format';
        }
        
        // Load latest blocks
        async function loadBlocks() {
            try {
                const head = await fetch('/api/chain/head').then(r => r.json());
                const blocksList = document.getElementById('blocks-list');
                
                let html = '<div class="space-y-4">';
                for (let i = 0; i < 5 && head.height - i >= 0; i++) {
                    const block = await fetch(`/api/blocks/${head.height - i}`).then(r => r.json());
                    html += `
                        <div class="border rounded p-4">
                            <div><strong>Height:</strong> ${block.height}</div>
                            <div><strong>Hash:</strong> ${block.hash ? block.hash.substring(0, 16) + '...' : 'N/A'}</div>
                            <div><strong>Time:</strong> ${formatTimestamp(block.timestamp)}</div>
                        </div>
                    `;
                }
                html += '</div>';
                blocksList.innerHTML = html;
            } catch (error) {
                console.error('Failed to load blocks:', error);
            }
        }
        
        // Initialize
        document.addEventListener('DOMContentLoaded', () => {
            loadBlocks();
        });
    </script>
</body>
</html>
"""

# Problem 1: Only /api/chain/head and /api/blocks/{height} defined, missing /api/transactions/{hash}
@app.get("/api/chain/head")
async def get_chain_head():
    """Get current chain head"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BLOCKCHAIN_RPC_URL}/rpc/head")
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        print(f"Error getting chain head: {e}")
    return {"height": 0, "hash": "", "timestamp": None}

@app.get("/api/blocks/{height}")
async def get_block(height: int):
    """Get block by height"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BLOCKCHAIN_RPC_URL}/rpc/blocks/{height}")
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        print(f"Error getting block {height}: {e}")
    return {"height": height, "hash": "", "timestamp": None, "transactions": []}

@app.get("/api/transactions/{tx_hash}")
async def get_transaction(tx_hash: str):
    """Get transaction by hash - Problem 1: This endpoint was missing"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BLOCKCHAIN_RPC_URL}/rpc/tx/{tx_hash}")
            if response.status_code == 200:
                tx_data = response.json()
                # Problem 2: Map RPC schema to UI schema
                return {
                    "hash": tx_data.get("tx_hash", tx_hash),  # tx_hash -> hash
                    "from": tx_data.get("sender", "unknown"),   # sender -> from
                    "to": tx_data.get("recipient", "unknown"),  # recipient -> to
                    "amount": tx_data.get("payload", {}).get("value", "0"),  # payload.value -> amount
                    "fee": tx_data.get("payload", {}).get("fee", "0"),        # payload.fee -> fee
                    "timestamp": tx_data.get("created_at"),     # created_at -> timestamp
                    "block_height": tx_data.get("block_height", "pending")
                }
            elif response.status_code == 404:
                raise HTTPException(status_code=404, detail="Transaction not found")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting transaction {tx_hash}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch transaction: {str(e)}")

# Missing: @app.get("/api/transactions/{tx_hash}") - THIS IS THE PROBLEM

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the explorer UI"""
    return HTML_TEMPLATE

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8017)
