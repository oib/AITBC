# Job Submission with Payment Failure

**Level**: Intermediate
**Prerequisites**: [Scenario 24 Fire-and-Forget Task Error Logging](./24_task_error_logging.md)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-08-19
**Version**: 1.1

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Job Submission with Payment Failure

---

## See Also

- **Previous Scenario**: [Scenario 24 Fire-and-Forget Task Error Logging](./24_task_error_logging.md)
- **Next Scenario**: [Scenario 26 GPU Marketplace N+1 Query Fix](./26_gpu_nplus1_query.md)
- **Feature Documentation**: [Coordinator API Reference](../apps/coordinator/coordinator-api.md)

---

## Scenario Overview

This scenario verifies that when a job submission includes a payment that fails, the job is still created with `payment_status="skipped"` and no orphaned payment records remain in the database. This covers the B12 fix: `session.rollback()` was added before setting `payment_status="skipped"` to prevent orphaned payment records from partially-successful `create_payment` calls.

### Use Case

A client submits a job with a payment amount and an invalid currency. The payment creation fails, but the job should still be queued. Without the B12 fix, a partially-created payment record would be orphaned in the database.

### What You'll Learn

- How to submit a job with a payment via the coordinator API
- How to verify that payment failures result in `payment_status="skipped"` (not job failure)
- How to check coordinator-api logs for the rollback warning message
- How to confirm no orphaned payment records exist

---

## Prerequisites

### Knowledge Required

- Familiarity with the coordinator API job submission flow
- Understanding of database transactions and rollback

### Tools Required

- `curl` (HTTP requests)
- `journalctl` (log inspection)
- Python 3.13 (for JWT token generation)

### Setup Required

- A running coordinator-api service on port 8203
- The JWT secret from `/etc/aitbc/aitbc-coordinator-api.env`

---

## Step-by-Step Workflow

### Step 1: Generate a JWT Token

```bash
JWT_SECRET=$(grep JWT_SECRET /etc/aitbc/aitbc-coordinator-api.env | cut -d= -f2)

cd /opt/aitbc && JWT_SECRET="$JWT_SECRET" PYTHONPATH=apps/coordinator-api/src ./venv/bin/python -c "
from coordinator_api.auth.jwt_auth import create_access_token
token = create_access_token('test-user-b12', 'client', {'wallet_address': '0x5e2D7C7A4F8E9B1C3d5A2e8F4c6b8a0D2e4f6A8C'})
print(token)
"
```

**Expected output:**

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXItYjEyIiw...
```

### Step 2: Submit a Job with Invalid Payment Currency

```bash
TOKEN="<token from step 1>"

curl -s -w "\nHTTP %{http_code}" -X POST http://localhost:8203/v1/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"payload":{"task":"test_b12","image":"hello"},"payment_amount":100,"payment_currency":"INVALID_CURRENCY"}'
```

**Expected output:**

```json
{"job_id":"cfe204e2ed3c4a2b8b0571b1ded74bc7","state":"QUEUED","assigned_miner_id":null,"requested_at":"2026-07-05T14:36:28.926270","expires_at":"2026-07-05T14:51:28.926270","error":null,"payment_id":null,"payment_status":"skipped"}
HTTP 201
```

Key observations:

- HTTP 201 (job created successfully)
- `payment_status: "skipped"` (payment failed, job proceeded without it)
- `payment_id: null` (no orphaned payment record)

### Step 3: Verify the Rollback Was Logged

```bash
journalctl -u aitbc-coordinator-api --since "1 min ago" --no-pager | grep -iE "Payment creation failed|proceeding without|rollback|skipped"
```

**Expected output:**

```
Jul 05 14:36:29 aitbc3 aitbc-coordinator-api[51036]: [WARNING] [app.contexts.infrastructure.routers.client] Payment creation failed for job cfe204e2ed3c4a2b8b0571b1ded74bc7, proceeding without payment: 1 validation error for JobPaymentCreate
```

### Step 4: Verify the Job Exists with payment_status=skipped

```bash
curl -s http://localhost:8203/v1/jobs/<job_id> -H "Authorization: Bearer $TOKEN"
```

**Expected output:**

```json
{"job_id":"cfe204e2ed3c4a2b8b0571b1ded74bc7","state":"COMPLETED","payment_id":null,"payment_status":"skipped"}
```

---

## Code Examples

### B12 Fix: Rollback Before Setting skipped

```python
# apps/coordinator-api/src/app/contexts/infrastructure/routers/client.py
@router.post("/jobs", response_model=JobView, status_code=201)
async def submit_job(req: JobCreate, request: Request, session: Session, user: ClientDep) -> JobView:
    service = JobService(session)
    job = service.create_job(user["sub"], req)
    if req.payment_amount and req.payment_amount > 0:
        try:
            payment_service = PaymentService(session)
            payment = await payment_service.create_payment(job.id, payment_create)
            job.payment_id = payment.id
            job.payment_status = payment.status
            session.commit()
        except Exception as e:
            # B12 fix: rollback partial payment changes before marking as skipped
            session.rollback()
            session.refresh(job)
            logger.warning("Payment creation failed for job %s, proceeding without payment: %s", job.id, e)
            job.payment_status = "skipped"
            session.commit()
            session.refresh(job)
    return service.to_view(job)
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Submit a job with a payment that fails and confirm the job is still created
- Verify that `payment_status` is set to `"skipped"` (not `"failed"` or missing)
- Confirm that no orphaned payment records exist (`payment_id: null`)
- Check that the rollback warning message appears in coordinator-api logs

---

## Validation

```bash
# Job should have payment_status=skipped and payment_id=null
curl -s http://localhost:8203/v1/jobs/<job_id> -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
job = json.load(sys.stdin)
assert job['payment_status'] == 'skipped', f'FAIL: {job[\"payment_status\"]}'
assert job['payment_id'] is None, f'FAIL: orphaned payment {job[\"payment_id\"]}'
print('PASS: B12 rollback verified')
"

# Log should contain the rollback warning
journalctl -u aitbc-coordinator-api --since "5 min ago" --no-pager | grep "Payment creation failed"
```

---

## Megaplan Status

This scenario has been refreshed to reflect the current codebase megaplan (hub `hub.aitbc` ↔ shop `aitbc3`).

- All examples use the current coordinator API path `/v1/jobs` and the authenticated coordinator (`Authorization: Bearer <JWT>`).
- The Agent SDK `ComputeConsumer` supports `auth_token` and `coordinator_url` in `create(...)`.
- The live two-node AI job flow has been validated end-to-end on the deployed hub and shop nodes.
- The megaplan test suite is green: **0 failures**, **9 skipped** live-deployment verification tests under `tests/verification/` (gated by `AITBC_ALLOW_PRODUCTION_WRITE_TESTS=1`), and **4 expected xfails** for removed BlockSearch/TransactionSearch model tests.


## Related Resources

- [Coordinator API Reference](../apps/coordinator/coordinator-api.md)
- [Next Scenario: GPU Marketplace N+1 Query Fix](./26_gpu_nplus1_query.md)

---

*Last updated: 2026-08-20*
*Version: 1.2*
