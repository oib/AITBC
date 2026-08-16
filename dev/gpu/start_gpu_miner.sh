#!/bin/bash
# Start GPU Miner Client

set -euo pipefail

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
if curl -s http://localhost:9080/health > /dev/null 2>&1; then
    echo "✓ Coordinator API is running on port 9080"
else
    echo "✗ Coordinator API is not accessible on port 9080"
    echo "  The miner will wait for the coordinator to start..."
fi

echo ""
echo "=== Starting GPU Miner ==="

# This was `cd /home/oib/windsurf/aitbc && exec python3 scripts/gpu/gpu_miner_host.py`: a
# checkout that exists on one workstation, and under it a path that exists in no checkout at
# all -- scripts/gpu/ holds only a README. The miner lives next to this script, so run it
# from here.
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/gpu_miner_host.py"
