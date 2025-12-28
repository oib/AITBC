#!/usr/bin/env python3
"""
Deploy AITBC services to incus container
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
    
    print("🚀 Deploying AITBC services to container...")
    
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
    run_command("cd /home/oib/aitbc && source .venv/bin/activate && pip install fastapi uvicorn httpx sqlmodel", container)
    
    # Install dependencies
    print("\n📦 Installing dependencies...")
    run_command("cd /home/oib/aitbc/apps/coordinator-api && source ../../.venv/bin/activate && pip install -e .", container)
    run_command("cd /home/oib/aitbc/apps/blockchain-node && source ../../.venv/bin/activate && pip install -e .", container)
    
    # Create startup script
    print("\n🔧 Creating startup script...")
    startup_script = """#!/bin/bash
cd /home/oib/aitbc

# Start blockchain node
echo "Starting blockchain node..."
cd apps/blockchain-node
source ../../.venv/bin/activate
python -m uvicorn aitbc_chain.app:app --host 0.0.0.0 --port 9080 &
NODE_PID=$!

# Start coordinator API
echo "Starting coordinator API..."
cd ../coordinator-api
source ../../.venv/bin/activate
python -m uvicorn src.app.main:app --host 0.0.0.0 --port 8000 &
COORD_PID=$!

# Start marketplace UI
echo "Starting marketplace UI..."
cd ../marketplace-ui
python server.py --port 3001 &
MARKET_PID=$!

# Start trade exchange
echo "Starting trade exchange..."
cd ../trade-exchange
python server.py --port 3002 &
EXCHANGE_PID=$!

echo "Services started!"
echo "Blockchain: http://10.1.223.93:9080"
echo "API: http://10.1.223.93:8000"
echo "Marketplace: http://10.1.223.93:3001"
echo "Exchange: http://10.1.223.93:3002"

# Wait for services
wait $NODE_PID $COORD_PID $MARKET_PID $EXCHANGE_PID
"""
    
    # Write startup script to container
    with open('/tmp/start_aitbc.sh', 'w') as f:
        f.write(startup_script)
    
    subprocess.run("incus file push /tmp/start_aitbc.sh aitbc/home/oib/", shell=True)
    run_command("chmod +x /home/oib/start_aitbc.sh", container)
    
    # Start services
    print("\n🚀 Starting AITBC services...")
    run_command("/home/oib/start_aitbc.sh", container)
    
    print(f"\n✅ Services deployed to container!")
    print(f"\n📋 Access URLs:")
    print(f"  🌐 Container IP: {container_ip}")
    print(f"  📊 Marketplace: http://{container_ip}:3001")
    print(f"  💱 Trade Exchange: http://{container_ip}:3002")
    print(f"  🔗 API: http://{container_ip}:8000")
    print(f"  ⛓️  Blockchain: http://{container_ip}:9080")

if __name__ == "__main__":
    deploy_to_container()
