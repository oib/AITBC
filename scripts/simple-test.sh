#!/bin/bash
# Simple AITBC Services Test

echo "=== 🧪 AITBC Services Test ==="
echo "Testing new port logic implementation"
echo ""

# Test Core Services
echo "🔍 Core Services:"
echo "Coordinator API (8000): $(curl -s http://localhost:8000/v1/health | jq -r .status 2>/dev/null || echo 'FAIL')"
echo "Exchange API (8001): $(curl -s http://localhost:8001/ | jq -r .detail 2>/dev/null || echo 'FAIL')"
echo "Blockchain RPC (8003): $(curl -s http://localhost:8003/rpc/head | jq -r .height 2>/dev/null || echo 'FAIL')"

echo ""
echo "🚀 Enhanced Services:"
echo "Multimodal GPU (8010): $(curl -s http://localhost:8010/health | jq -r .status 2>/dev/null || echo 'FAIL')"
echo "GPU Multimodal (8011): $(curl -s http://localhost:8011/health | jq -r .status 2>/dev/null || echo 'FAIL')"
echo "Modality Optimization (8012): $(curl -s http://localhost:8012/health | jq -r .status 2>/dev/null || echo 'FAIL')"
echo "Adaptive Learning (8013): $(curl -s http://localhost:8013/health | jq -r .status 2>/dev/null || echo 'FAIL')"
echo "Web UI (8016): $(curl -s http://localhost:8016/health | jq -r .status 2>/dev/null || echo 'FAIL')"
echo "Geographic Load Balancer (8017): $(curl -s http://localhost:8017/health | jq -r .status 2>/dev/null || echo 'FAIL')"

echo ""
echo "📊 Port Usage:"
sudo netstat -tlnp | grep -E ":(8000|8001|8003|8010|8011|8012|8013|8016|8017)" | sort

echo ""
echo "✅ All services tested!"
