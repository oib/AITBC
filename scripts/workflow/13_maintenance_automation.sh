#!/bin/bash
# AITBC Maintenance Automation Script
# Handles environment cleanup, configuration verification, and code synchronization

echo "=== AITBC Maintenance Automation ==="

# Step 1: Legacy Environment File Cleanup
echo "1. Legacy Environment File Cleanup..."
echo "   Removing .env.production and .env references from systemd services..."

# Find and update systemd service files
find /etc/systemd/system/aitbc-blockchain-*.service.d/ -name "*.conf" -exec grep -l "EnvironmentFile.*env" {} \; 2>/dev/null | while read file; do
  echo "   Updating: $file"
  sed -i 's|EnvironmentFile=/opt/aitbc/.env|EnvironmentFile=/etc/aitbc/blockchain.env|g' "$file"
  sed -i 's|EnvironmentFile=.*\.env\.production|EnvironmentFile=/etc/aitbc/blockchain.env|g' "$file"
done

# Remove any remaining old references
find /etc/systemd/system/aitbc-blockchain-*.service.d/ -name "*.conf" -exec grep -l "EnvironmentFile.*\.env\.production" {} \; 2>/dev/null | while read file; do
  echo "   Removing .env.production references from: $file"
  sed -i 's|EnvironmentFile.*\.env\.production|EnvironmentFile=/etc/aitbc/blockchain.env|g' "$file"
done

echo "   ✅ Legacy environment file cleanup completed"

# Step 2: Final Configuration Verification
echo "2. Final Configuration Verification..."
echo "   Checking systemd service configurations..."

# Verify all services use correct environment file
SERVICES_USING_CORRECT_ENV=$(find /etc/systemd/system/aitbc-blockchain-*.service.d/ -name "*.conf" -exec grep -l "EnvironmentFile=/etc/aitbc/blockchain.env" {} \; 2>/dev/null | wc -l)
echo "   Services using correct environment file: $SERVICES_USING_CORRECT_ENV"

# Verify the centralized environment file exists
if [ -f "/etc/aitbc/blockchain.env" ]; then
  echo "   ✅ Centralized environment file exists"
  echo "   Key configurations:"
  grep -E "^(chain_id|enable_block_production|proposer_id|keystore_path|db_path)" /etc/aitbc/blockchain.env | head -5
else
  echo "   ❌ Centralized environment file missing"
  exit 1
fi

# Check for legacy environment files
if [ -f "/opt/aitbc/.env" ]; then
  echo "   ⚠️ Legacy /opt/aitbc/.env still exists"
else
  echo "   ✅ No legacy environment files found"
fi

# Test that services can access the centralized configuration
echo "   Testing service configuration access..."
systemctl daemon-reload

# Step 3: Cross-Node Code Synchronization
echo "3. Cross-Node Code Synchronization..."
echo "   Ensuring aitbc node stays synchronized with aitbc1..."

# Check current git status on aitbc1
echo "   Current git status on aitbc1:"
cd /opt/aitbc
git status --porcelain

# Push any local changes to remote
if [ -n "$(git status --porcelain)" ]; then
  echo "   Pushing local changes to remote..."
  git add -A
  git commit -m "Automated maintenance update - $(date)"
  git push origin main
else
  echo "   No local changes to push"
fi

# Sync code to aitbc
echo "   Syncing code to aitbc..."
ssh aitbc '
  cd /opt/aitbc
  echo "   Current branch: $(git branch --show-current)"
  echo "   Pulling latest changes..."
  git pull origin main
  echo "   Latest commit: $(git log --oneline -1)"
  
  # Restart services if code changed
  echo "   Restarting services to apply code changes..."
  systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc
  
  # Verify services are running
  echo "   Verifying services..."
  systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc
'

# Verify both nodes are on the same commit
echo "4. Verification Results..."
AITBC1_COMMIT=$(cd /opt/aitbc && git rev-parse --short HEAD)
AITBC_COMMIT=$(ssh aitbc 'cd /opt/aitbc && git rev-parse --short HEAD')

echo "   aitbc1 commit: $AITBC1_COMMIT"
echo "   aitbc commit: $AITBC_COMMIT"

if [ "$AITBC1_COMMIT" = "$AITBC_COMMIT" ]; then
  echo "   ✅ Code synchronized between nodes"
else
  echo "   ❌ Code not synchronized - manual intervention required"
fi

# Test that both nodes are operational
echo "5. Cross-node functionality test..."
AITBC1_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height 2>/dev/null || echo "0")
AITBC_HEIGHT=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height 2>/dev/null || echo "0")

echo "   aitbc1 height: $AITBC1_HEIGHT"
echo "   aitbc height: $AITBC_HEIGHT"

HEIGHT_DIFF=$((AITBC1_HEIGHT - AITBC_HEIGHT))
if [ $HEIGHT_DIFF -le 5 ]; then
  echo "   ✅ Cross-node functionality working"
else
  echo "   ⚠️ Cross-node sync issues detected (diff: $HEIGHT_DIFF blocks)"
fi

# Service health check
echo "6. Service Health Check..."
AITBC1_SERVICES=$(systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc | grep -c "active")
AITBC_SERVICES=$(ssh aitbc 'systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc | grep -c "active"')

echo "   aitbc1 active services: $AITBC1_SERVICES/2"
echo "   aitbc active services: $AITBC_SERVICES/2"

if [ "$AITBC1_SERVICES" -eq 2 ] && [ "$AITBC_SERVICES" -eq 2 ]; then
  echo "   ✅ All services operational"
else
  echo "   ❌ Some services not running"
fi

echo "=== Maintenance Automation Complete ==="
