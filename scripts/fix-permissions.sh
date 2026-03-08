#!/bin/bash
# AITBC Permission Fix Script - No sudo required

echo "Fixing AITBC project permissions..."

# Fix ownership
sudo chown -R oib:aitbc /opt/aitbc

# Fix directory permissions
sudo find /opt/aitbc -type d -exec chmod 2775 {} \;

# Fix file permissions
sudo find /opt/aitbc -type f -exec chmod 664 {} \;

# Make scripts executable
sudo find /opt/aitbc -name "*.sh" -exec chmod +x {} \;
sudo find /opt/aitbc -name "*.py" -exec chmod +x {} \;

# Set SGID bit for directories
sudo find /opt/aitbc -type d -exec chmod g+s {} \;

echo "Permissions fixed!"
