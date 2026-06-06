-- Setup database for Marketplace service

-- Create database
CREATE DATABASE aitbc_marketplace;

-- Create user
CREATE USER aitbc_marketplace WITH PASSWORD 'password';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE aitbc_marketplace TO aitbc_marketplace;

-- Connect to the database
\c aitbc_marketplace

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO aitbc_marketplace;

-- Exit
\q
