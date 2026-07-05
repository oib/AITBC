#!/usr/bin/env python3
"""
Deploy AITBC services to incus container.
Uses the canonical systemd service files from the repo.
"""

import os
import subprocess


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
    container_ip = os.getenv("AITBC_CONTAINER_IP", "127.0.0.1")

    print("🚀 Deploying AITBC services to container...")

    # Stop local services
    print("\n📋 Stopping local services...")
    subprocess.run("sudo systemctl stop aitbc-exchange aitbc-marketplace aitbc-trading aitbc-wallet 2>/dev/null || true", shell=True)
    subprocess.run("sudo systemctl stop aitbc-coordinator-api aitbc-blockchain-rpc aitbc-blockchain-p2p 2>/dev/null || true", shell=True)

    # Copy project to container
    print("\n📁 Copying project to container...")
    subprocess.run(f"incus file push -r /opt/aitbc {container}/opt/", shell=True)

    # Setup Python environment in container
    print("\n🐍 Setting up Python environment...")
    run_command("cd /opt/aitbc && python3 -m venv venv", container)
    run_command("cd /opt/aitbc && source venv/bin/activate && pip install fastapi uvicorn httpx sqlmodel", container)

    # Install dependencies
    print("\n📦 Installing dependencies...")
    run_command("cd /opt/aitbc/apps/coordinator-api && source ../../venv/bin/activate && pip install -e .", container)
    run_command("cd /opt/aitbc/apps/blockchain-node && source ../../venv/bin/activate && pip install -e .", container)
    run_command("cd /opt/aitbc && source venv/bin/activate && pip install -e apps/marketplace apps/trading apps/wallet", container)

    # Install systemd service files from the repo
    print("\n⚙️ Installing systemd services...")
    run_command("find /opt/aitbc/apps -name 'aitbc-*.service' -exec cp {} /etc/systemd/system/ \\;", container)
    run_command("systemctl daemon-reload", container)

    # Enable and start services
    print("\n🚀 Starting AITBC services...")
    services = [
        "aitbc-coordinator-api",
        "aitbc-blockchain-rpc",
        "aitbc-blockchain-p2p",
        "aitbc-exchange",
        "aitbc-marketplace",
        "aitbc-trading",
        "aitbc-wallet",
    ]
    for svc in services:
        run_command(f"systemctl enable {svc}", container)
    for svc in services:
        run_command(f"systemctl start {svc}", container)

    # Wait for services to start
    print("\n⏳ Waiting for services to start...")
    subprocess.run("sleep 5", shell=True)

    print("\n✅ Services deployed to container!")
    print("\n📋 Access URLs:")
    print(f"  🌐 Container IP: {container_ip}")
    print(f"  💱 Exchange:        http://{container_ip}:8106")
    print(f"  📊 Marketplace:     http://{container_ip}:8107")
    print(f"  🔗 API:             http://{container_ip}:8203")
    print(f"  ⛓️  Blockchain RPC:  http://{container_ip}:8202")
    print(f"  📈 Trading:         http://{container_ip}:8201")
    print(f"  👛 Wallet:          http://{container_ip}:8108")


if __name__ == "__main__":
    deploy_to_container()
