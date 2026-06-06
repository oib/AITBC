-- Setup database for Governance service

-- Create database
CREATE DATABASE aitbc_governance;

-- Create user
CREATE USER aitbc_governance WITH PASSWORD 'password';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE aitbc_governance TO aitbc_governance;

-- Connect to the database
\c aitbc_governance

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO aitbc_governance;

-- Exit
\q
