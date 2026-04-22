---
description: Atomic AITBC transaction processing with deterministic validation and tracking
title: aitbc-transaction-processor
version: 1.1
---

# AITBC Transaction Processor

## Purpose
Execute, validate, and track AITBC blockchain transactions with deterministic outcome prediction.

## Activation
Trigger when user requests transaction operations: sending tokens, checking status, or retrieving transaction details.

## Input
```json
{
  "operation": "send|status|details|history",
  "from_wallet": "string",
  "to_wallet": "string (for send)",
  "to_address": "string (for send)",
  "amount": "number (for send)",
  "fee": "number (optional for send)",
  "password": "string (for send)",
  "transaction_id": "string (for status/details)",
  "wallet_name": "string (for history)",
  "limit": "number (optional for history)"
}
```

## Output
```json
{
  "summary": "Transaction operation completed successfully",
  "operation": "send|status|details|history",
  "transaction_id": "string (for send/status/details)",
  "from_wallet": "string",
  "to_address": "string (for send)",
  "amount": "number",
  "fee": "number",
  "status": "pending|confirmed|failed",
  "block_height": "number (for confirmed)",
  "confirmations": "number (for confirmed)",
  "transactions": "array (for history)",
  "issues": [],
  "recommendations": [],
  "confidence": 1.0,
  "execution_time": "number",
  "validation_status": "success|partial|failed"
}
```

## Process

### 1. Analyze
- Validate transaction parameters
- Check wallet existence and balance
- Verify recipient address format
- Assess transaction feasibility

### 2. Plan
- Calculate appropriate fee (if not specified)
- Validate sufficient balance including fees
- Prepare transaction parameters
- Set confirmation monitoring strategy

### 3. Execute
- Execute AITBC CLI transaction command
- Capture transaction ID and initial status
- Monitor transaction confirmation
- Parse transaction details

### 4. Validate
- Verify transaction submission
- Check transaction status changes
- Validate amount and fee calculations
- Confirm recipient address accuracy

## Constraints
- **MUST NOT** exceed wallet balance
- **MUST NOT** process transactions without valid password
- **MUST NOT** allow zero or negative amounts
- **MUST** validate address format (ait-prefixed hex)
- **MUST** set minimum fee (10 AIT) if not specified
- **MUST** monitor transactions until confirmation or timeout (60 seconds)

## Environment Assumptions
- AITBC CLI accessible at `/opt/aitbc/aitbc-cli`
- Blockchain node operational and synced
- Network connectivity for transaction propagation
- Minimum fee: 10 AIT tokens
- Transaction confirmation time: 10-30 seconds

## Error Handling
- Insufficient balance → Return error with required amount
- Invalid address → Return address validation error
- Network issues → Retry transaction up to 3 times
- Timeout → Return pending status with monitoring recommendations

## Example Usage Prompt

```
Send 100 AIT from trading-wallet to ait141b3bae6eea3a74273ef3961861ee58e12b6d855 with password "secure123"
```

## Expected Output Example

```json
{
  "summary": "Transaction of 100 AIT sent successfully from trading-wallet",
  "operation": "send",
  "transaction_id": "tx_7f8a9b2c3d4e5f6",
  "from_wallet": "trading-wallet",
  "to_address": "ait141b3bae6eea3a74273ef3961861ee58e12b6d855",
  "amount": 100,
  "fee": 10,
  "status": "confirmed",
  "block_height": 12345,
  "confirmations": 1,
  "issues": [],
  "recommendations": ["Monitor transaction for additional confirmations", "Update wallet records for accounting"],
  "confidence": 1.0,
  "execution_time": 15.2,
  "validation_status": "success"
}
```

## Model Routing Suggestion

**Fast Model** (Claude Haiku, GPT-3.5-turbo)
- Transaction status checking
- Transaction details retrieval
- Transaction history listing

**Reasoning Model** (Claude Sonnet, GPT-4)
- Transaction sending with validation
- Error diagnosis and recovery
- Complex transaction analysis

## Performance Notes
- **Execution Time**: 2-5 seconds for status/details, 15-60 seconds for send operations
- **Memory Usage**: <100MB for transaction processing
- **Network Requirements**: Blockchain node connectivity for transaction propagation
- **Concurrency**: Safe for multiple simultaneous transactions from different wallets
- **Confirmation Monitoring**: Automatic status updates until confirmation or timeout
