#!/usr/bin/env bash
# Security analysis script for AITBC smart contracts
# Runs Slither (static analysis) and Mythril (symbolic execution)
#
# Prerequisites:
#   pip install slither-analyzer mythril
#   npm install -g solc
#
# Usage:
#   ./scripts/security-analysis.sh [--slither-only | --mythril-only]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTRACTS_DIR="$(dirname "$SCRIPT_DIR")"
REPORT_DIR="$CONTRACTS_DIR/reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$REPORT_DIR"

echo "=== AITBC Smart Contract Security Analysis ==="
echo "Contracts directory: $CONTRACTS_DIR"
echo "Report directory: $REPORT_DIR"
echo ""

RUN_SLITHER=true
RUN_MYTHRIL=true

if [[ "${1:-}" == "--slither-only" ]]; then
    RUN_MYTHRIL=false
elif [[ "${1:-}" == "--mythril-only" ]]; then
    RUN_SLITHER=false
fi

# --- Slither Analysis ---
if $RUN_SLITHER; then
    echo "--- Running Slither Static Analysis ---"
    SLITHER_REPORT="$REPORT_DIR/slither_${TIMESTAMP}.json"
    SLITHER_TEXT="$REPORT_DIR/slither_${TIMESTAMP}.txt"

    if command -v slither &>/dev/null; then
        echo "Analyzing ZKReceiptVerifier.sol..."
        slither "$CONTRACTS_DIR/ZKReceiptVerifier.sol" \
            --json "$SLITHER_REPORT" \
            --checklist \
            --exclude-dependencies \
            2>&1 | tee "$SLITHER_TEXT" || true

        echo ""
        echo "Slither report saved to: $SLITHER_REPORT"
        echo "Slither text output: $SLITHER_TEXT"

        # Summary
        if [[ -f "$SLITHER_REPORT" ]]; then
            HIGH=$(grep -c '"impact": "High"' "$SLITHER_REPORT" 2>/dev/null || echo "0")
            MEDIUM=$(grep -c '"impact": "Medium"' "$SLITHER_REPORT" 2>/dev/null || echo "0")
            LOW=$(grep -c '"impact": "Low"' "$SLITHER_REPORT" 2>/dev/null || echo "0")
            echo ""
            echo "Slither Summary: High=$HIGH Medium=$MEDIUM Low=$LOW"
        fi
    else
        echo "WARNING: slither not installed. Install with: pip install slither-analyzer"
    fi
    echo ""
fi

# --- Mythril Analysis ---
if $RUN_MYTHRIL; then
    echo "--- Running Mythril Symbolic Execution ---"
    MYTHRIL_REPORT="$REPORT_DIR/mythril_${TIMESTAMP}.json"
    MYTHRIL_TEXT="$REPORT_DIR/mythril_${TIMESTAMP}.txt"

    if command -v myth &>/dev/null; then
        echo "Analyzing ZKReceiptVerifier.sol..."
        myth analyze "$CONTRACTS_DIR/ZKReceiptVerifier.sol" \
            --solv 0.8.19 \
            --execution-timeout 300 \
            --max-depth 22 \
            -o json \
            2>&1 > "$MYTHRIL_REPORT" || true

        myth analyze "$CONTRACTS_DIR/ZKReceiptVerifier.sol" \
            --solv 0.8.19 \
            --execution-timeout 300 \
            --max-depth 22 \
            -o text \
            2>&1 | tee "$MYTHRIL_TEXT" || true

        echo ""
        echo "Mythril report saved to: $MYTHRIL_REPORT"
        echo "Mythril text output: $MYTHRIL_TEXT"

        # Summary
        if [[ -f "$MYTHRIL_REPORT" ]]; then
            ISSUES=$(grep -c '"swcID"' "$MYTHRIL_REPORT" 2>/dev/null || echo "0")
            echo ""
            echo "Mythril Summary: $ISSUES issues found"
        fi
    else
        echo "WARNING: mythril not installed. Install with: pip install mythril"
    fi
    echo ""
fi

echo "=== Analysis Complete ==="
echo "Reports saved in: $REPORT_DIR"
