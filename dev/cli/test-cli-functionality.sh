#!/bin/bash

# CLI Functionality Testing Script
echo "=== CLI Functionality Test ==="
echo "Date: $(date)"
echo ""

# Test basic CLI functionality
echo "1. Testing CLI Version:"
aitbc --version
echo ""

echo "2. Testing CLI Help:"
aitbc --help | head -5
echo ""

echo "3. Testing CLI Config:"
aitbc --config-file /home/oib/windsurf/aitbc/cli-dev/cli-test-config.yaml config-show
echo ""

echo "4. Testing CLI Environment:"
aitbc --config-file /home/oib/windsurf/aitbc/cli-dev/cli-test-config.yaml test environment
echo ""

echo "5. Testing CLI API:"
aitbc --config-file /home/oib/windsurf/aitbc/cli-dev/cli-test-config.yaml test api
echo ""

echo "6. Testing CLI Wallet:"
aitbc --config-file /home/oib/windsurf/aitbc/cli-dev/cli-test-config.yaml wallet list | head -5
echo ""

echo "7. Testing CLI Marketplace:"
aitbc --config-file /home/oib/windsurf/aitbc/cli-dev/cli-test-config.yaml marketplace --help | head -3
echo ""

echo "8. Testing CLI Blockchain:"
aitbc --config-file /home/oib/windsurf/aitbc/cli-dev/cli-test-config.yaml blockchain --help | head -3
echo ""

echo "=== CLI Test Complete ==="
