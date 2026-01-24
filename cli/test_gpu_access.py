#!/usr/bin/env python3
"""
Simple GPU Access Test - Verify miner can access GPU
"""

import subprocess
import sys

def main():
    print("🔍 GPU Access Test for AITBC Miner")
    print("=" * 50)
    
    # Check if nvidia-smi is available
    print("\n1. Checking NVIDIA GPU...")
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            gpu_info = result.stdout.strip()
            print(f"✅ GPU Found: {gpu_info}")
        else:
            print("❌ No NVIDIA GPU detected")
            sys.exit(1)
    except FileNotFoundError:
        print("❌ nvidia-smi not found")
        sys.exit(1)
    
    # Check CUDA with PyTorch
    print("\n2. Checking CUDA with PyTorch...")
    try:
        import torch
        
        if torch.cuda.is_available():
            print(f"✅ CUDA Available: {torch.version.cuda}")
            print(f"   GPU Count: {torch.cuda.device_count()}")
            
            device = torch.device('cuda')
            
            # Test computation
            print("\n3. Testing GPU computation...")
            a = torch.randn(1000, 1000, device=device)
            b = torch.randn(1000, 1000, device=device)
            c = torch.mm(a, b)
            
            print("✅ GPU computation successful")
            
            # Check memory
            memory_allocated = torch.cuda.memory_allocated() / 1024**2
            print(f"   Memory used: {memory_allocated:.2f} MB")
            
        else:
            print("❌ CUDA not available in PyTorch")
            sys.exit(1)
            
    except ImportError:
        print("❌ PyTorch not installed")
        sys.exit(1)
    
    # Check miner service
    print("\n4. Checking miner service...")
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "aitbc-gpu-miner"],
            capture_output=True,
            text=True
        )
        
        if result.stdout.strip() == "active":
            print("✅ Miner service is running")
        else:
            print("⚠️  Miner service is not running")
    except:
        print("⚠️  Could not check miner service")
    
    print("\n✅ GPU access test completed!")
    print("\n💡 Your GPU is ready for mining AITBC!")
    print("   Start mining with: python3 cli/miner.py mine")

if __name__ == "__main__":
    main()
