#!/bin/bash

echo "=== PostgreSQL Setup for AITBC Wallet Daemon ==="
echo ""

# Create database and user
echo "Creating wallet database..."
sudo -u postgres psql -c "CREATE DATABASE aitbc_wallet;"
sudo -u postgres psql -c "CREATE USER aitbc_user WITH PASSWORD 'aitbc_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE aitbc_wallet TO aitbc_user;"

# Grant schema permissions
sudo -u postgres psql -d aitbc_wallet -c 'ALTER SCHEMA public OWNER TO aitbc_user;'
sudo -u postgres psql -d aitbc_wallet -c 'GRANT CREATE ON SCHEMA public TO aitbc_user;'

# Test connection
echo "Testing connection..."
sudo -u postgres psql -c "\l" | grep aitbc_wallet

echo ""
echo "✅ PostgreSQL setup complete for Wallet Daemon!"
echo ""
echo "Connection details:"
echo "  Database: aitbc_wallet"
echo "  User: aitbc_user"
echo "  Host: localhost"
echo "  Port: 5432"
echo ""
echo "You can now run the migration script."
