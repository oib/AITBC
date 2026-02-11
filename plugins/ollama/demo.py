#!/usr/bin/env python3
"""
Demo of Ollama Plugin - Complete workflow
"""

import subprocess
import time
import asyncio
from client_plugin import OllamaClient

def main():
    print("🚀 AITBC Ollama Plugin Demo")
    print("=" * 60)
    
    # Check Ollama is running
    print("\n1. Checking Ollama...")
    result = subprocess.run(
        ["curl", "-s", "http://localhost:11434/api/tags"],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print("❌ Ollama is not running!")
        print("   Start with: ollama serve")
        return
    
    import json
    models = json.loads(result.stdout)["models"]
    print(f"✅ Ollama running with {len(models)} models")
    
    # Create client
    client = OllamaClient("http://localhost:8001", "${CLIENT_API_KEY}")
    
    # Submit a few different jobs
    jobs = []
    
    print("\n2. Submitting jobs...")
    
    # Job 1: Text generation
    job1 = client.submit_generation(
        model="llama3.2:latest",
        prompt="What is blockchain technology?",
        max_tokens=100
    )
    if job1:
        jobs.append(("Text Generation", job1))
        print(f"✅ Submitted: {job1}")
    
    # Job 2: Code generation
    job2 = client.submit_code_generation(
        model="qwen2.5-coder:14b",
        prompt="Create a function to calculate factorial",
        language="python"
    )
    if job2:
        jobs.append(("Code Generation", job2))
        print(f"✅ Submitted: {job2}")
    
    # Job 3: Translation
    job3 = client.submit_generation(
        model="lauchacarro/qwen2.5-translator:latest",
        prompt="Translate to French: Hello, how are you today?",
        max_tokens=50
    )
    if job3:
        jobs.append(("Translation", job3))
        print(f"✅ Submitted: {job3}")
    
    print(f"\n3. Submitted {len(jobs)} jobs to the network")
    print("\n💡 To process these jobs:")
    print("   1. Start the miner: python3 miner_plugin.py")
    print("   2. The miner will automatically pick up and process jobs")
    print("   3. Check results: python3 client_plugin.py status <job_id>")
    print("   4. Track earnings: cd home/miner && python3 wallet.py balance")
    
    # Show job IDs
    print("\n📋 Submitted Jobs:")
    for job_type, job_id in jobs:
        print(f"   • {job_type}: {job_id}")
    
    # Check initial status
    print("\n4. Checking initial job status...")
    for job_type, job_id in jobs:
        status = client.get_job_status(job_id)
        if status:
            print(f"   {job_id}: {status['state']}")
    
    print("\n✅ Demo complete! Start mining to process these jobs.")

if __name__ == "__main__":
    main()
