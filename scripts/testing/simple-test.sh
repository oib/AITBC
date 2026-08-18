#!/bin/bash
# Simple AITBC Services Test

set -euo pipefail

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
# Was labelled "GPU Multimodal (8203)" until V23-99. 8203 is aitbc-coordinator-api; the GPU
# service is 8101. Every other port in this file belongs to a service layout that does not
# exist on any AITBC host -- see V23-99 for that backlog.
echo "Coordinator API (8203): $(curl -fsS http://localhost:8203/health | jq -r .status 2>/dev/null || echo 'FAIL')"
echo "Modality Optimization (8012): $(curl -s http://localhost:8012/health | jq -r .status 2>/dev/null || echo 'FAIL')"
echo "Adaptive Learning (8013): $(curl -s http://localhost:8013/health | jq -r .status 2>/dev/null || echo 'FAIL')"
echo "Geographic Load Balancer (8017): $(curl -s http://localhost:8017/health | jq -r .status 2>/dev/null || echo 'FAIL')"

echo ""
echo "📊 Port Usage:"
# `|| true`: none of these ports listening is a real answer for a status dump, but under
# the pipefail this script gained in V23-99 an empty grep would abort it one line before
# it says it is done.
sudo netstat -tlnp | grep -E ":(8000|8001|8003|8010|8203|8012|8013|8017)" | sort || true

echo ""
echo "✅ All services tested!"
