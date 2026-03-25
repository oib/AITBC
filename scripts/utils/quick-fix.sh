#!/bin/bash
# Quick Permission Fix for AITBC Development

echo "🔧 Quick AITBC Permission Fix..."

# Fix ownership
sudo chown -R oib:aitbc /opt/aitbc

# Fix directory permissions
sudo find /opt/aitbc -type d -exec chmod 2775 {} \;

# Fix file permissions
sudo find /opt/aitbc -type f -exec chmod 664 {} \;

# Make scripts executable
sudo find /opt/aitbc -name "*.sh" -exec chmod +x {} \;
sudo find /opt/aitbc -name "*.py" -exec chmod +x {} \;

# Set SGID bit
sudo find /opt/aitbc -type d -exec chmod g+s {} \;

echo "✅ Permissions fixed!"
