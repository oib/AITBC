#!/usr/bin/env python3
"""
GPU Access Test - Check if miner can access local GPU resources
"""

import argparse
import subprocess
import json
import time
import psutil

def check_nvidia_gpu():
    """Check NVIDIA GPU availability"""
    print("🔍 Checking NVIDIA GPU...")
    
    try:
        # Check nvidia-smi
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,utilization.gpu", 
             "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            print(f"✅ NVIDIA GPU(s) Found: {len(lines)}")
            
            for i, line in enumerate(lines, 1):
                parts = line.split(', ')
                if len(parts) >= 4:
                    name = parts[0]
                    total_mem = parts[1]
                    free_mem = parts[2]
                    util = parts[3]
                    print(f"\n   GPU {i}:")
                    print(f"   📦 Model: {name}")
                    print(f"   💾 Memory: {free_mem}/{total_mem} MB free")
                    print(f"   ⚡ Utilization: {util}%")
            
            return True
        else:
            print("❌ nvidia-smi command failed")
            return False
            
    except FileNotFoundError:
        print("❌ nvidia-smi not found - NVIDIA drivers not installed")
        return False

def check_cuda():
    """Check CUDA availability"""
    print("\n🔍 Checking CUDA...")
    
    try:
        # Try to import pynvml
        import pynvml
        pynvml.nvmlInit()
        
        device_count = pynvml.nvmlDeviceGetCount()
        print(f"✅ CUDA Available - {device_count} device(s)")
        
        for i in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle).decode('utf-8')
            memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            
            print(f"\n   CUDA Device {i}:")
            print(f"   📦 Name: {name}")
            print(f"   💾 Memory: {memory_info.free // 1024**2}/{memory_info.total // 1024**2} MB free")
        
        return True
        
    except ImportError:
        print("⚠️  pynvml not installed - install with: pip install pynvml")
        return False
    except Exception as e:
        print(f"❌ CUDA error: {e}")
        return False

def check_pytorch():
    """Check PyTorch CUDA support"""
    print("\n🔍 Checking PyTorch CUDA...")
    
    try:
        import torch
        
        print(f"✅ PyTorch Installed: {torch.__version__}")
        print(f"   CUDA Available: {torch.cuda.is_available()}")
        
        if torch.cuda.is_available():
            print(f"   CUDA Version: {torch.version.cuda}")
            print(f"   GPU Count: {torch.cuda.device_count()}")
            
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                print(f"\n   PyTorch GPU {i}:")
                print(f"   📦 Name: {props.name}")
                print(f"   💾 Memory: {props.total_memory // 1024**2} MB")
                print(f"   Compute: {props.major}.{props.minor}")
        
        return torch.cuda.is_available()
        
    except ImportError:
        print("❌ PyTorch not installed - install with: pip install torch")
        return False

def run_gpu_stress_test(duration=10):
    """Run a quick GPU stress test"""
    print(f"\n🔥 Running GPU Stress Test ({duration}s)...")
    
    try:
        import torch
        
        if not torch.cuda.is_available():
            print("❌ CUDA not available for stress test")
            return False
        
        device = torch.device('cuda')
        
        # Create tensors and perform matrix multiplication
        print("   ⚡ Performing matrix multiplications...")
        start_time = time.time()
        
        while time.time() - start_time < duration:
            # Create large matrices
            a = torch.randn(1000, 1000, device=device)
            b = torch.randn(1000, 1000, device=device)
            
            # Multiply them
            c = torch.mm(a, b)
            
            # Sync to ensure computation completes
            torch.cuda.synchronize()
        
        print("✅ Stress test completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Stress test failed: {e}")
        return False

def check_system_resources():
    """Check system resources"""
    print("\n💻 System Resources:")
    
    # CPU
    cpu_percent = psutil.cpu_percent(interval=1)
    print(f"   🖥️  CPU Usage: {cpu_percent}%")
    print(f"   🧠 CPU Cores: {psutil.cpu_count()} logical, {psutil.cpu_count(logical=False)} physical")
    
    # Memory
    memory = psutil.virtual_memory()
    print(f"   💾 RAM: {memory.used // 1024**2}/{memory.total // 1024**2} MB used ({memory.percent}%)")
    
    # Disk
    disk = psutil.disk_usage('/')
    print(f"   💿 Disk: {disk.used // 1024**3}/{disk.total // 1024**3} GB used")

def main():
    parser = argparse.ArgumentParser(description="GPU Access Test for AITBC Miner")
    parser.add_argument("--stress", type=int, default=0, help="Run stress test for N seconds")
    parser.add_argument("--all", action="store_true", help="Run all tests including stress")
    
    args = parser.parse_args()
    
    print("🚀 AITBC GPU Access Test")
    print("=" * 60)
    
    # Check system resources
    check_system_resources()
    
    # Check GPU availability
    has_nvidia = check_nvidia_gpu()
    has_cuda = check_cuda()
    has_pytorch = check_pytorch()
    
    # Summary
    print("\n📊 SUMMARY")
    print("=" * 60)
    
    if has_nvidia or has_cuda or has_pytorch:
        print("✅ GPU is available for mining!")
        
        if args.stress > 0 or args.all:
            run_gpu_stress_test(args.stress if args.stress > 0 else 10)
        
        print("\n💡 Miner can run GPU-intensive tasks:")
        print("   • Model inference (LLaMA, Stable Diffusion)")
        print("   • Training jobs")
        print("   • Batch processing")
        
    else:
        print("❌ No GPU available - miner will run in CPU-only mode")
        print("\n💡 To enable GPU mining:")
        print("   1. Install NVIDIA drivers")
        print("   2. Install CUDA toolkit")
        print("   3. Install PyTorch with CUDA: pip install torch")
    
    # Check if miner service is running
    print("\n🔍 Checking miner service...")
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
            print("   Start with: sudo systemctl start aitbc-gpu-miner")
    except:
        print("⚠️  Could not check miner service status")

if __name__ == "__main__":
    main()
