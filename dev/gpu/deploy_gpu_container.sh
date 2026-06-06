#!/bin/bash
# Deploy GPU Miner to AITBC Container

echo "🚀 Deploying GPU Miner to AITBC Container..."

# Check if container is accessible
echo "1. Checking container access..."
sudo incus exec aitbc -- whoami

# Copy GPU miner files
echo "2. Copying GPU miner files..."
sudo incus file push /home/oib/windsurf/aitbc/gpu_miner_with_wait.py aitbc/home/oib/
sudo incus file push /home/oib/windsurf/aitbc/gpu_registry_demo.py aitbc/home/oib/

# Install dependencies
echo "3. Installing dependencies..."
sudo incus exec aitbc -- pip install httpx fastapi uvicorn psutil

# Create GPU miner service
echo "4. Creating GPU miner service..."
cat << 'EOF' | sudo tee /tmp/gpu-miner.service
[Unit]
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
EOF

sudo incus file push /tmp/gpu-miner.service aitbc/tmp/
sudo incus exec aitbc -- sudo mv /tmp/gpu-miner.service /etc/systemd/system/
sudo incus exec aitbc -- sudo systemctl daemon-reload
sudo incus exec aitbc -- sudo systemctl enable gpu-miner.service
sudo incus exec aitbc -- sudo systemctl start gpu-miner.service

# Create GPU registry service
echo "5. Creating GPU registry service..."
cat << 'EOF' | sudo tee /tmp/gpu-registry.service
[Unit]
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
EOF

sudo incus file push /tmp/gpu-registry.service aitbc/tmp/
sudo incus exec aitbc -- sudo mv /tmp/gpu-registry.service /etc/systemd/system/
sudo incus exec aitbc -- sudo systemctl daemon-reload
sudo incus exec aitbc -- sudo systemctl enable gpu-registry.service
sudo incus exec aitbc -- sudo systemctl start gpu-registry.service

# Check services
echo "6. Checking services..."
echo "GPU Miner Service:"
sudo incus exec aitbc -- sudo systemctl status gpu-miner.service --no-pager

echo -e "\nGPU Registry Service:"
sudo incus exec aitbc -- sudo systemctl status gpu-registry.service --no-pager

# Show access URLs
echo -e "\n✅ Deployment complete!"
echo "Access URLs:"
echo "  - Container IP: 10.1.223.93"
echo "  - GPU Registry: http://10.1.223.93:8091/miners/list"
echo "  - Coordinator API: http://10.1.223.93:8000"

echo -e "\nTo check GPU status:"
echo "  curl http://10.1.223.93:8091/miners/list"
