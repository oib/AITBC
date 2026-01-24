-- Migration: 001_initial_schema
-- Description: Initial database schema for Coordinator API
-- Created: 2026-01-24

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Jobs table
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id VARCHAR(64) UNIQUE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    prompt TEXT NOT NULL,
    model VARCHAR(100) NOT NULL DEFAULT 'llama3.2',
    params JSONB DEFAULT '{}',
    result TEXT,
    error TEXT,
    client_id VARCHAR(100),
    miner_id VARCHAR(100),
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    deadline TIMESTAMP WITH TIME ZONE,
    
    CONSTRAINT valid_status CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled'))
);

-- Miners table
CREATE TABLE IF NOT EXISTS miners (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    miner_id VARCHAR(100) UNIQUE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'offline',
    capabilities TEXT[] DEFAULT '{}',
    gpu_info JSONB DEFAULT '{}',
    endpoint VARCHAR(255),
    max_concurrent_jobs INTEGER DEFAULT 1,
    current_jobs INTEGER DEFAULT 0,
    jobs_completed INTEGER DEFAULT 0,
    jobs_failed INTEGER DEFAULT 0,
    score DECIMAL(5,2) DEFAULT 100.00,
    uptime_percent DECIMAL(5,2) DEFAULT 100.00,
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT valid_miner_status CHECK (status IN ('available', 'busy', 'maintenance', 'offline'))
);

-- Receipts table
CREATE TABLE IF NOT EXISTS receipts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    receipt_id VARCHAR(64) UNIQUE NOT NULL,
    job_id VARCHAR(64) NOT NULL REFERENCES jobs(job_id),
    provider VARCHAR(100) NOT NULL,
    client VARCHAR(100) NOT NULL,
    units DECIMAL(10,4) NOT NULL,
    unit_type VARCHAR(50) DEFAULT 'gpu_seconds',
    price DECIMAL(10,4),
    model VARCHAR(100),
    started_at BIGINT NOT NULL,
    completed_at BIGINT NOT NULL,
    result_hash VARCHAR(128),
    signature JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Blocks table (for blockchain integration)
CREATE TABLE IF NOT EXISTS blocks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    height BIGINT UNIQUE NOT NULL,
    hash VARCHAR(128) UNIQUE NOT NULL,
    parent_hash VARCHAR(128),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    proposer VARCHAR(100),
    transaction_count INTEGER DEFAULT 0,
    receipt_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Transactions table
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tx_hash VARCHAR(128) UNIQUE NOT NULL,
    block_height BIGINT REFERENCES blocks(height),
    tx_type VARCHAR(50) NOT NULL,
    sender VARCHAR(100),
    recipient VARCHAR(100),
    amount DECIMAL(20,8),
    fee DECIMAL(20,8),
    data JSONB,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    confirmed_at TIMESTAMP WITH TIME ZONE
);

-- API keys table
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key_hash VARCHAR(128) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    owner VARCHAR(100) NOT NULL,
    scopes TEXT[] DEFAULT '{}',
    rate_limit INTEGER DEFAULT 100,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE
);

-- Job history table (for analytics)
CREATE TABLE IF NOT EXISTS job_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Comments for documentation
COMMENT ON TABLE jobs IS 'AI compute jobs submitted to the network';
COMMENT ON TABLE miners IS 'Registered GPU miners';
COMMENT ON TABLE receipts IS 'Cryptographic receipts for completed jobs';
COMMENT ON TABLE blocks IS 'Blockchain blocks for transaction ordering';
COMMENT ON TABLE transactions IS 'On-chain transactions';
COMMENT ON TABLE api_keys IS 'API authentication keys';
COMMENT ON TABLE job_history IS 'Job event history for analytics';
