#!/bin/bash

# Diagnose AITBC services

set -euo pipefail

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
curl -fsS "http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-coordinator-api]}/health" 2>/dev/null && echo "  ✅ OK" || echo "  ❌ Failed"

echo "Blockchain RPC:"
curl -s http://127.0.0.1:8202/rpc/head 2>/dev/null | head -c 50 && echo "..." || echo "  ❌ Failed"

echo "Exchange Health:"
curl -fsS "http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-exchange]}/health" 2>/dev/null && echo "  ✅ OK" || echo "  ❌ Failed"

echo "Marketplace Health:"
curl -fsS "http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-marketplace]}/health" 2>/dev/null && echo "  ✅ OK" || echo "  ❌ Failed"

echo "Trading Health:"
curl -fsS "http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-trading]}/health" 2>/dev/null && echo "  ✅ OK" || echo "  ❌ Failed"

echo "Wallet Health:"
curl -fsS "http://127.0.0.1:${AITBC_SERVICE_PORTS[aitbc-wallet]}/health" 2>/dev/null && echo "  ✅ OK" || echo "  ❌ Failed"

echo ""
echo "🌐 Remote Endpoints (via domain):"
echo "Domain API Health:"
curl -fsS https://aitbc.bubuit.net/health 2>/dev/null && echo "  ✅ OK" || echo "  ❌ Failed"

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
