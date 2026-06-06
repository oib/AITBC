-- Migration: 002_indexes
-- Description: Performance indexes for Coordinator API
-- Created: 2026-01-24

-- Jobs indexes
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_client_id ON jobs(client_id);
CREATE INDEX IF NOT EXISTS idx_jobs_miner_id ON jobs(miner_id);
CREATE INDEX IF NOT EXISTS idx_jobs_model ON jobs(model);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_pending ON jobs(status, priority DESC, created_at ASC) 
    WHERE status = 'pending';

-- Miners indexes
CREATE INDEX IF NOT EXISTS idx_miners_status ON miners(status);
CREATE INDEX IF NOT EXISTS idx_miners_capabilities ON miners USING GIN(capabilities);
CREATE INDEX IF NOT EXISTS idx_miners_last_heartbeat ON miners(last_heartbeat DESC);
CREATE INDEX IF NOT EXISTS idx_miners_available ON miners(status, score DESC) 
    WHERE status = 'available';

-- Receipts indexes
CREATE INDEX IF NOT EXISTS idx_receipts_job_id ON receipts(job_id);
CREATE INDEX IF NOT EXISTS idx_receipts_provider ON receipts(provider);
CREATE INDEX IF NOT EXISTS idx_receipts_client ON receipts(client);
CREATE INDEX IF NOT EXISTS idx_receipts_created_at ON receipts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_receipts_provider_created ON receipts(provider, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_receipts_client_created ON receipts(client, created_at DESC);

-- Blocks indexes
CREATE INDEX IF NOT EXISTS idx_blocks_height ON blocks(height DESC);
CREATE INDEX IF NOT EXISTS idx_blocks_timestamp ON blocks(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_blocks_proposer ON blocks(proposer);

-- Transactions indexes
CREATE INDEX IF NOT EXISTS idx_transactions_block_height ON transactions(block_height);
CREATE INDEX IF NOT EXISTS idx_transactions_sender ON transactions(sender);
CREATE INDEX IF NOT EXISTS idx_transactions_recipient ON transactions(recipient);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(tx_type);

-- API keys indexes
CREATE INDEX IF NOT EXISTS idx_api_keys_owner ON api_keys(owner);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active) WHERE is_active = TRUE;

-- Job history indexes
CREATE INDEX IF NOT EXISTS idx_job_history_job_id ON job_history(job_id);
CREATE INDEX IF NOT EXISTS idx_job_history_event_type ON job_history(event_type);
CREATE INDEX IF NOT EXISTS idx_job_history_created_at ON job_history(created_at DESC);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_jobs_explorer ON jobs(status, created_at DESC) 
    INCLUDE (job_id, model, miner_id);
CREATE INDEX IF NOT EXISTS idx_receipts_explorer ON receipts(created_at DESC) 
    INCLUDE (receipt_id, job_id, provider, client, price);

-- Full-text search index for job prompts (optional)
-- CREATE INDEX IF NOT EXISTS idx_jobs_prompt_fts ON jobs USING GIN(to_tsvector('english', prompt));

-- Analyze tables after index creation
ANALYZE jobs;
ANALYZE miners;
ANALYZE receipts;
ANALYZE blocks;
ANALYZE transactions;
