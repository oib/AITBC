# AITBC Payment Architecture

## Overview

The AITBC platform uses a dual-currency system:
- **AITBC Tokens**: For job payments and platform operations
- **Bitcoin**: For purchasing AITBC tokens through the exchange

## Payment Flow

### 1. Job Payments (AITBC Tokens)
```
Client ──► Creates Job with AITBC Payment ──► Coordinator API
    │                                        │
    │                                        ▼
    │                                  Create Token Escrow
    │                                        │
    │                                        ▼
    │                                  Exchange API (Token)
    │                                        │
    ▼                                        ▼
Miner completes job ──► Release AITBC Escrow ──► Miner Wallet
```

### 2. Token Purchase (Bitcoin → AITBC)
```
Client ──► Bitcoin Payment ──► Exchange API
    │                           │
    │                           ▼
    │                     Process Bitcoin
    │                           │
    ▼                           ▼
Receive AITBC Tokens ◄─── Exchange Rate ◄─── 1 BTC = 100,000 AITBC
```

## Implementation Details

### Job Payment Structure
```json
{
    "payload": {...},
    "ttl_seconds": 900,
    "payment_amount": 100,      // AITBC tokens
    "payment_currency": "AITBC" // Always AITBC for jobs
}
```

### Payment Methods
- `aitbc_token`: Default for all job payments
- `bitcoin`: Only used for exchange purchases

### Escrow System
- **AITBC Token Escrow**: Managed by Exchange API
  - Endpoint: `/api/v1/token/escrow/create`
  - Timeout: 1 hour default
  - Release on job completion
  
- **Bitcoin Escrow**: Managed by Wallet Daemon
  - Endpoint: `/api/v1/escrow/create`
  - Only for token purchases

## API Endpoints

### Job Payment Endpoints
- `POST /v1/jobs` - Create job with AITBC payment
- `GET /v1/jobs/{id}/payment` - Get job payment status
- `POST /v1/payments/{id}/release` - Release AITBC payment
- `POST /v1/payments/{id}/refund` - Refund AITBC tokens

### Exchange Endpoints
- `POST /api/exchange/purchase` - Buy AITBC with BTC
- `GET /api/exchange/rate` - Get current rate (1 BTC = 100,000 AITBC)

## Database Schema

### Job Payments Table
```sql
CREATE TABLE job_payments (
    id VARCHAR(255) PRIMARY KEY,
    job_id VARCHAR(255) NOT NULL,
    amount DECIMAL(20, 8) NOT NULL,
    currency VARCHAR(10) DEFAULT 'AITBC',
    payment_method VARCHAR(20) DEFAULT 'aitbc_token',
    status VARCHAR(20) DEFAULT 'pending',
    ...
);
```

## Security Considerations

1. **Token Validation**: All AITBC payments require valid token balance
2. **Escrow Security**: Tokens held in smart contract escrow
3. **Rate Limiting**: Exchange purchases limited per user
4. **Audit Trail**: All transactions recorded on blockchain

## Example Flow

### 1. Client Creates Job
```bash
curl -X POST http://localhost:18000/v1/jobs \
  -H "X-Api-Key: ${CLIENT_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {
      "job_type": "ai_inference",
      "parameters": {"model": "gpt-4"}
    },
    "payment_amount": 100,
    "payment_currency": "AITBC"
  }'
```

### 2. Response with Payment
```json
{
    "job_id": "abc123",
    "state": "queued",
    "payment_id": "pay456",
    "payment_status": "escrowed",
    "payment_currency": "AITBC"
}
```

### 3. Job Completion & Payment Release
```bash
curl -X POST http://localhost:18000/v1/payments/pay456/release \
  -H "X-Api-Key: ${CLIENT_API_KEY}" \
  -d '{"job_id": "abc123", "reason": "Job completed"}'
```

## Benefits

1. **Stable Pricing**: AITBC tokens provide stable job pricing
2. **Fast Transactions**: Token payments faster than Bitcoin
3. **Gas Optimization**: Batch operations reduce costs
4. **Platform Control**: Token supply managed by platform

## Migration Path

1. **Phase 1**: Implement AITBC token payments for new jobs
2. **Phase 2**: Migrate existing Bitcoin job payments to tokens
3. **Phase 3**: Phase out Bitcoin for direct job payments
4. **Phase 4**: Bitcoin only used for token purchases

This architecture ensures efficient job payments while maintaining Bitcoin as the entry point for platform participation.
