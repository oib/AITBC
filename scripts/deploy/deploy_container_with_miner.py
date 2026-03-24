#!/usr/bin/env python3
"""
Deploy AITBC services to incus container with GPU miner integration
"""

import subprocess
import time
import sys

def run_command(cmd, container=None):
    """Run command locally or in container"""
    if container:
        cmd = f"incus exec {container} -- {cmd}"
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False
    return True

def deploy_to_container():
    container = "aitbc"
    container_ip = "10.1.223.93"
    
    print("🚀 Deploying AITBC services to container with GPU miner...")
    
    # Check if container exists
    result = subprocess.run("incus list -c n", shell=True, capture_output=True, text=True)
    if container not in result.stdout:
        print(f"\n📦 Creating container {container}...")
        subprocess.run(f"incus launch images:ubuntu/22.04 {container}", shell=True)
        time.sleep(10)
    
    # Ensure container is running
    subprocess.run(f"incus start {container}", shell=True)
    time.sleep(5)
    
    # Update and install packages in container
    print("\n📦 Installing packages in container...")
    run_command("apt-get update", container)
    run_command("apt-get install -y python3 python3-pip python3-venv curl", container)
    
    # Stop local services
    print("\n📋 Stopping local services...")
    subprocess.run("sudo fuser -k 8000/tcp 2>/dev/null || true", shell=True)
    subprocess.run("sudo fuser -k 9080/tcp 2>/dev/null || true", shell=True)
    subprocess.run("pkill -f 'marketplace-ui' 2>/dev/null || true", shell=True)
    subprocess.run("pkill -f 'trade-exchange' 2>/dev/null || true", shell=True)
    
    # Copy project to container
    print("\n📁 Copying project to container...")
    subprocess.run(f"incus file push -r /home/oib/windsurf/aitbc {container}/home/oib/", shell=True)
    
    # Setup Python environment in container
    print("\n🐍 Setting up Python environment...")
    run_command("cd /home/oib/aitbc && python3 -m venv .venv", container)
    run_command("cd /home/oib/aitbc && source .venv/bin/activate && pip install fastapi uvicorn httpx sqlmodel psutil", container)
    
    # Install dependencies
    print("\n📦 Installing dependencies...")
    run_command("cd /home/oib/aitbc/apps/coordinator-api && source ../../.venv/bin/activate && pip install -e .", container)
    run_command("cd /home/oib/aitbc/apps/blockchain-node && source ../../.venv/bin/activate && pip install -e .", container)
    
    # Create startup script with GPU miner
    print("\n🔧 Creating startup script with GPU miner...")
    startup_script = """#!/bin/bash
cd /home/oib/aitbc
source .venv/bin/activate

# Start coordinator API
echo "Starting Coordinator API..."
cd apps/coordinator-api
source ../../.venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
COORD_PID=$!

# Start blockchain node
echo "Starting Blockchain Node..."
cd ../../apps/blockchain-node
source ../../.venv/bin/activate
python -m uvicorn aitbc_chain.app:app --host 0.0.0.0 --port 9080 &
BLOCK_PID=$!

# Start trade exchange
echo "Starting Trade Exchange..."
cd ../../apps/trade-exchange
source ../../.venv/bin/activate
python simple_exchange_api.py &
EXCHANGE_PID=$!

# Start GPU registry
echo "Starting GPU Registry..."
cd ../..
python gpu_registry_demo.py &
REGISTRY_PID=$!

# Start GPU miner
echo "Starting GPU Miner..."
python gpu_miner_with_wait.py &
MINER_PID=$!

echo "All services started!"
echo "Coordinator API: http://10.1.223.93:8000"
echo "Blockchain RPC: http://10.1.223.93:9080"
echo "Trade Exchange: http://10.1.223.93:3002"
echo "GPU Registry: http://10.1.223.93:8091"

# Wait for services
wait $COORD_PID $BLOCK_PID $EXCHANGE_PID $REGISTRY_PID $MINER_PID
"""
    
    # Write startup script to container
    with open('/tmp/startup.sh', 'w') as f:
        f.write(startup_script)
    subprocess.run(f"incus file push /tmp/startup.sh {container}/home/oib/aitbc/", shell=True)
    run_command("chmod +x /home/oib/aitbc/startup.sh", container)
    
    # Create systemd service
    print("\n⚙️ Creating systemd service...")
    service_content = """[Unit]
Description=AITBC Services with GPU Miner
After=network.target

[Service]
Type=simple
User=oib
WorkingDirectory=/home/oib/aitbc
ExecStart=/home/oib/aitbc/startup.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
    
    with open('/tmp/aitbc.service', 'w') as f:
        f.write(service_content)
    subprocess.run(f"incus file push /tmp/aitbc.service {container}/tmp/", shell=True)
    run_command("mv /tmp/aitbc.service /etc/systemd/system/", container)
    run_command("systemctl daemon-reload", container)
    run_command("systemctl enable aitbc.service", container)
    run_command("systemctl start aitbc.service", container)
    
    print("\n✅ Deployment complete!")
    print(f"\n📊 Service URLs:")
    print(f"  - Coordinator API: http://{container_ip}:8000")
    print(f"  - Blockchain RPC: http://{container_ip}:9080")
    print(f"  - Trade Exchange: http://{container_ip}:3002")
    print(f"  - GPU Registry: http://{container_ip}:8091")
    print(f"\n🔍 Check GPU status:")
    print(f"  curl http://{container_ip}:8091/miners/list")
    
    print(f"\n📋 To manage services in container:")
    print(f"  incus exec {container} -- systemctl status aitbc")
    print(f"  incus exec {container} -- journalctl -u aitbc -f")

if __name__ == "__main__":
    deploy_to_container()
