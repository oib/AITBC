"""
Simple AITBC Blockchain Explorer - Demonstrating the issues described in the analysis
"""

import re

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.network.http_client import AsyncAITBCHTTPClient

app = FastAPI(title="Simple AITBC Explorer", version="0.1.0")
logger = get_logger(__name__)
BLOCKCHAIN_RPC_URL = "http://localhost:8025"
TX_HASH_PATTERN = re.compile("^[a-fA-F0-9]{64}$")


def validate_tx_hash(tx_hash: str) -> bool:
    """Validate transaction hash to prevent SSRF"""
    if not tx_hash:
        return False
    if any(char in tx_hash for char in ["/", "\\", "..", "\n", "\r", "\t", "?", "&"]):
        return False
    return bool(TX_HASH_PATTERN.match(tx_hash))


HTML_TEMPLATE = '\n<!DOCTYPE html>\n<html lang="en">\n<head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n    <title>Simple AITBC Explorer</title>\n    <script src="https://cdn.tailwindcss.com"></script>\n</head>\n<body class="bg-gray-50">\n    <div class="container mx-auto px-4 py-8">\n        <h1 class="text-3xl font-bold mb-8">AITBC Blockchain Explorer</h1>\n        \n        <!-- Search -->\n        <div class="bg-white rounded-lg shadow p-6 mb-8">\n            <h2 class="text-xl font-semibold mb-4">Search</h2>\n            <div class="flex space-x-4">\n                <input type="text" id="search-input" placeholder="Search by transaction hash (64 chars)" \n                       class="flex-1 px-4 py-2 border rounded-lg">\n                <button onclick="performSearch()" class="bg-blue-600 text-white px-6 py-2 rounded-lg">\n                    Search\n                </button>\n            </div>\n        </div>\n        \n        <!-- Results -->\n        <div id="results" class="hidden bg-white rounded-lg shadow p-6">\n            <h2 class="text-xl font-semibold mb-4">Transaction Details</h2>\n            <div id="tx-details"></div>\n        </div>\n        \n        <!-- Latest Blocks -->\n        <div class="bg-white rounded-lg shadow p-6">\n            <h2 class="text-xl font-semibold mb-4">Latest Blocks</h2>\n            <div id="blocks-list"></div>\n        </div>\n    </div>\n\n    <script>\n        // Problem 1: Frontend calls /api/transactions/{hash} but backend doesn\'t have it\n        async function performSearch() {\n            const query = document.getElementById(\'search-input\').value.trim();\n            if (!query) return;\n            \n            if (/^[a-fA-F0-9]{64}$/.test(query)) {\n                try {\n                    const tx = await fetch(`/api/transactions/${query}`).then(r => {\n                        if (!r.ok) throw new Error(\'Transaction not found\');\n                        return r.json();\n                    });\n                    showTransactionDetails(tx);\n                } catch (error) {\n                    alert(\'Transaction not found\');\n                }\n            } else {\n                alert(\'Please enter a valid 64-character hex transaction hash\');\n            }\n        }\n        \n        // Problem 2: UI expects tx.hash, tx.from, tx.to, tx.amount, tx.fee\n        // But RPC returns tx_hash, sender, recipient, payload, created_at\n        function showTransactionDetails(tx) {\n            const resultsDiv = document.getElementById(\'results\');\n            const detailsDiv = document.getElementById(\'tx-details\');\n            \n            detailsDiv.innerHTML = `\n                <div class="space-y-4">\n                    <div><strong>Hash:</strong> ${tx.hash || \'N/A\'}</div>\n                    <div><strong>From:</strong> ${tx.from || \'N/A\'}</div>\n                    <div><strong>To:</strong> ${tx.to || \'N/A\'}</div>\n                    <div><strong>Amount:</strong> ${tx.amount || \'N/A\'}</div>\n                    <div><strong>Fee:</strong> ${tx.fee || \'N/A\'}</div>\n                    <div><strong>Timestamp:</strong> ${formatTimestamp(tx.timestamp)}</div>\n                </div>\n            `;\n            \n            resultsDiv.classList.remove(\'hidden\');\n        }\n        \n        // Problem 3: formatTimestamp now handles both numeric and ISO string timestamps\n        function formatTimestamp(timestamp) {\n            if (!timestamp) return \'N/A\';\n            \n            // Handle ISO string timestamps\n            if (typeof timestamp === \'string\') {\n                try {\n                    return new Date(timestamp).toLocaleString();\n                } catch (e) {\n                    return \'Invalid timestamp\';\n                }\n            }\n            \n            // Handle numeric timestamps (Unix seconds)\n            if (typeof timestamp === \'number\') {\n                try {\n                    return new Date(timestamp * 1000).toLocaleString();\n                } catch (e) {\n                    return \'Invalid timestamp\';\n                }\n            }\n            \n            return \'Invalid timestamp format\';\n        }\n        \n        // Load latest blocks\n        async function loadBlocks() {\n            try {\n                const head = await fetch(\'/api/chain/head\').then(r => r.json());\n                const blocksList = document.getElementById(\'blocks-list\');\n                \n                let html = \'<div class="space-y-4">\';\n                for (let i = 0; i < 5 && head.height - i >= 0; i++) {\n                    const block = await fetch(`/api/blocks/${head.height - i}`).then(r => r.json());\n                    html += `\n                        <div class="border rounded p-4">\n                            <div><strong>Height:</strong> ${block.height}</div>\n                            <div><strong>Hash:</strong> ${block.hash ? block.hash.substring(0, 16) + \'...\' : \'N/A\'}</div>\n                            <div><strong>Time:</strong> ${formatTimestamp(block.timestamp)}</div>\n                        </div>\n                    `;\n                }\n                html += \'</div>\';\n                blocksList.innerHTML = html;\n            } catch (error) {\n                console.error(\'Failed to load blocks:\', error);\n            }\n        }\n        \n        // Initialize\n        document.addEventListener(\'DOMContentLoaded\', () => {\n            loadBlocks();\n        });\n    </script>\n</body>\n</html>\n'


@app.get("/api/chain/head")
async def get_chain_head() -> dict[str, object]:
    """Get current chain head"""
    try:
        client = AsyncAITBCHTTPClient(base_url=BLOCKCHAIN_RPC_URL, timeout=10)
        response = await client.async_get("/rpc/head")
        if response:
            return response
    except NetworkError as e:
        logger.error("Error getting chain head: %s", e)
    return {"height": 0, "hash": "", "timestamp": None}


@app.get("/api/blocks/{height}")
async def get_block(height: int) -> dict[str, object]:
    """Get block by height"""
    if height < 0 or height > 10000000:
        return {"height": height, "hash": "", "timestamp": None, "transactions": []}
    try:
        client = AsyncAITBCHTTPClient(base_url=BLOCKCHAIN_RPC_URL, timeout=10)
        response = await client.async_get(f"/rpc/blocks/{height}")
        if response:
            return response
    except NetworkError as e:
        logger.error("Error getting block: %s", e)
    return {"height": height, "hash": "", "timestamp": None, "transactions": []}


@app.get("/api/transactions/{tx_hash}")
async def get_transaction(tx_hash: str) -> dict[str, object]:
    """Get transaction by hash - Problem 1: This endpoint was missing"""
    if not validate_tx_hash(tx_hash):
        return {"hash": tx_hash, "from": "unknown", "to": "unknown", "amount": 0, "timestamp": None}
    try:
        client = AsyncAITBCHTTPClient(base_url=BLOCKCHAIN_RPC_URL, timeout=10)
        response = await client.async_get(f"/rpc/tx/{tx_hash}")
        if response:
            return {
                "hash": response.get("tx_hash", tx_hash),
                "from": response.get("sender", "unknown"),
                "to": response.get("recipient", "unknown"),
                "amount": response.get("payload", {}).get("value", "0"),
                "fee": response.get("payload", {}).get("fee", "0"),
                "timestamp": response.get("created_at"),
                "block_height": response.get("block_height", "pending"),
            }
        return {"hash": tx_hash, "from": "unknown", "to": "unknown", "amount": 0, "timestamp": None}
    except NetworkError as e:
        logger.error("Error getting transaction %s: %s", tx_hash, e)
        raise HTTPException(status_code=500, detail=f"Failed to fetch transaction: {str(e)}") from e


@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    """Serve the explorer UI"""
    return HTMLResponse(HTML_TEMPLATE)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8017)
