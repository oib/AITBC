#!/usr/bin/env python3
"""
Local proxy to simulate domain routing for development
"""

import subprocess
import time
import os
import signal
import sys
from pathlib import Path

# Configuration
DOMAIN = "aitbc.bubuit.net"
SERVICES = {
    "api": {"port": 8000, "path": "/v1"},
    "rpc": {"port": 9080, "path": "/rpc"},
    "marketplace": {"port": 3001, "path": "/"},
    "exchange": {"port": 3002, "path": "/"},
}

def start_services():
    """Start all AITBC services"""
    print("🚀 Starting AITBC Services")
    print("=" * 40)
    
    # Change to project directory
    os.chdir("/home/oib/windsurf/aitbc")
    
    processes = {}
    
    # Start Coordinator API
    print("\n1. Starting Coordinator API...")
    api_proc = subprocess.Popen([
        "python", "-m", "uvicorn", 
        "src.app.main:app",
        "--host", "127.0.0.1",
        "--port", "8000"
    ], cwd="apps/coordinator-api")
    processes["api"] = api_proc
    print(f"   PID: {api_proc.pid}")
    
    # Start Blockchain Node (if not running)
    print("\n2. Checking Blockchain Node...")
    result = subprocess.run(["lsof", "-i", ":9080"], capture_output=True)
    if not result.stdout:
        print("   Starting Blockchain Node...")
        node_proc = subprocess.Popen([
            "python", "-m", "uvicorn",
            "aitbc_chain.app:app",
            "--host", "127.0.0.1",
            "--port", "9080"
        ], cwd="apps/blockchain-node")
        processes["blockchain"] = node_proc
        print(f"   PID: {node_proc.pid}")
    else:
        print("   ✅ Already running")
    
    # Start Marketplace UI
    print("\n3. Starting Marketplace UI...")
    market_proc = subprocess.Popen([
        "python", "server.py",
        "--port", "3001"
    ], cwd="apps/marketplace-ui")
    processes["marketplace"] = market_proc
    print(f"   PID: {market_proc.pid}")
    
    # Start Trade Exchange
    print("\n4. Starting Trade Exchange...")
    exchange_proc = subprocess.Popen([
        "python", "server.py",
        "--port", "3002"
    ], cwd="apps/trade-exchange")
    processes["exchange"] = exchange_proc
    print(f"   PID: {exchange_proc.pid}")
    
    # Wait for services to start
    print("\n⏳ Waiting for services to start...")
    time.sleep(5)
    
    # Test endpoints
    print("\n🧪 Testing Services:")
    test_endpoints()
    
    print("\n✅ All services started!")
    print("\n📋 Local URLs:")
    print(f"   API: http://127.0.0.1:8000/v1")
    print(f"   RPC: http://127.0.0.1:9080/rpc")
    print(f"   Marketplace: http://127.0.0.1:3001")
    print(f"   Exchange: http://127.0.0.1:3002")
    
    print("\n🌐 Domain URLs (when proxied):")
    print(f"   API: https://{DOMAIN}/api")
    print(f"   RPC: https://{DOMAIN}/rpc")
    print(f"   Marketplace: https://{DOMAIN}/Marketplace")
    print(f"   Exchange: https://{DOMAIN}/Exchange")
    print(f"   Admin: https://{DOMAIN}/admin")
    
    print("\n🛑 Press Ctrl+C to stop all services")
    
    try:
        # Keep running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping services...")
        for name, proc in processes.items():
            print(f"   Stopping {name}...")
            proc.terminate()
            proc.wait()
        print("✅ All services stopped!")

def test_endpoints():
    """Test if services are responding"""
    import requests
    
    endpoints = [
        ("API Health", "http://127.0.0.1:8000/v1/health"),
        ("Admin Stats", "http://127.0.0.1:8000/v1/admin/stats"),
        ("Marketplace", "http://127.0.0.1:3001"),
        ("Exchange", "http://127.0.0.1:3002"),
    ]
    
    for name, url in endpoints:
        try:
            if "admin" in url:
                response = requests.get(url, headers={"X-Api-Key": "${ADMIN_API_KEY}"}, timeout=2)
            else:
                response = requests.get(url, timeout=2)
            print(f"   {name}: ✅ {response.status_code}")
        except Exception as e:
            print(f"   {name}: ❌ {str(e)[:50]}")

if __name__ == "__main__":
    start_services()
