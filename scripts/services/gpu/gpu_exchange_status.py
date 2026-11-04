#!/usr/bin/env python3
"""
GPU Exchange Integration Demo
Shows how the GPU miner is integrated with the exchange
"""

import httpx

print("🔗 AITBC GPU Exchange Integration")
print("=" * 50)

# #1027: every section records what it actually probed — the summary
# below prints those results, not a hard-coded "everything works".
probes = {}

# Check GPU Registry
print("\n1. 📊 Checking GPU Registry...")
try:
    response = httpx.get("http://localhost:8091/miners/list", timeout=5)
    if response.status_code == 200:
        data = response.json()
        gpus = data.get("gpus", [])
        print(f"   Found {len(gpus)} registered GPU(s)")
        probes["GPU Registry"] = f"up — {len(gpus)} GPU(s) registered"

        for gpu in gpus:
            print("\n   🎮 GPU Details:")
            print(f"      Model: {gpu['capabilities']['gpu']['model']}")
            print(f"      Memory: {gpu['capabilities']['gpu']['memory_gb']} GB")
            print(f"      CUDA: {gpu['capabilities']['gpu']['cuda_version']}")
            print(f"      Status: {gpu.get('status', 'Unknown')}")
            print(f"      Region: {gpu.get('region', 'Unknown')}")
    else:
        print("   ❌ GPU Registry not accessible")
        probes["GPU Registry"] = f"down — HTTP {response.status_code}"
except httpx.RequestError as e:
    print(f"   ❌ Error: {e}")
    probes["GPU Registry"] = f"down — {type(e).__name__}"

# Check Exchange
print("\n2. 💰 Checking Trade Exchange...")
try:
    response = httpx.get("http://localhost:3002", timeout=5)
    if response.status_code == 200:
        print("   ✅ Trade Exchange is running")
        print("   🌐 URL: http://localhost:3002")
        probes["Trade Exchange"] = "up"
    else:
        print("   ❌ Trade Exchange not responding")
        probes["Trade Exchange"] = f"down — HTTP {response.status_code}"
except httpx.RequestError as e:
    print("   ❌ Trade Exchange not accessible")
    probes["Trade Exchange"] = f"down — {type(e).__name__}"

# Check Blockchain
print("\n3. ⛓️  Checking Blockchain Node...")
try:
    response = httpx.get("http://localhost:9080/rpc/head", timeout=5)
    if response.status_code == 200:
        data = response.json()
        print("   ✅ Blockchain Node active")
        print(f"      Block Height: {data.get('height', 'Unknown')}")
        print(f"      Block Hash: {data.get('hash', 'Unknown')[:16]}...")
        probes["Blockchain Node"] = f"up — height {data.get('height', '?')}"
    else:
        print("   ❌ Blockchain Node not responding")
        probes["Blockchain Node"] = f"down — HTTP {response.status_code}"
except (httpx.RequestError, KeyError, ValueError) as e:
    print("   ❌ Blockchain Node not accessible")
    probes["Blockchain Node"] = f"down — {type(e).__name__}"

# Show Integration Points
print("\n4. 🔌 Integration Points:")
print("   • GPU Registry: http://localhost:8091/miners/list")
print("   • Trade Exchange: http://localhost:3002")
print("   • Blockchain RPC: http://localhost:9080")
print("   • GPU Market: Exchange > Browse GPU Market")

# Show API Usage
print("\n5. 📡 API Usage Examples:")
print("\n   Get registered GPUs:")
print("   curl http://localhost:8091/miners/list")
print("\n   Get GPU details:")
print("   curl http://localhost:8091/miners/localhost-gpu-miner")
print("\n   Get blockchain info:")
print("   curl http://localhost:9080/rpc/head")

# Show Current Status — the real probe outcomes, not assumptions (#1027)
print("\n6. 📈 Current System Status:")
for name, result in probes.items():
    mark = "✅" if result.startswith("up") else "❌"
    print(f"   {mark} {name}: {result}")

print("\n" + "=" * 50)
if probes and all(r.startswith("up") for r in probes.values()):
    print("🎯 GPU is successfully integrated with the exchange!")
else:
    print("⚠️  Some probes failed — see the status lines above")
print("\nNext steps:")
print("1. Open http://localhost:3002 in your browser")
print("2. Click 'Browse GPU Market'")
print("3. View the registered RTX 4060 Ti GPU")
print("4. Purchase GPU compute time with the network tokens")
