#!/usr/bin/env python3
"""
AITBC Agent Live API
Real-time dynamic endpoints that query blockchain RPC and serve fresh data
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

# Try to import fastapi, fallback to flask
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    try:
        from flask import Flask, jsonify, abort
        HAS_FLASK = True
    except ImportError:
        print("Error: Neither FastAPI nor Flask installed")
        sys.exit(1)

import urllib.request
import urllib.error
import ssl

# Configuration
RPC_URL = os.getenv("AITBC_RPC_URL", "http://localhost:8006/rpc")
NODE_ID = os.getenv("NODE_ID", "aitbc")
ISLAND_ID = os.getenv("ISLAND_ID", "ait-mainnet-island")
CHAIN_ID = os.getenv("CHAIN_ID", "ait-mainnet")
NODE_ROLE = os.getenv("NODE_ROLE", "hub")

# SSL context that doesn't verify certs (for local dev)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


def rpc_query(method: str, params: Optional[list] = None) -> Optional[Dict]:
    """Query the blockchain RPC endpoint"""
    try:
        url = f"{RPC_URL}/{method}"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=5, context=ssl_context) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"RPC query failed: {e}", file=sys.stderr)
        return None


def get_live_island_data() -> Dict[str, Any]:
    """Get real-time island data from RPC"""
    # Query chain head for current block info
    head = rpc_query("head")
    info = rpc_query("info")
    islands_rpc = rpc_query("islands")
    
    # Get peer count from island manager if available
    peer_count = 0
    if islands_rpc and isinstance(islands_rpc, dict) and "islands" in islands_rpc:
        for island in islands_rpc["islands"]:
            if island.get("island_id") == ISLAND_ID:
                peer_count = island.get("peer_count", 0)
                break
    
    block_height = head.get("height", 0) if head else 0
    block_hash = head.get("hash", "unknown") if head else "unknown"
    timestamp = head.get("timestamp", datetime.now(timezone.utc).isoformat()) if head else datetime.now(timezone.utc).isoformat()
    
    return {
        "islands": [
            {
                "island_id": ISLAND_ID,
                "island_name": "AIT Mainnet" if CHAIN_ID == "ait-mainnet" else "AIT Testnet",
                "chain_id": CHAIN_ID,
                "status": "active",
                "role": NODE_ROLE,
                "chain_info": {
                    "block_time": 5,
                    "consensus": "proof_of_authority",
                    "network_id": 1337,
                    "current_height": block_height,
                    "current_hash": block_hash,
                    "last_update": timestamp
                },
                "endpoints": {
                    "rpc": [
                        {"url": f"http://{NODE_ID}:8006", "node_id": NODE_ID, "role": NODE_ROLE},
                        {"url": f"http://{'aitbc1' if NODE_ID == 'aitbc' else 'aitbc'}:8006", 
                         "node_id": 'aitbc1' if NODE_ID == 'aitbc' else 'aitbc', 
                         "role": "follower" if NODE_ROLE == "hub" else "hub"}
                    ],
                    "p2p": [
                        {"address": f"{NODE_ID}:7070", "node_id": NODE_ID},
                        {"address": f"{'aitbc1' if NODE_ID == 'aitbc' else 'aitbc'}:7070", 
                         "node_id": 'aitbc1' if NODE_ID == 'aitbc' else 'aitbc'}
                    ]
                },
                "stats": {
                    "peer_count": peer_count,
                    "block_height": block_height,
                    "last_block_hash": block_hash,
                    "last_block_time": timestamp
                },
                "this_node": {
                    "node_id": NODE_ID,
                    "role": NODE_ROLE,
                    "is_hub": NODE_ROLE == "hub",
                    "block_production_chains": [CHAIN_ID] if NODE_ROLE == "hub" else [],
                    "enable_block_production": NODE_ROLE == "hub"
                }
            }
        ],
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "format_version": "1.0",
            "total_islands": 1,
            "active_islands": 1,
            "data_source": "live_rpc",
            "note": "This endpoint shows real-time data from the blockchain RPC"
        }
    }


def get_live_chain_data() -> Dict[str, Any]:
    """Get real-time chain data from RPC"""
    head = rpc_query("head")
    info = rpc_query("info")
    
    block_height = head.get("height", 0) if head else 0
    block_hash = head.get("hash", "unknown") if head else "unknown"
    timestamp = head.get("timestamp", datetime.now(timezone.utc).isoformat()) if head else datetime.now(timezone.utc).isoformat()
    tx_count = head.get("tx_count", 0) if head else 0
    
    return {
        "chains": [
            {
                "chain_id": CHAIN_ID,
                "name": "AIT Mainnet" if CHAIN_ID == "ait-mainnet" else "AIT Testnet",
                "island_id": ISLAND_ID,
                "type": "production" if CHAIN_ID == "ait-mainnet" else "test",
                "status": "active",
                "live_stats": {
                    "current_height": block_height,
                    "current_hash": block_hash,
                    "last_block_time": timestamp,
                    "tx_count_last_block": tx_count,
                    "queried_at": datetime.now(timezone.utc).isoformat()
                },
                "config": {
                    "block_time": info.get("block_time", 5) if info else 5,
                    "consensus": "proof_of_authority",
                    "network_id": info.get("network_id", 1337) if info else 1337
                },
                "endpoints": {
                    "rpc": [
                        f"http://{NODE_ID}:8006/rpc",
                        f"http://{'aitbc1' if NODE_ID == 'aitbc' else 'aitbc'}:8006/rpc"
                    ],
                    "head": "/rpc/head",
                    "info": "/rpc/info",
                    "supply": "/rpc/supply"
                },
                "join": {
                    "guide": f"/agent/join/{CHAIN_ID}.json"
                }
            }
        ],
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "format_version": "1.0",
            "total_chains": 1,
            "active_chains": 1,
            "data_source": "live_rpc"
        }
    }


def get_join_instructions(chain_id: str) -> Dict[str, Any]:
    """Get dynamic join instructions for a specific chain"""
    # Validate chain_id matches this node's chain
    if chain_id != CHAIN_ID:
        return {"error": "Chain not supported by this node", "supported_chain": CHAIN_ID}
    
    # Get current network info
    head = rpc_query("head")
    info = rpc_query("info")
    islands_rpc = rpc_query("islands")
    
    block_height = head.get("height", 0) if head else 0
    network_id = info.get("network_id", 1337) if info else 1337
    block_time = info.get("block_time", 5) if info else 5
    
    # Get peer addresses from islands RPC
    p2p_peers = [f"{NODE_ID}:7070"]
    if islands_rpc and isinstance(islands_rpc, dict) and "islands" in islands_rpc:
        for island in islands_rpc["islands"]:
            if island.get("island_id") == ISLAND_ID:
                endpoints = island.get("endpoints", {})
                p2p_list = endpoints.get("p2p", [])
                p2p_peers = [peer.get("address", peer) for peer in p2p_list]
                break
    
    return {
        "chain_id": CHAIN_ID,
        "island_id": ISLAND_ID,
        "chain_name": "AIT Mainnet" if CHAIN_ID == "ait-mainnet" else "AIT Testnet",
        "chain_type": "production" if CHAIN_ID == "ait-mainnet" else "test",
        "current_height": block_height,
        "environment_variables": {
            "NODE_ID": "your-node-id",
            "ISLAND_ID": ISLAND_ID,
            "CHAIN_ID": CHAIN_ID,
            "NODE_ROLE": "follower",
            "AITBC_RPC_URL": f"http://{NODE_ID}:8006/rpc",
            "P2P_BIND_PORT": "7070",
            "ENABLE_BLOCK_PRODUCTION": "false"
        },
        "config_files": {
            "/etc/aitbc/.env": f"AITBC_RPC_URL=http://{NODE_ID}:8006/rpc\nENABLE_BLOCK_PRODUCTION=false\n",
            "/etc/aitbc/node.env": f"NODE_ID=your-node-id\nISLAND_ID={ISLAND_ID}\nCHAIN_ID={CHAIN_ID}\nNODE_ROLE=follower\nP2P_BIND_PORT=7070\n"
        },
        "p2p_configuration": {
            "peers": p2p_peers,
            "bootstrap_nodes": [f"{NODE_ID}:7070"],
            "bind_port": 7070,
            "external_address": "your-node-ip:7070"
        },
        "rpc_configuration": {
            "endpoints": [
                f"http://{NODE_ID}:8006/rpc",
                f"http://{'aitbc1' if NODE_ID == 'aitbc' else 'aitbc'}:8006/rpc"
            ],
            "network_id": network_id,
            "block_time": block_time,
            "consensus": "proof_of_authority"
        },
        "setup_steps": [
            "1. Clone the AITBC repository: git clone https://gitea.bubuit.net/oib/aitbc.git /opt/aitbc",
            "2. Run the setup script: sudo /opt/aitbc/scripts/deployment/setup.sh",
            "3. Configure environment variables in /etc/aitbc/.env and /etc/aitbc/node.env",
            "4. Start the blockchain node: sudo systemctl start aitbc-blockchain-node",
            "5. Verify connection: curl http://localhost:8006/rpc/head"
        ],
        "documentation": "/docs/deployment/SETUP.md",
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": NODE_ID,
            "data_source": "live_rpc",
            "note": "Replace 'your-node-id' and 'your-node-ip' with your actual node configuration"
        }
    }


def get_live_discovery() -> Dict[str, Any]:
    """Get live discovery data"""
    head = rpc_query("head")
    
    block_height = head.get("height", 0) if head else 0
    # Determine health based on RPC responsiveness
    node_health = "healthy" if head else "unhealthy"
    
    return {
        "network": {
            "name": "AITBC",
            "version": "1.0.0",
            "description": "AI-powered blockchain platform",
            "live_status": {
                "current_height": block_height,
                "node_health": node_health,
                "last_update": datetime.now(timezone.utc).isoformat()
            },
            "apis": {
                "rpc": {
                    "url": f"http://{NODE_ID}:8006/rpc",
                    "documentation": "/agent/openapi.json"
                },
                "agent": {
                    "discovery": "/agent/discovery.json",
                    "islands": "/agent/islands.json",
                    "chains": "/agent/chains.json",
                    "health": "/agent/health",
                    "join": f"/agent/join/{CHAIN_ID}.json"
                }
            },
            "islands": [
                {
                    "island_id": ISLAND_ID,
                    "name": "AIT Mainnet" if CHAIN_ID == "ait-mainnet" else "AIT Testnet",
                    "chain_id": CHAIN_ID,
                    "current_height": block_height,
                    "status": "active",
                    "join_guide": f"/agent/join/{CHAIN_ID}.json",
                    "note": f"This node ({NODE_ID}) is the HUB for this island"
                }
            ]
        },
        "this_node": {
            "node_id": NODE_ID,
            "role": NODE_ROLE,
            "is_hub": NODE_ROLE == "hub",
            "block_production": NODE_ROLE == "hub",
            "chains": [CHAIN_ID] if NODE_ROLE == "hub" else [],
            "island_memberships": [ISLAND_ID],
            "live_data": True
        },
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "format_version": "1.1",
            "data_source": "live_rpc"
        }
    }


# Create app based on available framework
if HAS_FASTAPI:
    app = FastAPI(title="AITBC Agent Live API")
    
    @app.get("/agent/islands.json")
    async def live_islands():
        return JSONResponse(content=get_live_island_data())
    
    @app.get("/agent/chains.json")
    async def live_chains():
        return JSONResponse(content=get_live_chain_data())
    
    @app.get("/agent/discovery.json")
    async def live_discovery():
        return JSONResponse(content=get_live_discovery())
    
    @app.get("/agent/health")
    async def live_health():
        head = rpc_query("head")
        return JSONResponse(content={
            "status": "healthy" if head else "unhealthy",
            "node_id": NODE_ID,
            "chain_id": CHAIN_ID,
            "current_height": head.get("height", 0) if head else 0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    @app.get("/agent/join/{chain_id}.json")
    async def join_instructions(chain_id: str):
        instructions = get_join_instructions(chain_id)
        if "error" in instructions:
            raise HTTPException(status_code=404, detail=instructions["error"])
        return JSONResponse(content=instructions)

elif HAS_FLASK:
    app = Flask(__name__)
    
    @app.route("/agent/islands.json")
    def live_islands():
        return jsonify(get_live_island_data())
    
    @app.route("/agent/chains.json")
    def live_chains():
        return jsonify(get_live_chain_data())
    
    @app.route("/agent/discovery.json")
    def live_discovery():
        return jsonify(get_live_discovery())
    
    @app.route("/agent/health")
    def live_health():
        head = rpc_query("head")
        return jsonify({
            "status": "healthy" if head else "unhealthy",
            "node_id": NODE_ID,
            "chain_id": CHAIN_ID,
            "current_height": head.get("height", 0) if head else 0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    @app.route("/agent/join/<chain_id>.json")
    def join_instructions(chain_id):
        instructions = get_join_instructions(chain_id)
        if "error" in instructions:
            abort(404, description=instructions["error"])
        return jsonify(instructions)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    
    print(f"Starting AITBC Agent Live API on {args.host}:{args.port}")
    print(f"RPC URL: {RPC_URL}")
    print(f"Node: {NODE_ID} | Chain: {CHAIN_ID} | Role: {NODE_ROLE}")
    
    if HAS_FASTAPI:
        uvicorn.run(app, host=args.host, port=args.port)
    elif HAS_FLASK:
        app.run(host=args.host, port=args.port)
