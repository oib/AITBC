#!/bin/bash
# Start GPU Miner Client

echo "=== AITBC GPU Miner Client Startup ==="
echo "Starting GPU miner client..."
echo ""

# Check if GPU is available
if ! command -v nvidia-smi &> /dev/null; then
    echo "WARNING: nvidia-smi not found, GPU may not be available"
fi

# Show GPU info
if command -v nvidia-smi &> /dev/null; then
    echo "=== GPU Status ==="
    nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader,nounits
    echo ""
fi

# Check if coordinator is running
echo "=== Checking Coordinator API ==="
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✓ Coordinator API is running on port 8000"
else
    echo "✗ Coordinator API is not accessible on port 8000"
    echo "  The miner will wait for the coordinator to start..."
fi

echo ""
echo "=== Starting GPU Miner ==="
cd /home/oib/windsurf/aitbc
python3 gpu_miner_with_wait.py
