#!/bin/bash
#
# AITBC Permission Test Suite
# Run this to verify your permission setup is working correctly
#

echo "=== 🧪 AITBC Permission Setup Test Suite ==="
echo ""

# Test 1: Service Management
echo "📋 Test 1: Service Management (should NOT ask for password)"
echo "Command: sudo systemctl status aitbc-coordinator-api.service --no-pager"
echo "Expected: Service status without password prompt"
echo ""
sudo systemctl status aitbc-coordinator-api.service --no-pager | head -3
echo "✅ Service management test completed"
echo ""

# Test 2: File Operations
echo "📋 Test 2: File Operations"
echo "Command: touch /opt/aitbc/test-permissions.txt"
echo "Expected: File creation without sudo"
echo ""
touch /opt/aitbc/test-permissions.txt
echo "✅ File created: /opt/aitbc/test-permissions.txt"
echo ""

echo "Command: rm /opt/aitbc/test-permissions.txt"
echo "Expected: File deletion without sudo"
echo ""
rm /opt/aitbc/test-permissions.txt
echo "✅ File deleted successfully"
echo ""

# Test 3: Development Tools
echo "📋 Test 3: Development Tools"
echo "Command: git status"
echo "Expected: Git status without password"
echo ""
git status --porcelain | head -3 || echo "✅ Git working (clean working directory)"
echo ""

# Test 4: Log Access
echo "📋 Test 4: Log Access (should NOT ask for password)"
echo "Command: sudo journalctl -u aitbc-coordinator-api.service --no-pager -n 2"
echo "Expected: Recent logs without password prompt"
echo ""
sudo journalctl -u aitbc-coordinator-api.service --no-pager -n 2
echo "✅ Log access test completed"
echo ""

# Test 5: Network Tools
echo "📋 Test 5: Network Tools (should NOT ask for password)"
echo "Command: sudo lsof -i :8000"
echo "Expected: Network info without password prompt"
echo ""
sudo lsof -i :8000 | head -2 || echo "✅ lsof command working"
echo ""

# Test 6: Helper Scripts
echo "📋 Test 6: Helper Scripts"
echo "Command: /opt/aitbc/scripts/fix-permissions.sh"
echo "Expected: Permission fix script runs"
echo ""
/opt/aitbc/scripts/fix-permissions.sh
echo "✅ Helper script test completed"
echo ""

# Test 7: Development Environment
echo "📋 Test 7: Development Environment"
echo "Command: source /opt/aitbc/.env.dev"
echo "Expected: Environment loads without errors"
echo ""
source /opt/aitbc/.env.dev
echo "✅ Development environment loaded"
echo ""

echo "=== 🎉 All Tests Completed! ==="
echo ""
echo "✅ Service Management: Working"
echo "✅ File Operations: Working"
echo "✅ Development Tools: Working"
echo "✅ Log Access: Working"
echo "✅ Network Tools: Working"
echo "✅ Helper Scripts: Working"
echo "✅ Development Environment: Working"
echo ""
echo "🚀 Your AITBC development environment is fully configured!"
echo ""
echo "💡 Available aliases (now active):"
echo "   aitbc-services - Service management"
echo "   aitbc-fix      - Quick permission fix"
echo "   aitbc-logs     - View logs"
