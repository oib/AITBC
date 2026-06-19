#!/bin/bash
# Update all AITBC systemd service files to use unified aitbc user
# This script should be run after create_aitbc_user.sh

set -e

echo "Updating AITBC service files to use unified aitbc user..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root"
    exit 1
fi

# Check if aitbc user exists
if ! id aitbc > /dev/null 2>&1; then
    echo "Error: aitbc user does not exist. Run create_aitbc_user.sh first."
    exit 1
fi

# Directory containing service files
SERVICE_DIR="/opt/aitbc/apps"

# Find all .service files
SERVICE_FILES=$(find "$SERVICE_DIR" -name "*.service")

if [ -z "$SERVICE_FILES" ]; then
    echo "No service files found in $SERVICE_DIR"
    exit 1
fi

echo "Found $(echo "$SERVICE_FILES" | wc -l) service files"
echo ""

# Track changes
CHANGES=0
SKIPPED=0

for service_file in $SERVICE_FILES; do
    echo "Processing $service_file"

    # Check if service file has User directive
    if grep -q "^User=" "$service_file"; then
        current_user=$(grep "^User=" "$service_file" | head -1 | cut -d= -f2)

        # Skip if already using aitbc user
        if [ "$current_user" = "aitbc" ]; then
            echo "  Already using aitbc user, skipping"
            SKIPPED=$((SKIPPED + 1))
            continue
        fi

        # Update User directive
        sed -i 's/^User=.*/User=aitbc/' "$service_file"

        # Update Group directive to aitbc
        if grep -q "^Group=" "$service_file"; then
            sed -i 's/^Group=.*/Group=aitbc/' "$service_file"
        else
            # Add Group directive if it doesn't exist
            sed -i '/^User=/a Group=aitbc' "$service_file"
        fi

        echo "  Updated from User=$current_user to User=aitbc"
        CHANGES=$((CHANGES + 1))
    else
        echo "  No User directive found, adding User=aitbc and Group=aitbc"
        # Add User and Group directives after [Service] section
        sed -i '/^\[Service\]/a User=aitbc\nGroup=aitbc' "$service_file"
        CHANGES=$((CHANGES + 1))
    fi
done

echo ""
echo "Summary:"
echo "  Updated: $CHANGES service files"
echo "  Skipped: $SKIPPED service files (already using aitbc)"
echo ""
echo "Next steps:"
echo "1. Reload systemd: systemctl daemon-reload"
echo "2. Restart services: systemctl restart aitbc-*"
echo "3. Verify services are running: systemctl status aitbc-*"
