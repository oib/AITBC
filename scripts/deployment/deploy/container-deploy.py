#!/usr/bin/env python3
"""
Deploy AITBC services to incus container.
Uses the canonical systemd service files from the repo.
"""

import os
import subprocess
import sys
import time


def run_command(cmd, container=None):
    """Run command locally or in container"""
    if container:
        # bash -c inside the container preserves the `cd X && source Y && ...`
        # compound-command semantics without a local shell or string concat.
        argv = ["incus", "exec", container, "--", "bash", "-c", cmd]
    else:
        argv = ["bash", "-c", cmd]
    print(f"Running: {' '.join(argv)}")
    result = subprocess.run(argv, capture_output=True, text=True)
    if result.returncode != 0:
        # #893: a failed deploy step is fatal — no silent success banner.
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return True


def deploy_to_container():
    container = os.environ.get("AITBC_CONTAINER")
    if not container:
        print("refused: set AITBC_CONTAINER — no default target (#893)")
        sys.exit(1)
    container_ip = os.getenv("AITBC_CONTAINER_IP", "127.0.0.1")

    print("🚀 Deploying AITBC services to container...")

    # #893: a deploy INTO a container must not stop the host's own units —
    # the old stop pair left the host's rpc/market/wallet down permanently.

    # Copy project to container
    print("\n📁 Copying project to container...")
    if subprocess.run(["incus", "file", "push", "-r", "/opt/aitbc", f"{container}/opt/"]).returncode != 0:
        print("Error: incus file push failed")
        sys.exit(1)

    # Setup Python environment in container
    print("\n🐍 Setting up Python environment...")
    run_command("cd /opt/aitbc && python3 -m venv venv", container)
    run_command("cd /opt/aitbc && source venv/bin/activate && pip install fastapi uvicorn httpx sqlmodel", container)

    # Install dependencies
    print("\n📦 Installing dependencies...")
    run_command("cd /opt/aitbc/apps/coordinator-api && source ../../venv/bin/activate && pip install -e .", container)
    run_command("cd /opt/aitbc/apps/blockchain-node && source ../../venv/bin/activate && pip install -e .", container)
    run_command("cd /opt/aitbc && source venv/bin/activate && pip install -e apps/market apps/trading apps/wallet", container)

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
        "aitbc-market",
        "aitbc-trading",
        "aitbc-wallet",
    ]
    for svc in services:
        run_command(f"systemctl enable {svc}", container)
    for svc in services:
        run_command(f"systemctl start {svc}", container)

    # Wait for services to start
    print("\n⏳ Waiting for services to start...")
    time.sleep(5)

    print("\n✅ Services deployed to container!")
    print("\n📋 Access URLs:")
    print(f"  🌐 Container IP: {container_ip}")
    print(f"  💱 Exchange:        http://{container_ip}:8106")
    print(f"  📊 Market:     http://{container_ip}:8107")
    print(f"  🔗 API:             http://{container_ip}:8203")
    print(f"  ⛓️  Blockchain RPC:  http://{container_ip}:8202")
    print(f"  📈 Trading:         http://{container_ip}:8201")
    print(f"  👛 Wallet:          http://{container_ip}:8108")


if __name__ == "__main__":
    deploy_to_container()
