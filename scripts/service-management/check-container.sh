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
incus exec aitbc -- ps aux | grep -E "(uvicorn|python)" | grep -v grep || echo "No services running"

echo ""
echo "🌐 Ports listening in container:"
incus exec aitbc -- ss -tlnp | grep -E "(8000|9080|3001|3002)" || echo "No ports listening"

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

# Start the services
incus exec aitbc -- bash -c "
cd /home/oib/aitbc
pkill -f uvicorn 2>/dev/null || true
pkill -f server.py 2>/dev/null || true

# Start blockchain node
cd apps/blockchain-node
source ../../.venv/bin/activate
python -m uvicorn aitbc_chain.app:app --host 0.0.0.0 --port 9080 &

# Start coordinator API
cd ../coordinator-api
source ../../.venv/bin/activate
python -m uvicorn src.app.main:app --host 0.0.0.0 --port 8000 &

# Start marketplace UI
cd ../marketplace-ui
python server.py --port 3001 &

# Start trade exchange
cd ../trade-exchange
python server.py --port 3002 &

sleep 3
echo 'Services started!'
"

echo ""
echo "✅ Done! Check services:"
echo "incus exec aitbc -- ps aux | grep uvicorn"
