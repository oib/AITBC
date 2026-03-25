#!/bin/bash

# Debug script to identify malformed service names

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_status "Debugging AITBC service names..."

# Show raw systemctl output
print_status "Raw systemctl output for AITBC services:"
systemctl list-units --all | grep "aitbc-" | cat -A

echo ""

# Show each field separately
print_status "Analyzing service names field by field:"
systemctl list-units --all | grep "aitbc-" | while read -r line; do
    echo "Raw line: '$line'"
    
    # Extract each field
    unit=$(echo "$line" | awk '{print $1}')
    load=$(echo "$line" | awk '{print $2}')
    active=$(echo "$line" | awk '{print $3}')
    sub=$(echo "$line" | awk '{print $4}')
    description=$(echo "$line" | cut -d' ' -f5-)
    
    echo "  Unit: '$unit'"
    echo "  Load: '$load'"
    echo "  Active: '$active'"
    echo "  Sub: '$sub'"
    echo "  Description: '$description'"
    
    # Check if unit name is valid
    if [[ "$unit" =~ [^a-zA-Z0-9\-\._] ]]; then
        print_error "  ❌ Invalid characters in unit name!"
        echo "  ❌ Hex representation: $(echo -n "$unit" | od -c)"
    else
        print_success "  ✅ Valid unit name"
    fi
    
    echo ""
done

# Check for any hidden characters
print_status "Checking for hidden characters in service names:"
systemctl list-units --all | grep "aitbc-" | awk '{print $2}' | grep "\.service$" | while read -r service; do
    echo "Service: '$service'"
    echo "Length: ${#service}"
    echo "Hex dump:"
    echo -n "$service" | od -c
    echo ""
done

# Show systemctl list-unit-files output
print_status "Checking systemctl list-unit-files:"
systemctl list-unit-files | grep "aitbc-" | cat -A

# Check service files on disk
print_status "Checking service files in /etc/systemd/system/:"
if [ -d "/etc/systemd/system" ]; then
    find /etc/systemd/system/ -name "*aitbc*" -type f | while read -r file; do
        echo "Found: $file"
        basename "$file"
        echo "Hex: $(basename "$file" | od -c)"
        echo ""
    done
fi

# Check service files in user directory
print_status "Checking service files in user directory:"
if [ -d "$HOME/.config/systemd/user" ]; then
    find "$HOME/.config/systemd/user" -name "*aitbc*" -type f 2>/dev/null | while read -r file; do
        echo "Found: $file"
        basename "$file"
        echo "Hex: $(basename "$file" | od -c)"
        echo ""
    done
fi

# Check for any encoding issues
print_status "Checking locale and encoding:"
echo "Current locale: $LANG"
echo "System encoding: $(locale charmap)"
echo ""

# Try to reload systemd daemon
print_status "Reloading systemd daemon to clear any cached issues:"
sudo systemctl daemon-reload
echo "Daemon reload completed"

echo ""
print_status "Debug complete. Review the output above to identify the source of the malformed service name."
