#!/bin/bash
# AITBC Miner Management Integration Script
# This script integrates the miner management functionality with the main AITBC CLI

echo "🤖 AITBC Miner Management Integration"
echo "=================================="

# Check if miner CLI exists
MINER_CLI="/opt/aitbc/cli/miner_cli.py"
if [ ! -f "$MINER_CLI" ]; then
    echo "❌ Error: Miner CLI not found at $MINER_CLI"
    exit 1
fi

# Create a symlink in the main CLI directory
MAIN_CLI_DIR="/opt/aitbc"
MINER_CMD="$MAIN_CLI_DIR/aitbc-miner"

if [ ! -L "$MINER_CMD" ]; then
    echo "🔗 Creating symlink: $MINER_CMD -> $MINER_CLI"
    ln -s "$MINER_CLI" "$MINER_CMD"
    chmod +x "$MINER_CMD"
fi

# Test the integration
echo "🧪 Testing miner CLI integration..."
echo ""

# Test help
echo "📋 Testing help command:"
$MINER_CMD --help | head -10
echo ""

# Test registration (with test data)
echo "📝 Testing registration command:"
$MINER_CMD register --miner-id integration-test --wallet ait113e1941cb60f3bb945ec9d412527b6048b73eb2d --gpu-memory 2048 --models qwen3:8b --pricing 0.45 --region integration-test 2>/dev/null | grep "Status:"
echo ""

echo "✅ Miner CLI integration completed!"
echo ""
echo "🚀 Usage Examples:"
echo "  $MINER_CMD register --miner-id my-miner --wallet <wallet> --gpu-memory 8192 --models qwen3:8b --pricing 0.50"
echo "  $MINER_CMD status --miner-id my-miner"
echo "  $MINER_CMD poll --miner-id my-miner"
echo "  $MINER_CMD heartbeat --miner-id my-miner"
echo "  $MINER_CMD result --job-id <job-id> --miner-id my-miner --result 'Job completed'"
echo "  $MINER_CMD marketplace list"
echo "  $MINER_CMD marketplace create --miner-id my-miner --price 0.75"
echo ""
echo "📚 All miner management commands are now available via: $MINER_CMD"
