---
description: Atomic AITBC wallet management operations with deterministic outputs
title: aitbc-wallet-manager
version: 1.1
---

# AITBC Wallet Manager

## Purpose
Create, list, and manage AITBC blockchain wallets with deterministic validation.

## Activation
Trigger when user requests wallet operations: creation, listing, balance checking, or wallet information retrieval.

## Input
```json
{
  "operation": "create|list|balance|info",
  "wallet_name": "string (optional for create/list)",
  "password": "string (optional for create)",
  "node": "genesis|follower (optional, default: genesis)"
}
```

## Output
```json
{
  "summary": "Wallet operation completed successfully",
  "operation": "create|list|balance|info",
  "wallet_name": "string",
  "wallet_address": "string (for create/info)",
  "balance": "number (for balance/info)",
  "node": "genesis|follower",
  "issues": [],
  "recommendations": [],
  "confidence": 1.0,
  "execution_time": "number",
  "validation_status": "success|partial|failed"
}
```

## Process

### 1. Analyze
- Validate input parameters
- Check node connectivity
- Verify CLI accessibility
- Assess operation requirements

### 2. Plan
- Select appropriate CLI command
- Prepare execution parameters
- Define validation criteria
- Set error handling strategy

### 3. Execute
- Execute AITBC CLI command
- Capture output and errors
- Parse structured results
- Validate operation success

### 4. Validate
- Verify operation completion
- Check output consistency
- Validate wallet creation/listing
- Confirm balance accuracy

## Constraints
- **MUST NOT** perform transactions
- **MUST NOT** access private keys without explicit request
- **MUST NOT** exceed 30 seconds execution time
- **MUST** validate wallet name format (alphanumeric, hyphens, underscores only)
- **MUST** handle cross-node operations with proper SSH connectivity

## Environment Assumptions
- AITBC CLI accessible at `/opt/aitbc/aitbc-cli`
- Python venv activated for CLI operations
- SSH access to follower node (aitbc1) for cross-node operations
- Default wallet password: "123" for new wallets
- Blockchain node operational on specified node

## Error Handling
- CLI command failures → Return detailed error in issues array
- Network connectivity issues → Attempt fallback node
- Invalid wallet names → Return validation error
- SSH failures → Return cross-node operation error

## Example Usage Prompt

```
Create a new wallet named "trading-wallet" on genesis node with password "secure123"
```

## Expected Output Example

```json
{
  "summary": "Wallet 'trading-wallet' created successfully on genesis node",
  "operation": "create",
  "wallet_name": "trading-wallet",
  "wallet_address": "ait158ec7a0713f30ccfb1aac6bfbab71f36271c5871",
  "balance": 0,
  "node": "genesis",
  "issues": [],
  "recommendations": ["Fund wallet with initial AIT tokens for trading operations"],
  "confidence": 1.0,
  "execution_time": 2.3,
  "validation_status": "success"
}
```

## Model Routing Suggestion

**Fast Model** (Claude Haiku, GPT-3.5-turbo)
- Simple wallet listing operations
- Balance checking
- Basic wallet information retrieval

**Reasoning Model** (Claude Sonnet, GPT-4)
- Wallet creation with validation
- Cross-node wallet operations
- Error diagnosis and recovery

## Performance Notes
- **Execution Time**: 1-5 seconds for local operations, 3-10 seconds for cross-node
- **Memory Usage**: <50MB for wallet operations
- **Network Requirements**: Local CLI operations, SSH for cross-node
- **Concurrency**: Safe for multiple simultaneous wallet operations on different wallets
