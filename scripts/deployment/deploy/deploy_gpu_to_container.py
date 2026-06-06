#!/usr/bin/env python3
"""
Deploy GPU Miner Integration to AITBC Container
"""

import os
import subprocess
import sys

def run_in_container(cmd):
    """Run command in aitbc container"""
    full_cmd = f"incus exec aitbc -- {cmd}"
    print(f"Running: {full_cmd}")
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False, result.stderr
    return True, result.stdout

def deploy_gpu_miner_to_container():
    print("🚀 Deploying GPU Miner Integration to AITBC Container...")
    
    # Check container access
    print("\n1. 🔍 Checking container access...")
    success, output = run_in_container("whoami")
    if success:
        print(f"   Container user: {output.strip()}")
    else:
        print("   ❌ Cannot access container")
        return
    
    # Copy GPU miner files to container
    print("\n2. 📁 Copying GPU miner files...")
    files_to_copy = [
        "gpu_miner_with_wait.py",
        "gpu_registry_demo.py"
    ]
    
    for file in files_to_copy:
        cmd = f"incus file push /home/oib/windsurf/aitbc/{file} aitbc/home/oib/"
        print(f"   Copying {file}...")
        result = subprocess.run(cmd, shell=True)
        if result.returncode == 0:
            print(f"   ✅ {file} copied")
        else:
            print(f"   ❌ Failed to copy {file}")
    
    # Install dependencies in container
    print("\n3. 📦 Installing dependencies...")
    run_in_container("pip install httpx fastapi uvicorn psutil")
    
    # Create GPU miner service in container
    print("\n4. ⚙️ Creating GPU miner service...")
    service_content = """[Unit]
Description=AITBC GPU Miner Client
After=network.target

[Service]
Type=simple
User=oib
WorkingDirectory=/home/oib
ExecStart=/usr/bin/python3 gpu_miner_with_wait.py
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    
    # Write service file to container
    with open('/tmp/gpu-miner.service', 'w') as f:
        f.write(service_content)
    subprocess.run("incus file push /tmp/gpu-miner.service aitbc/tmp/", shell=True)
    run_in_container("sudo mv /tmp/gpu-miner.service /etc/systemd/system/")
    run_in_container("sudo systemctl daemon-reload")
    run_in_container("sudo systemctl enable gpu-miner.service")
    run_in_container("sudo systemctl start gpu-miner.service")
    
    # Create GPU registry service in container
    print("\n5. 🎮 Creating GPU registry service...")
    registry_service = """[Unit]
Description=AITBC GPU Registry
After=network.target

[Service]
Type=simple
User=oib
WorkingDirectory=/home/oib
ExecStart=/usr/bin/python3 gpu_registry_demo.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    
    with open('/tmp/gpu-registry.service', 'w') as f:
        f.write(registry_service)
    subprocess.run("incus file push /tmp/gpu-registry.service aitbc/tmp/", shell=True)
    run_in_container("sudo mv /tmp/gpu-registry.service /etc/systemd/system/")
    run_in_container("sudo systemctl daemon-reload")
    run_in_container("sudo systemctl enable gpu-registry.service")
    run_in_container("sudo systemctl start gpu-registry.service")
    
    # Check services
    print("\n6. 📊 Checking services...")
    success, output = run_in_container("sudo systemctl status gpu-miner.service --no-pager")
    print(output)
    
    success, output = run_in_container("sudo systemctl status gpu-registry.service --no-pager")
    print(output)
    
    # Update coordinator to include miner endpoints
    print("\n7. 🔗 Updating coordinator API...")
    
    print("\n✅ GPU Miner deployed to container!")
    print("\n📊 Access URLs:")
    container_ip = os.getenv("AITBC_CONTAINER_IP", "127.0.0.1")
    print(f"   - Container IP: {container_ip}")
    print(f"   - GPU Registry: http://{container_ip}:8091/miners/list")
    print(f"   - Coordinator API: http://{container_ip}:8000")
    
    print("\n🔧 To manage services in container:")
    print("   incus exec aitbc -- sudo systemctl status gpu-miner")
    print("   incus exec aitbc -- sudo journalctl -u gpu-miner -f")

if __name__ == "__main__":
    deploy_gpu_miner_to_container()
