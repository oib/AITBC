-- Setup database for Market service

-- Create database
CREATE DATABASE aitbc_market;

-- Create user
CREATE USER aitbc_market WITH PASSWORD 'password';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE aitbc_market TO aitbc_market;

-- Connect to the database
\c aitbc_market

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO aitbc_market;

-- Exit
\q
