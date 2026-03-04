from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
import json
import socket
from datetime import datetime

app = FastAPI(title="CLI Mock Server", version="1.0.0")

@app.get("/health")
async def mock_health():
    return {
        "status": "healthy",
        "service": "coordinator-api",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/v1/health")
async def mock_v1_health():
    return {
        "status": "ok",
        "env": "development",
        "python_version": "3.13.5"
    }

@app.get("/v1/marketplace/gpu/list")
async def mock_marketplace_gpus():
    return [
        {
            "id": "gpu-001",
            "model": "NVIDIA-RTX-4060Ti",
            "memory": "16GB",
            "price_per_hour": 0.001,
            "available": True,
            "miner_id": "test-miner-001"
        },
        {
            "id": "gpu-002", 
            "model": "NVIDIA-RTX-3080",
            "memory": "10GB",
            "price_per_hour": 0.002,
            "available": False,
            "miner_id": "test-miner-002"
        }
    ]

@app.get("/v1/marketplace/offers")
async def mock_marketplace_offers():
    return [
        {
            "id": "offer-001",
            "gpu_id": "gpu-001",
            "price": 0.001,
            "miner_id": "test-miner-001",
            "status": "active"
        }
    ]

@app.get("/v1/agents/workflows")
async def mock_agent_workflows():
    return [
        {
            "id": "workflow-001",
            "name": "test-workflow",
            "status": "running",
            "created_at": datetime.now().isoformat()
        }
    ]

@app.get("/v1/blockchain/status")
async def mock_blockchain_status():
    return {
        "status": "connected",
        "height": 12345,
        "hash": "0x1234567890abcdef",
        "timestamp": datetime.now().isoformat(),
        "tx_count": 678
    }

def find_available_port(start_port=8020, max_port=8050):
    for port in range(start_port, max_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return None

if __name__ == "__main__":
    port = find_available_port()
    if port:
        print(f"Starting CLI Mock Server on port {port}...")
        
        # Write config for CLI to use
        config_path = "/home/oib/windsurf/aitbc/cli-dev/cli-staging-config-dynamic.yaml"
        with open(config_path, "w") as f:
            f.write(f"""coordinator_url: http://127.0.0.1:{port}
api_key: null
output_format: table
config_file: {config_path}
test_mode: true
timeout: 30
debug: true
staging: true
""")
        print(f"Created config file for this port at {config_path}")
        
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    else:
        print("Error: Could not find an available port in range 8020-8050")
