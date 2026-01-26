-- Migration: Add payment support
-- Date: 2026-01-26

-- Add payment tracking to jobs table
ALTER TABLE job 
ADD COLUMN payment_id VARCHAR(255) REFERENCES job_payments(id),
ADD COLUMN payment_status VARCHAR(20);

-- Create job_payments table
CREATE TABLE IF NOT EXISTS job_payments (
    id VARCHAR(255) PRIMARY KEY,
    job_id VARCHAR(255) NOT NULL,
    amount DECIMAL(20, 8) NOT NULL,
    currency VARCHAR(10) DEFAULT 'AITBC',
    status VARCHAR(20) DEFAULT 'pending',
    payment_method VARCHAR(20) DEFAULT 'aitbc_token',
    escrow_address VARCHAR(100),
    refund_address VARCHAR(100),
    transaction_hash VARCHAR(100),
    refund_transaction_hash VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    escrowed_at TIMESTAMP,
    released_at TIMESTAMP,
    refunded_at TIMESTAMP,
    expires_at TIMESTAMP,
    metadata JSON
);

-- Create payment_escrows table
CREATE TABLE IF NOT EXISTS payment_escrows (
    id VARCHAR(255) PRIMARY KEY,
    payment_id VARCHAR(255) NOT NULL,
    amount DECIMAL(20, 8) NOT NULL,
    currency VARCHAR(10) DEFAULT 'AITBC',
    address VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_released BOOLEAN DEFAULT FALSE,
    is_refunded BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    released_at TIMESTAMP,
    refunded_at TIMESTAMP,
    expires_at TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_job_payments_job_id ON job_payments(job_id);
CREATE INDEX IF NOT EXISTS idx_job_payments_status ON job_payments(status);
CREATE INDEX IF NOT EXISTS idx_job_payments_created_at ON job_payments(created_at);
CREATE INDEX IF NOT EXISTS idx_payment_escrows_payment_id ON payment_escrows(payment_id);
CREATE INDEX IF NOT EXISTS idx_payment_escrows_address ON payment_escrows(address);

-- Add index for job payment_id
CREATE INDEX IF NOT EXISTS idx_job_payment_id ON job(payment_id);
