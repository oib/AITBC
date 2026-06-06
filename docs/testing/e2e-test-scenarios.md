# E2E Test Scenarios

**Version:** 2.0
**Date:** 2026-06-04
**Status:** Updated for v0.4.x
**Purpose:** Define end-to-end test scenarios for AITBC platform

## Overview

This document defines the end-to-end test scenarios for the AITBC platform, covering complete user journeys from software offer creation to job execution with escrow and on-chain proof of work.

## Current State

### Existing Test Infrastructure

**Integration Tests Location:** `/opt/aitbc/tests/integration/`

**Existing Test Files:**
- `test_full_workflow.py` - Integration tests for job execution, payment flow, P2P sync, marketplace, security
- `test_agent_coordinator.py` - Agent coordinator integration tests (141KB)
- `test_agent_coordinator_api.py` - Agent coordinator API tests
- `test_blockchain_nodes.py` - Blockchain node integration tests
- `test_staking_lifecycle.py` - Staking lifecycle tests
- `test_working_integration.py` - Working integration tests
- `test_basic_integration.py` - Basic integration tests
- `test_blockchain_simple.py` - Simple blockchain tests
- `test_blockchain_final.py` - Final blockchain tests
- `test_integration_simple.py` - Simple integration tests

**Scenario Scripts Location:** `/opt/aitbc/scripts/workflow/` and `/opt/aitbc/dev/testing/tests/`

**Updated Scenario Scripts:**
- `24_marketplace_scenario.sh` - Software offer creation, execution, escrow (v0.4.x)
- `test_scenario_a.sh` - Software offer creation and execution (v0.4.x)
- `test_scenario_b.sh` - Software offer discovery and execution (v0.4.x)
- `test_scenario_c.sh` - Container service operations (v0.4.x)
- `test_scenario_d.sh` - Multi-node connectivity test (v0.4.x)

### Current Limitations

1. **Mock Clients:** Most integration tests use mock clients rather than real services
2. **Service Dependencies:** Tests require running services (blockchain, plugin registry, whisper, marketplace)
3. **No True E2E:** Tests don't span full user journeys from registration to completion
4. **Environment Setup:** No dedicated E2E test environment configuration
5. **Test Data:** No comprehensive test data fixtures for E2E scenarios

## Test Scenarios

### 1. Software Offer Creation and Registration
**Objective:** Verify software offer creation and plugin registry registration

**Steps:**
1. User creates software offer via CLI: `aitbc market software-offer ollama llama2 0.001`
2. Offer transaction is posted on-chain
3. Offer is automatically registered in plugin registry (port 8109)
4. User verifies offer in plugin registry: `GET /plugins/{offer_id}`
5. User retrieves offer details: `GET /plugins/{offer_id}/offer`
6. User lists all offers: `aitbc market list`

**Success Criteria:**
- Software offer is created with valid offer_id (format: sw_offer_YYYYMMDDHHMMSS_<8hex>)
- Offer transaction is posted on blockchain
- Offer appears in plugin registry
- Offer details are retrievable
- Offer appears in marketplace list

**Prerequisites:**
- Blockchain node running (port 8006)
- Plugin registry running (port 8109)
- CLI installed and configured

### 2. Ollama Inference with Escrow
**Objective:** Verify complete Ollama inference workflow with escrow

**Steps:**
1. User creates Ollama software offer
2. User runs inference: `aitbc market run <offer_id> <prompt>`
3. Escrow is locked with payment amount
4. Inference is executed (metered)
5. Result is returned to user
6. Job transaction is posted on-chain with job_id, offer_id, actual_cost
7. Escrow is released to provider
8. Transaction is recorded in blockchain

**Success Criteria:**
- Inference job is created with valid job_id (format: sw_job_YYYYMMDDHHMMSS_<8hex>)
- Escrow is locked correctly
- Inference completes successfully
- Result is returned to user
- Job transaction is posted on-chain
- Escrow is released
- Transaction is recorded in blockchain

**Prerequisites:**
- Blockchain node running
- Plugin registry running
- Ollama service running (port 11434)
- CLI installed and configured

### 3. Whisper Transcription with Proof of Work
**Objective:** Verify Whisper transcription workflow with on-chain proof of work

**Steps:**
1. User creates Whisper software offer
2. User submits audio file: `aitbc market transcribe <offer_id> <audio_file>`
3. Whisper service transcribes audio
4. Service returns result_hash (SHA256 of transcript)
5. Job transaction is posted on-chain with job_id, offer_id, result_hash, actual_duration, actual_cost
6. Escrow is released to provider
7. Full chain: offer → job (proof) → escrow release (payment)

**Success Criteria:**
- Transcription job is created
- Audio is transcribed successfully
- result_hash is computed and returned
- Job transaction includes proof of work (result_hash)
- Escrow is released
- Transaction is recorded in blockchain

**Prerequisites:**
- Blockchain node running
- Plugin registry running
- Whisper service running (port 8110)
- CLI installed and configured

### 4. Plugin Registry Operations
**Objective:** Verify plugin registry CRUD operations

**Steps:**
1. Create software offer (auto-registers in plugin registry)
2. Retrieve plugin by ID: `GET /plugins/{id}`
3. Retrieve plugin offer details: `GET /plugins/{id}/offer`
4. List all plugins: `GET /plugins`
5. Delete plugin: `DELETE /plugins/{id}`

**Success Criteria:**
- Plugin is registered automatically on offer creation
- Plugin retrieval works correctly
- Plugin offer details are accessible
- Plugin list returns all registered plugins
- Plugin deletion works correctly

**Prerequisites:**
- Plugin registry running (port 8109)
- JSON store at `/var/lib/aitbc/plugins.json`

### 5. Escrow Release with Job Transaction
**Objective:** Verify escrow release with job transaction hash tracking

**Steps:**
1. Software job is executed
2. Job transaction is posted on-chain with job_tx_hash
3. Escrow release is requested with job_tx_hash
4. Escrow release validates job transaction
5. Payment is released to provider
6. job_tx_hash is stored in database for audit trail

**Success Criteria:**
- Job transaction includes job_tx_hash
- Escrow release accepts job_tx_hash
- Payment is released correctly
- job_tx_hash is stored in database
- Audit trail is complete

**Prerequisites:**
- Blockchain node running
- Escrow service running
- Database for audit trail

### 6. Multi-Node P2P Communication
**Objective:** Verify P2P communication between blockchain nodes

**Steps:**
1. Start multiple blockchain nodes
2. Nodes connect via P2P network
3. Nodes exchange blocks
4. Nodes sync blockchain state
5. Handle invalid JSON connections gracefully

**Success Criteria:**
- Nodes connect successfully
- Blocks are propagated
- Blockchain state is synchronized
- Invalid connections are handled with proper logging

**Prerequisites:**
- Multiple blockchain nodes running
- P2P service running
- Network connectivity between nodes

### 7. Agent Coordinator Messaging
**Objective:** Verify agent-to-agent communication via coordinator

**Steps:**
1. Agent registers with coordinator
2. Agent sends message to another agent
3. Message is stored in Redis
4. Recipient retrieves message
5. Message is marked as read

**Success Criteria:**
- Agent registration succeeds
- Message is stored correctly
- Message is retrieved by recipient
- Read status is updated
- Redis connection is logged when unavailable

**Prerequisites:**
- Agent coordinator running (port 8080)
- Redis running
- Agent daemon running

## Risks and Mitigations

### Risks

1. **Service Dependencies:** Tests depend on multiple services
   - **Mitigation:** Use docker-compose for service orchestration, implement service health checks

2. **Test Data Management:** Managing test data across tests
   - **Mitigation:** Implement robust fixture system, use database transactions for rollback

3. **Test Execution Time:** E2E tests can be slow
   - **Mitigation:** Parallelize tests where possible, use test selection for targeted testing

4. **Environment Differences:** Test environment may not match production
   - **Mitigation:** Use production-like configuration, regular environment audits

5. **Test Flakiness:** E2E tests can be flaky due to timing issues
   - **Mitigation:** Implement proper waits and retries, use idempotent operations

## See Also

- [E2E Test Environment](e2e-test-environment.md) - Environment setup and data management
- [E2E Test Execution](e2e-test-execution.md) - Execution, reporting, and maintenance
- [Marketplace CLI Commands](../../cli/CLI_USAGE_GUIDE.md) - CLI command reference
