#!/usr/bin/env python3
"""
Test the AITBC Ollama Plugin
"""

import asyncio
import subprocess
import time
from client_plugin import OllamaClient

def test_ollama_service():
    """Test Ollama service directly"""
    print("🔍 Testing Ollama Service...")
    
    # Test Ollama is running
    result = subprocess.run(
        ["curl", "-s", "http://localhost:11434/api/tags"],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        import json
        data = json.loads(result.stdout)
        print(f"✅ Ollama is running with {len(data['models'])} models")
        return True
    else:
        print("❌ Ollama is not running")
        return False

def test_plugin_service():
    """Test the plugin service"""
    print("\n🔌 Testing Plugin Service...")
    
    from service import handle_request
    
    async def test():
        # Test list models
        result = await handle_request({"action": "list_models"})
        if result["success"]:
            print(f"✅ Plugin found {len(result['models'])} models")
        else:
            print(f"❌ Failed to list models: {result}")
            return False
        
        # Test generation
        result = await handle_request({
            "action": "generate",
            "model": "llama3.2:latest",
            "prompt": "What is AITBC in one sentence?",
            "max_tokens": 50
        })
        
        if result["success"]:
            print(f"✅ Generated text:")
            print(f"   {result['text'][:100]}...")
            print(f"   Cost: {result['cost']} AITBC")
        else:
            print(f"❌ Generation failed: {result}")
            return False
        
        return True
    
    return asyncio.run(test())

def test_client_miner_flow():
    """Test client submits job, miner processes it"""
    print("\n🔄 Testing Client-Miner Flow...")
    
    # Create client
    client = OllamaClient("http://localhost:8001", "${CLIENT_API_KEY}")
    
    # Submit a job
    print("1. Submitting inference job...")
    job_id = client.submit_generation(
        model="llama3.2:latest",
        prompt="Explain blockchain in simple terms",
        max_tokens=100
    )
    
    if not job_id:
        print("❌ Failed to submit job")
        return False
    
    print(f"✅ Job submitted: {job_id}")
    
    # Start miner in background (simplified)
    print("\n2. Starting Ollama miner...")
    miner_cmd = [
        "python3", "miner_plugin.py",
        "http://localhost:8001",
        "${MINER_API_KEY}",
        "ollama-miner-test"
    ]
    
    miner_process = subprocess.Popen(
        miner_cmd,
        cwd="/home/oib/windsurf/aitbc/plugins/ollama",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait a bit for miner to process
    time.sleep(10)
    
    # Check job status
    print("\n3. Checking job status...")
    status = client.get_job_status(job_id)
    
    if status:
        print(f"   State: {status['state']}")
        print(f"   Miner: {status.get('assigned_miner_id', 'None')}")
        
        if status['state'] == 'completed':
            print(f"✅ Job completed!")
            result = status.get('result', {})
            print(f"   Output: {result.get('output', '')[:200]}...")
            print(f"   Cost: {result.get('cost', 0)} AITBC")
        
    # Stop miner
    miner_process.terminate()
    miner_process.wait()
    
    return True

def main():
    print("🚀 AITBC Ollama Plugin Test Suite")
    print("=" * 60)
    
    # Test 1: Ollama service
    if not test_ollama_service():
        print("\n❌ Please start Ollama first: ollama serve")
        return
    
    # Test 2: Plugin service
    if not test_plugin_service():
        print("\n❌ Plugin service test failed")
        return
    
    # Test 3: Client-miner flow
    if not test_client_miner_flow():
        print("\n❌ Client-miner flow test failed")
        return
    
    print("\n✅ All tests passed!")
    print("\n💡 To use the Ollama plugin:")
    print("   1. Start mining: python3 plugins/ollama/miner_plugin.py")
    print("   2. Submit jobs: python3 plugins/ollama/client_plugin.py generate llama3.2:latest 'Your prompt'")
    print("   3. Check earnings: cd home/miner && python3 wallet.py balance")

if __name__ == "__main__":
    main()
