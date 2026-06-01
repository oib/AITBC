-- Setup database for GPU service

-- Create database
CREATE DATABASE aitbc_gpu;

-- Create user
CREATE USER aitbc_gpu WITH PASSWORD 'password';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE aitbc_gpu TO aitbc_gpu;

-- Connect to the database
\c aitbc_gpu

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO aitbc_gpu;

-- Exit
\q
