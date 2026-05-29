# E2E Test Scenarios

**Version:** 1.0
**Date:** 2026-05-11
**Status:** Draft
**Purpose:** Define end-to-end test scenarios for AITBC platform

## Overview

This document defines the end-to-end test scenarios for the AITBC platform, covering complete user journeys from registration to completion.

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

### Current Limitations

1. **Mock Clients:** Most integration tests use mock clients rather than real services
2. **Service Dependencies:** Tests require running services (coordinator, blockchain, marketplace, wallet)
3. **No True E2E:** Tests don't span full user journeys from registration to completion
4. **Environment Setup:** No dedicated E2E test environment configuration
5. **Test Data:** No comprehensive test data fixtures for E2E scenarios

## Test Scenarios

### 1. User Registration and Wallet Creation
**Objective:** Verify complete user onboarding flow

**Steps:**
1. User registers via CLI
2. Wallet is created automatically
3. Private key is generated and stored securely
4. User receives wallet address
5. User can view wallet balance

**Success Criteria:**
- Registration completes without errors
- Wallet is created with valid address
- Private key is securely stored
- User can access wallet information

**Prerequisites:**
- Coordinator API running
- Wallet daemon running
- Blockchain node running

### 2. Job Submission and Processing
**Objective:** Verify complete job lifecycle

**Steps:**
1. User submits AI inference job via CLI
2. Job is queued in coordinator
3. Miner picks up job via polling
4. Miner processes job (GPU execution)
5. Miner submits result
6. User receives result
7. Payment is processed

**Success Criteria:**
- Job is successfully submitted
- Job transitions through states: QUEUED → ASSIGNED → PROCESSING → COMPLETED
- Result is returned to user
- Payment is transferred correctly
- Transaction is recorded on blockchain

**Prerequisites:**
- Coordinator API running
- GPU miner running
- Wallet daemon running
- Blockchain node running
- Marketplace service running

### 3. Payment and Receipt Generation
**Objective:** Verify payment flow and receipt generation

**Steps:**
1. Job is submitted with payment
2. Payment is escrowed in smart contract
3. Job completes successfully
4. Payment is released to miner
5. Receipt is generated
6. Receipt is stored on blockchain
7. User can retrieve receipt

**Success Criteria:**
- Payment is escrowed correctly
- Payment is released on job completion
- Receipt is generated with all required fields
- Receipt is stored on blockchain
- User can retrieve and verify receipt

**Prerequisites:**
- Coordinator API running
- Wallet daemon running
- Blockchain node running
- Smart contracts deployed

### 4. Miner Registration and Operation
**Objective:** Verify miner onboarding and operation

**Steps:**
1. Miner registers with coordinator
2. Miner provides GPU capabilities
3. Miner creates marketplace offer
4. Miner receives jobs
5. Miner processes jobs
6. Miner receives payments
7. Miner updates capabilities

**Success Criteria:**
- Miner registration succeeds
- Capabilities are recorded correctly
- Marketplace offer is created
- Jobs are assigned to miner
- Payments are received
- Capability updates succeed

**Prerequisites:**
- Coordinator API running
- GPU miner running
- Wallet daemon running
- Marketplace service running
- Blockchain node running

### 5. Agent Communication
**Objective:** Verify agent-to-agent communication

**Steps:**
1. Agent A registers with coordinator
2. Agent B registers with coordinator
3. Agent A sends message to Agent B
4. Agent B receives message
5. Agent B responds
6. Communication is encrypted
7. Message is logged on blockchain

**Success Criteria:**
- Agents register successfully
- Message is delivered
- Response is received
- Communication is encrypted
- Message is recorded on blockchain

**Prerequisites:**
- Coordinator API running
- Agent daemon running
- Blockchain node running
- Smart contracts deployed

### 6. Blockchain Transactions
**Objective:** Verify blockchain transaction processing

**Steps:**
1. User initiates transaction
2. Transaction is submitted to blockchain
3. Transaction is validated
4. Transaction is included in block
5. Block is propagated to network
6. Transaction is confirmed
7. Receipt is generated

**Success Criteria:**
- Transaction is submitted successfully
- Transaction is validated
- Transaction is included in block
- Block is propagated
- Transaction is confirmed
- Receipt is generated

**Prerequisites:**
- Blockchain node running (multiple nodes for network testing)
- Wallet daemon running
- Consensus mechanism operational

### 7. API Interactions
**Objective:** Verify API contract compliance

**Steps:**
1. Test all API endpoints
2. Verify request/response formats
3. Test authentication/authorization
4. Test error handling
5. Test rate limiting
6. Test pagination
7. Test filtering and sorting

**Success Criteria:**
- All endpoints respond correctly
- Request/response formats match API spec
- Authentication/authorization works correctly
- Errors are handled appropriately
- Rate limiting is enforced
- Pagination works correctly
- Filtering and sorting work correctly

**Prerequisites:**
- All API services running
- API documentation available
- Test users with different roles

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
