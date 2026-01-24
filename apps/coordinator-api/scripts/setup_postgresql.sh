#!/bin/bash

echo "=== PostgreSQL Setup for AITBC Coordinator API ==="
echo ""

# Create database and user
echo "Creating coordinator database..."
sudo -u postgres psql -c "CREATE DATABASE aitbc_coordinator;"
sudo -u postgres psql -c "CREATE USER aitbc_user WITH PASSWORD 'aitbc_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE aitbc_coordinator TO aitbc_user;"

# Grant schema permissions
sudo -u postgres psql -d aitbc_coordinator -c 'ALTER SCHEMA public OWNER TO aitbc_user;'
sudo -u postgres psql -d aitbc_coordinator -c 'GRANT CREATE ON SCHEMA public TO aitbc_user;'

# Test connection
echo "Testing connection..."
sudo -u postgres psql -c "\l" | grep aitbc_coordinator

echo ""
echo "✅ PostgreSQL setup complete for Coordinator API!"
echo ""
echo "Connection details:"
echo "  Database: aitbc_coordinator"
echo "  User: aitbc_user"
echo "  Host: localhost"
echo "  Port: 5432"
echo ""
echo "You can now run the migration script."
