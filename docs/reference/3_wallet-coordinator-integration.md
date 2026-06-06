# Wallet-Coordinator Integration Implementation

## Overview

This document describes the implementation of wallet-coordinator integration for job payments in the AITBC platform.

## Implemented Features

### ✅ 1. Payment Endpoints in Coordinator API

#### New Routes Added:
- `POST /v1/payments` - Create payment for a job
- `GET /v1/payments/{payment_id}` - Get payment details
- `GET /v1/jobs/{job_id}/payment` - Get payment for a specific job
- `POST /v1/payments/{payment_id}/release` - Release payment from escrow
- `POST /v1/payments/{payment_id}/refund` - Refund payment
- `GET /v1/payments/{payment_id}/receipt` - Get payment receipt

### ✅ 2. Escrow Service

#### Features:
- Automatic escrow creation for Bitcoin payments
- Timeout-based escrow expiration (default 1 hour)
- Integration with wallet daemon for escrow management
- Status tracking (pending → escrowed → released/refunded)

### ✅ 3. Wallet Daemon Integration

#### Integration Points:
- HTTP client communication with wallet daemon at `http://127.0.0.1:20000`
- Escrow creation via `/api/v1/escrow/create`
- Payment release via `/api/v1/escrow/release`
- Refunds via `/api/v1/refund`

### ✅ 4. Payment Status Tracking

#### Job Model Updates:
- Added `payment_id` field to track associated payment
- Added `payment_status` field for status visibility
- Relationship with JobPayment model

### ✅ 5. Refund Mechanism

#### Features:
- Automatic refund for failed/cancelled jobs
- Refund to specified address
- Transaction hash tracking for refunds

### ✅ 6. Payment Receipt Generation

#### Features:
- Detailed payment receipts with verification status
- Transaction hash inclusion
- Timestamp tracking for all payment events

### ✅ 7. Integration Test Updates

#### Test: `test_job_payment_flow`
- Creates job with payment amount
- Verifies payment creation
- Tests payment status tracking
- Attempts payment release (gracefully handles wallet daemon unavailability)

## Database Schema

### New Tables:

#### `job_payments`
- id (PK)
- job_id (indexed)
- amount (DECIMAL(20,8))
- currency
- status
- payment_method
- escrow_address
- refund_address
- transaction_hash
- refund_transaction_hash
- Timestamps (created, updated, escrowed, released, refunded, expires)

#### `payment_escrows`
- id (PK)
- payment_id (indexed)
- amount
- currency
- address
- Status flags (is_active, is_released, is_refunded)
- Timestamps

### Updated Tables:

#### `job`
- Added payment_id (FK to job_payments)
- Added payment_status (VARCHAR)

## API Examples

### Create Job with Payment
```json
POST /v1/jobs
{
    "payload": {
        "job_type": "ai_inference",
        "parameters": {"model": "gpt-4", "prompt": "Hello"}
    },
    "ttl_seconds": 900,
    "payment_amount": 0.001,
    "payment_currency": "BTC"
}
```

### Response with Payment Info
```json
{
    "job_id": "abc123",
    "state": "queued",
    "payment_id": "pay456",
    "payment_status": "escrowed",
    ...
}
```

### Release Payment
```json
POST /v1/payments/pay456/release
{
    "job_id": "abc123",
    "reason": "Job completed successfully"
}
```

## Files Created/Modified

### New Files:
- `apps/coordinator-api/src/app/schemas/payments.py` - Payment schemas
- `apps/coordinator-api/src/app/domain/payment.py` - Payment domain models
- `apps/coordinator-api/src/app/services/payments.py` - Payment service
- `apps/coordinator-api/src/app/routers/payments.py` - Payment endpoints
- `apps/coordinator-api/migrations/004_payments.sql` - Database migration

### Modified Files:
- `apps/coordinator-api/src/app/domain/job.py` - Added payment tracking
- `apps/coordinator-api/src/app/schemas.py` - Added payment fields to JobCreate/JobView
- `apps/coordinator-api/src/app/services/jobs.py` - Integrated payment creation
- `apps/coordinator-api/src/app/routers/client.py` - Added payment handling
- `apps/coordinator-api/src/app/main.py` - Added payments router
- `apps/coordinator-api/src/app/routers/__init__.py` - Exported payments router
- `tests/integration/test_full_workflow.py` - Updated payment test

## Next Steps

1. **Deploy Database Migration**
   ```sql
   -- Apply migration 004_payments.sql
   ```

2. **Start Wallet Daemon**
   ```bash
   # Ensure wallet daemon is running on port 20000
   ./scripts/wallet-daemon.sh start
   ```

3. **Test Payment Flow**
   ```bash
   # Run the updated integration test
   python -m pytest tests/integration/test_full_workflow.py::TestWalletToCoordinatorIntegration::test_job_payment_flow -v
   ```

4. **Configure Production**
   - Update wallet daemon URL in production
   - Set appropriate escrow timeouts
   - Configure payment thresholds

## Security Considerations

- All payment endpoints require API key authentication
- Payment amounts are validated as positive numbers
- Escrow addresses are generated securely by wallet daemon
- Refunds only go to specified refund addresses
- Transaction hashes provide audit trail

## Monitoring

Payment events should be monitored:
- Failed escrow creations
- Expired escrows
- Refund failures
- Payment status transitions

## Future Enhancements

1. **Multi-currency Support** - Add support for AITBC tokens
2. **Payment Routing** - Route payments through multiple providers
3. **Batch Payments** - Support batch release/refund operations
4. **Payment History** - Enhanced payment tracking and reporting
