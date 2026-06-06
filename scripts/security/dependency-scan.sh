#!/bin/bash
# Dependency Security Scanning Script
# Scans Python dependencies for known vulnerabilities

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_DIR="$PROJECT_ROOT/venv"

echo "=== AITBC Dependency Security Scan ==="
echo "Project root: $PROJECT_ROOT"
echo "Venv: $VENV_DIR"
echo ""

# Check if venv exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Error: Virtual environment not found at $VENV_DIR"
    echo "Please run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# Install security scanning tools if not present
echo "Installing security scanning tools..."
pip install --quiet safety bandit 2>/dev/null || true

# Run safety scan for known vulnerabilities
echo ""
echo "=== Running Safety Scan (CVE Database) ==="
safety check --file "$PROJECT_ROOT/requirements.txt" || echo "Safety scan completed with warnings"

# Run bandit for security issues in code
echo ""
echo "=== Running Bandit Security Linter ==="
bandit -r "$PROJECT_ROOT/apps" -f screen -ll || echo "Bandit scan completed with warnings"

# Check for outdated packages
echo ""
echo "=== Checking for Outdated Packages ==="
pip list --outdated --format=columns || echo "Outdated package check completed"

echo ""
echo "=== Scan Complete ==="
echo "Review the output above for any security issues"
echo ""
echo "Recommendations:"
echo "1. Update packages with known vulnerabilities: pip install --upgrade <package>"
echo "2. Address bandit warnings in code"
echo "3. Keep dependencies updated regularly"
