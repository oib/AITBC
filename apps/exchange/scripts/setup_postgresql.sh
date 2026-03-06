#!/bin/bash

echo "=== PostgreSQL Setup for AITBC Exchange ==="
echo ""

# Install PostgreSQL if not already installed
if ! command -v psql &> /dev/null; then
    echo "Installing PostgreSQL..."
    sudo apt-get update
    sudo apt-get install -y postgresql postgresql-contrib
fi

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create database and user
echo "Creating database and user..."
sudo -u postgres psql -c "CREATE DATABASE aitbc_exchange;"
sudo -u postgres psql -c "CREATE USER aitbc_user WITH PASSWORD 'aitbc_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE aitbc_exchange TO aitbc_user;"

# Test connection
echo "Testing connection..."
sudo -u postgres psql -c "\l" | grep aitbc_exchange

echo ""
echo "✅ PostgreSQL setup complete!"
echo ""
echo "Connection details:"
echo "  Host: localhost"
echo "  Port: 5432"
echo "  Database: aitbc_exchange"
echo "  User: aitbc_user"
echo "  Password: aitbc_password"
echo ""
echo "You can now run the migration script."
