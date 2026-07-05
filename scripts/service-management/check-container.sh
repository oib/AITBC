#!/bin/bash

# Check what's running in the aitbc container

echo "🔍 Checking AITBC Container Status"
echo "================================="

# First, let's see if we can access the container
if ! groups | grep -q incus; then
    echo "❌ You're not in the incus group!"
    echo "Run: sudo usermod -aG incus \$USER"
    echo "Then log out and log back in"
    exit 1
fi

echo "📋 Container Info:"
incus list | grep aitbc

echo ""
echo "🔧 Services in container:"
incus exec aitbc -- ps aux | grep -E "(uvicorn|python|simple_exchange)" | grep -v grep || echo "No services running"

echo ""
echo "🌐 Ports listening in container:"
incus exec aitbc -- ss -tlnp | grep -E "(8106|8107|8108|8201|8202|8203)" || echo "No ports listening"

echo ""
echo "📁 Nginx status:"
incus exec aitbc -- systemctl status nginx --no-pager -l | head -20

echo ""
echo "🔍 Nginx config test:"
incus exec aitbc -- nginx -t

echo ""
echo "📝 Nginx sites enabled:"
incus exec aitbc -- ls -la /etc/nginx/sites-enabled/

echo ""
echo "🚀 Starting services if needed..."

# Start the services via systemd
incus exec aitbc -- bash -c "
systemctl start aitbc-coordinator-api aitbc-blockchain-rpc aitbc-exchange aitbc-marketplace aitbc-trading 2>/dev/null || true

sleep 3
echo 'Services started!'
"

echo ""
echo "✅ Done! Check services:"
echo "incus exec aitbc -- systemctl status aitbc-exchange"
echo "incus exec aitbc -- systemctl status aitbc-coordinator-api"
