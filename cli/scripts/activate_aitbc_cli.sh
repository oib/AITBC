#!/bin/bash
# AITBC CLI activation script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/venv/bin/activate"
echo "AITBC CLI environment activated. Use 'aitbc --help' to get started."
