#!/usr/bin/env python3
"""
Test script for host GPU miner
"""

import subprocess
import httpx

# Test GPU
print("Testing GPU access...")
result = subprocess.run(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader,nounits'], 
                       capture_output=True, text=True)
if result.returncode == 0:
    print(f"✅ GPU detected: {result.stdout.strip()}")
else:
    print("❌ GPU not accessible")

# Test Ollama
print("\nTesting Ollama...")
try:
    response = httpx.get("http://localhost:11434/api/tags", timeout=5)
    if response.status_code == 200:
        models = response.json().get('models', [])
        print(f"✅ Ollama running with {len(models)} models")
        for m in models[:3]:  # Show first 3 models
            print(f"   - {m['name']}")
    else:
        print("❌ Ollama not responding")
except Exception as e:
    print(f"❌ Ollama error: {e}")

# Test Coordinator
print("\nTesting Coordinator...")
try:
    response = httpx.get("http://127.0.0.1:8000/v1/health", timeout=5)
    if response.status_code == 200:
        print("✅ Coordinator is accessible")
    else:
        print("❌ Coordinator not responding")
except Exception as e:
    print(f"❌ Coordinator error: {e}")

# Test Ollama inference
print("\nTesting Ollama inference...")
try:
    response = httpx.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "llama3.2:latest",
            "prompt": "Say hello",
            "stream": False
        },
        timeout=10
    )
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Inference successful: {result.get('response', '')[:50]}...")
    else:
        print("❌ Inference failed")
except Exception as e:
    print(f"❌ Inference error: {e}")

print("\n✅ All tests completed!")
