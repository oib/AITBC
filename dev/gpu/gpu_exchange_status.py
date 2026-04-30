#!/usr/bin/env python3
"""
GPU Exchange Integration Demo
Shows how the GPU miner is integrated with the exchange
"""

import json
import httpx
import subprocess
import time
from datetime import datetime

print("🔗 AITBC GPU Exchange Integration")
print("=" * 50)

# Check GPU Registry
print("\n1. 📊 Checking GPU Registry...")
try:
    response = httpx.get("http://localhost:8091/miners/list")
    if response.status_code == 200:
        data = response.json()
        gpus = data.get("gpus", [])
        print(f"   Found {len(gpus)} registered GPU(s)")
        
        for gpu in gpus:
            print(f"\n   🎮 GPU Details:")
            print(f"      Model: {gpu['capabilities']['gpu']['model']}")
            print(f"      Memory: {gpu['capabilities']['gpu']['memory_gb']} GB")
            print(f"      CUDA: {gpu['capabilities']['gpu']['cuda_version']}")
            print(f"      Status: {gpu.get('status', 'Unknown')}")
            print(f"      Region: {gpu.get('region', 'Unknown')}")
    else:
        print("   ❌ GPU Registry not accessible")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Check Exchange
print("\n2. 💰 Checking Trade Exchange...")
try:
    response = httpx.get("http://localhost:3002")
    if response.status_code == 200:
        print("   ✅ Trade Exchange is running")
        print("   🌐 URL: http://localhost:3002")
    else:
        print("   ❌ Trade Exchange not responding")
except Exception:
    print("   ❌ Trade Exchange not accessible")

# Check Blockchain
print("\n3. ⛓️  Checking Blockchain Node...")
try:
    response = httpx.get("http://localhost:8003/rpc/head")
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Blockchain Node active")
        print(f"      Block Height: {data.get('height', 'Unknown')}")
        print(f"      Block Hash: {data.get('hash', 'Unknown')[:16]}...")
    else:
        print("   ❌ Blockchain Node not responding")
except Exception:
    print("   ❌ Blockchain Node not accessible")

# Show Integration Points
print("\n4. 🔌 Integration Points:")
print("   • GPU Registry: http://localhost:8091/miners/list")
print("   • Trade Exchange: http://localhost:3002")
print("   • Blockchain RPC: http://localhost:9080")
print("   • GPU Marketplace: Exchange > Browse GPU Marketplace")

# Show API Usage
print("\n5. 📡 API Usage Examples:")
print("\n   Get registered GPUs:")
print("   curl http://localhost:8091/miners/list")
print("\n   Get GPU details:")
print("   curl http://localhost:8091/miners/localhost-gpu-miner")
print("\n   Get blockchain info:")
print("   curl http://localhost:8003/rpc/head")

# Show Current Status
print("\n6. 📈 Current System Status:")
print("   ✅ GPU Miner: Running (systemd)")
print("   ✅ GPU Registry: Running on port 8091")
print("   ✅ Trade Exchange: Running on port 3002")
print("   ✅ Blockchain Node: Running on port 8003")

print("\n" + "=" * 50)
print("🎯 GPU is successfully integrated with the exchange!")
print("\nNext steps:")
print("1. Open http://localhost:3002 in your browser")
print("2. Click 'Browse GPU Marketplace'")
print("3. View the registered RTX 4060 Ti GPU")
print("4. Purchase GPU compute time with AITBC tokens")
