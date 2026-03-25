#!/bin/bash
# Simple verification of GPU deployment in container

echo "🔍 Checking GPU deployment in AITBC container..."

# Check if services exist
echo "1. Checking if services are installed..."
if ssh aitbc 'systemctl list-unit-files | grep -E "aitbc-gpu" 2>/dev/null'; then
    echo "✅ GPU services found"
else
    echo "❌ GPU services not found - need to deploy first"
    exit 1
fi

# Check service status
echo -e "\n2. Checking service status..."
ssh aitbc 'sudo systemctl status aitbc-gpu-registry.service --no-pager --lines=3'
ssh aitbc 'sudo systemctl status aitbc-gpu-miner.service --no-pager --lines=3'

# Check if ports are listening
echo -e "\n3. Checking if GPU registry is listening..."
if ssh aitbc 'ss -tlnp | grep :8091 2>/dev/null'; then
    echo "✅ GPU registry listening on port 8091"
else
    echo "❌ GPU registry not listening"
fi

# Check GPU registration
echo -e "\n4. Checking GPU registration from container..."
ssh aitbc 'curl -s http://127.0.0.1:8091/miners/list 2>/dev/null | python3 -c "import sys,json; data=json.load(sys.stdin); print(f\"Found {len(data.get(\"gpus\", []))} GPU(s)\")" 2>/dev/null || echo "Failed to get GPU list"'

echo -e "\n5. Checking from host (10.1.223.93)..."
curl -s http://10.1.223.93:8091/miners/list 2>/dev/null | python3 -c "import sys,json; data=json.load(sys.stdin); print(f\"✅ From host: Found {len(data.get(\"gpus\", []))} GPU(s)\")" 2>/dev/null || echo "❌ Cannot access from host"

echo -e "\n✅ Verification complete!"
