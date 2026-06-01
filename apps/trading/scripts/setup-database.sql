-- Setup database for Trading service

-- Create database
CREATE DATABASE aitbc_trading;

-- Create user
CREATE USER aitbc_trading WITH PASSWORD 'password';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE aitbc_trading TO aitbc_trading;

-- Connect to the database
\c aitbc_trading

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO aitbc_trading;

-- Exit
\q
