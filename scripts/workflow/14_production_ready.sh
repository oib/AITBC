#!/bin/bash
# AITBC Production Ready Script
# Complete production deployment and verification

echo "=== AITBC Production Ready Deployment ==="

# Check prerequisites
echo "1. Prerequisites Check..."
if [ "$(hostname)" != "aitbc1" ]; then
  echo "❌ Error: This script must be run on aitbc1 (genesis authority node)"
  exit 1
fi

# Define production workflow
PRODUCTION_STEPS=(
  "01_preflight_setup.sh:Pre-Flight Setup"
  "02_genesis_authority_setup.sh:Genesis Authority Setup"
  "03_follower_node_setup.sh:Follower Node Setup"
  "08_blockchain_sync_fix.sh:Blockchain Sync Fix"
  "04_create_wallet.sh:Wallet Creation"
  "09_transaction_manager.sh:Transaction Manager"
  "12_complete_sync.sh:Complete Sync"
  "11_network_optimizer.sh:Network Optimization"
  "13_maintenance_automation.sh:Maintenance Automation"
  "06_final_verification.sh:Final Verification"
)

# Execute production workflow
echo "2. Executing Production Workflow..."
FAILED_STEPS=()

for step in "${PRODUCTION_STEPS[@]}"; do
  SCRIPT=$(echo "$step" | cut -d: -f1)
  DESCRIPTION=$(echo "$step" | cut -d: -f2)
  
  echo
  echo "=========================================="
  echo "PRODUCTION STEP: $DESCRIPTION"
  echo "SCRIPT: $SCRIPT"
  echo "=========================================="
  
  if [ -f "/opt/aitbc/scripts/workflow/$SCRIPT" ]; then
    echo "Executing $SCRIPT..."
    bash "/opt/aitbc/scripts/workflow/$SCRIPT"
    
    if [ $? -eq 0 ]; then
      echo "✅ $DESCRIPTION completed successfully"
    else
      echo "❌ $DESCRIPTION failed"
      FAILED_STEPS+=("$DESCRIPTION")
    fi
  else
    echo "❌ Script not found: $SCRIPT"
    FAILED_STEPS+=("$DESCRIPTION (script missing)")
  fi
done

# Production verification
echo
echo "=========================================="
echo "PRODUCTION VERIFICATION"
echo "=========================================="

# Service status
echo "3. Service Status Verification:"
AITBC1_SERVICES=$(systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc | grep -c "active")
AITBC_SERVICES=$(ssh aitbc 'systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc 2>/dev/null | grep -c "active"')

echo "   aitbc1 services: $AITBC1_SERVICES/2 active"
echo "   aitbc services: $AITBC_SERVICES/2 active"

# Blockchain status
echo "4. Blockchain Status:"
AITBC1_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height 2>/dev/null || echo "0")
AITBC_HEIGHT=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height 2>/dev/null || echo "0")

echo "   aitbc1 height: $AITBC1_HEIGHT"
echo "   aitbc height: $AITBC_HEIGHT"
echo "   Sync difference: $((AITBC1_HEIGHT - AITBC_HEIGHT)) blocks"

# Network performance
echo "5. Network Performance:"
AITBC1_RPC_TIME=$(curl -w "%{time_total}" -s -o /dev/null http://localhost:8006/rpc/head)
AITBC_RPC_TIME=$(ssh aitbc 'curl -w "%{time_total}" -s -o /dev/null http://localhost:8006/rpc/head')
NETWORK_LATENCY=$(ping -c 1 10.1.223.93 | grep "time=" | cut -d= -f2 | cut -d" " -f1)

echo "   aitbc1 RPC time: ${AITBC1_RPC_TIME}s"
echo "   aitbc RPC time: ${AITBC_RPC_TIME}s"
echo "   Network latency: ${NETWORK_LATENCY}ms"

# Security check
echo "6. Security Configuration:"
if [ -f "/etc/aitbc/blockchain.env" ]; then
  ENV_PERMISSIONS=$(stat -c "%a" /etc/aitbc/blockchain.env)
  echo "   Environment file permissions: $ENV_PERMISSIONS"
else
  echo "   ❌ Environment file missing"
fi

KEYSTORE_PERMISSIONS=$(stat -c "%a" /var/lib/aitbc/keystore 2>/dev/null || echo "missing")
echo "   Keystore permissions: $KEYSTORE_PERMISSIONS"

# Production readiness assessment
echo
echo "=========================================="
echo "PRODUCTION READINESS ASSESSMENT"
echo "=========================================="

SERVICES_OK=false
SYNC_OK=false
PERFORMANCE_OK=false
SECURITY_OK=false

# Check services
if [ "$AITBC1_SERVICES" -eq 2 ] && [ "$AITBC_SERVICES" -eq 2 ]; then
  SERVICES_OK=true
  echo "✅ Services: All operational"
else
  echo "❌ Services: Some services not running"
fi

# Check sync
HEIGHT_DIFF=$((AITBC1_HEIGHT - AITBC_HEIGHT))
if [ $HEIGHT_DIFF -le 2 ]; then
  SYNC_OK=true
  echo "✅ Sync: Nodes synchronized"
else
  echo "❌ Sync: Nodes not synchronized (diff: $HEIGHT_DIFF blocks)"
fi

# Check performance
if (( $(echo "$AITBC1_RPC_TIME < 1.0" | bc -l) )) && (( $(echo "$AITBC_RPC_TIME < 1.0" | bc -l) )); then
  PERFORMANCE_OK=true
  echo "✅ Performance: RPC times acceptable"
else
  echo "❌ Performance: RPC times too slow"
fi

# Check security
if [ "$ENV_PERMISSIONS" = "644" ] && [ "$KEYSTORE_PERMISSIONS" = "700" ]; then
  SECURITY_OK=true
  echo "✅ Security: Permissions correct"
else
  echo "❌ Security: Check permissions"
fi

# Final assessment
echo
echo "7. Final Production Status:"
if [ "$SERVICES_OK" = true ] && [ "$SYNC_OK" = true ] && [ "$PERFORMANCE_OK" = true ] && [ "$SECURITY_OK" = true ]; then
  echo "🎉 PRODUCTION READY!"
  echo "   All systems operational and optimized"
  echo "   Ready for production deployment"
else
  echo "⚠️  NOT PRODUCTION READY"
  echo "   Some issues need to be resolved"
  
  if [ ${#FAILED_STEPS[@]} -gt 0 ]; then
    echo "   Failed steps: ${FAILED_STEPS[*]}"
  fi
fi

echo
echo "8. Next Steps:"
echo "   • Monitor with: /opt/aitbc/scripts/health_check.sh"
echo "   • Test with: /opt/aitbc/tests/integration_test.sh"
echo "   • Scale with: /opt/aitbc/scripts/provision_node.sh <new-node>"
echo "   • Enterprise features: /opt/aitbc/cli/enterprise_cli.py"

echo "=== Production Ready Deployment Complete ==="
