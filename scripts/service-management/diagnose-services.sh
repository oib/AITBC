#!/bin/bash

# Diagnose AITBC services

echo "🔍 Diagnosing AITBC Services"
echo "=========================="
echo ""

# Check local services
echo "📋 Local Services:"
echo "Port 8000 (Coordinator API):"
lsof -i :8000 2>/dev/null || echo "  ❌ Not running"

echo "Port 9080 (Blockchain Node):"
lsof -i :9080 2>/dev/null || echo "  ❌ Not running"

echo "Port 3001 (Marketplace UI):"
lsof -i :3001 2>/dev/null || echo "  ❌ Not running"

echo "Port 3002 (Trade Exchange):"
lsof -i :3002 2>/dev/null || echo "  ❌ Not running"

echo ""
echo "🌐 Testing Endpoints:"

# Test local endpoints
echo "Local API Health:"
curl -s http://127.0.0.1:8000/v1/health 2>/dev/null && echo "  ✅ OK" || echo "  ❌ Failed"

echo "Local Blockchain:"
curl -s http://127.0.0.1:9080/rpc/head 2>/dev/null | head -c 50 && echo "..." || echo "  ❌ Failed"

echo "Local Admin:"
curl -s http://127.0.0.1:8000/v1/admin/stats 2>/dev/null | head -c 50 && echo "..." || echo "  ❌ Failed"

echo ""
echo "🌐 Remote Endpoints (via domain):"
echo "Domain API Health:"
curl -s https://aitbc.bubuit.net/health 2>/dev/null && echo "  ✅ OK" || echo "  ❌ Failed"

echo "Domain Admin:"
curl -s https://aitbc.bubuit.net/admin/stats 2>/dev/null | head -c 50 && echo "..." || echo "  ❌ Failed"

echo ""
echo "🔧 Fixing common issues..."

# Stop any conflicting services
echo "Stopping local services..."
sudo fuser -k 8000/tcp 2>/dev/null || true
sudo fuser -k 9080/tcp 2>/dev/null || true
sudo fuser -k 3001/tcp 2>/dev/null || true
sudo fuser -k 3002/tcp 2>/dev/null || true

echo ""
echo "📝 Instructions:"
echo "1. Make sure you're in the incus group: sudo usermod -aG incus \$USER"
echo "2. Log out and log back in"
echo "3. Run: incus exec aitbc -- bash"
echo "4. Inside container, run: /home/oib/start_aitbc.sh"
echo "5. Check services: ps aux | grep uvicorn"
echo ""
echo "If services are running in container but not accessible:"
echo "1. Check port forwarding to 10.1.223.93"
echo "2. Check nginx config in container"
echo "3. Check firewall rules"
