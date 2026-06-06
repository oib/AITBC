#!/bin/bash
# Deploy GPU Miner to AITBC Container - All in One

set -e

echo "🚀 Deploying GPU Miner to AITBC Container..."

# Step 1: Copy files
echo "1. Copying GPU scripts..."
scp -o StrictHostKeyChecking=no /home/oib/windsurf/aitbc/gpu_registry_demo.py aitbc:/home/oib/
scp -o StrictHostKeyChecking=no /home/oib/windsurf/aitbc/gpu_miner_with_wait.py aitbc:/home/oib/

# Step 2: Install Python and deps
echo "2. Installing Python and dependencies..."
ssh aitbc 'sudo apt-get update -qq'
ssh aitbc 'sudo apt-get install -y -qq python3 python3-venv python3-pip'
ssh aitbc 'python3 -m venv /home/oib/.venv-gpu'
ssh aitbc '/home/oib/.venv-gpu/bin/pip install -q fastapi uvicorn httpx psutil'

# Step 3: Create GPU registry service
echo "3. Creating GPU registry service..."
ssh aitbc "sudo tee /etc/systemd/system/aitbc-gpu-registry.service >/dev/null <<'EOF'
[Unit]
Description=AITBC GPU Registry
After=network.target

[Service]
Type=simple
User=oib
WorkingDirectory=/home/oib
ExecStart=/home/oib/.venv-gpu/bin/python /home/oib/gpu_registry_demo.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF"

# Step 4: Start GPU registry
echo "4. Starting GPU registry..."
ssh aitbc 'sudo systemctl daemon-reload'
ssh aitbc 'sudo systemctl enable --now aitbc-gpu-registry.service'

# Step 5: Create GPU miner service
echo "5. Creating GPU miner service..."
ssh aitbc "sudo tee /etc/systemd/system/aitbc-gpu-miner.service >/dev/null <<'EOF'
[Unit]
Description=AITBC GPU Miner Client
After=network.target aitbc-gpu-registry.service
Wants=aitbc-gpu-registry.service

[Service]
Type=simple
User=oib
WorkingDirectory=/home/oib
ExecStart=/home/oib/.venv-gpu/bin/python /home/oib/gpu_miner_with_wait.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF"

# Step 6: Start GPU miner
echo "6. Starting GPU miner..."
ssh aitbc 'sudo systemctl daemon-reload'
ssh aitbc 'sudo systemctl enable --now aitbc-gpu-miner.service'

# Step 7: Check services
echo "7. Checking services..."
echo -e "\n=== GPU Registry Service ==="
ssh aitbc 'sudo systemctl status aitbc-gpu-registry.service --no-pager'

echo -e "\n=== GPU Miner Service ==="
ssh aitbc 'sudo systemctl status aitbc-gpu-miner.service --no-pager'

# Step 8: Verify GPU registration
echo -e "\n8. Verifying GPU registration..."
sleep 3
echo " curl http://10.1.223.93:8091/miners/list"
curl -s http://10.1.223.93:8091/miners/list | python3 -c "import sys,json; data=json.load(sys.stdin); print(f'✅ Found {len(data.get(\"gpus\", []))} GPU(s)'); [print(f'  - {gpu[\"capabilities\"][\"gpu\"][\"model\"]} ({gpu[\"capabilities\"][\"gpu\"][\"memory_gb\"]}GB)') for gpu in data.get('gpus', [])]"

echo -e "\n✅ Deployment complete!"
echo "GPU Registry: http://10.1.223.93:8091"
echo "GPU Miner: Running and sending heartbeats"
