#!/bin/bash

# Diagnose AITBC services

# Service list and ports come from lib/services.sh so all of these scripts agree.
source "$(dirname "${BASH_SOURCE[0]}")/lib/services.sh"

echo "🔍 Diagnosing AITBC Services"
echo "=========================="
echo ""

# Check systemd services
echo "📋 Systemd Services:"
for svc in "${AITBC_SERVICES[@]}" "$AITBC_SECRETS_UNIT"; do
    status=$(systemctl is-active "$svc" 2>/dev/null || echo "not-found")
    echo "  $svc: $status"
done

echo ""
echo "🌐 Ports listening:"
for port in $(printf '%s\n' "${AITBC_SERVICE_PORTS[@]}" | sort -n); do
    echo -n "  Port $port: "
    if ss -ltnp 2>/dev/null | grep -q ":$port "; then
        echo "✅ listening"
    else
        echo "❌ not listening"
    fi
done

echo ""
echo "🌐 Testing Endpoints:"

echo "Coordinator API Health:"
curl -s http://127.0.0.1:8203/v1/health 2>/dev/null && echo "  ✅ OK" || echo "  ❌ Failed"

echo "Blockchain RPC:"
curl -s http://127.0.0.1:8202/rpc/head 2>/dev/null | head -c 50 && echo "..." || echo "  ❌ Failed"

echo "Exchange Health:"
curl -s http://127.0.0.1:8106/health 2>/dev/null && echo "  ✅ OK" || echo "  ❌ Failed"

echo "Marketplace Health:"
curl -s http://127.0.0.1:8107/health 2>/dev/null && echo "  ✅ OK" || echo "  ❌ Failed"

echo "Trading Health:"
curl -s http://127.0.0.1:8201/health 2>/dev/null && echo "  ✅ OK" || echo "  ❌ Failed"

echo "Wallet Health:"
curl -s http://127.0.0.1:8108/health 2>/dev/null && echo "  ✅ OK" || echo "  ❌ Failed"

echo ""
echo "🌐 Remote Endpoints (via domain):"
echo "Domain API Health:"
curl -s https://aitbc.bubuit.net/health 2>/dev/null && echo "  ✅ OK" || echo "  ❌ Failed"

echo ""
echo "📝 Instructions:"
echo "1. Start services: sudo systemctl start aitbc-*"
echo "2. Check status:   systemctl status aitbc-exchange"
echo "3. View logs:      journalctl -u aitbc-exchange -f"
echo ""
echo "If services won't start:"
echo "1. Check logs: journalctl -u aitbc-exchange --since '5 min ago'"
echo "2. Check config: /etc/aitbc/*.env"
echo "3. Check secrets: sudo systemctl status aitbc-load-secrets"
