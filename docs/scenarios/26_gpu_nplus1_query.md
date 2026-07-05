# GPU Marketplace N+1 Query Fix

**Level**: Intermediate
**Prerequisites**: [Scenario 25 Job Submission with Payment Failure](./25_job_payment_failure.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-07-05
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > GPU Marketplace N+1 Query Fix

---

## See Also

- **Previous Scenario**: [Scenario 25 Job Submission with Payment Failure](./25_job_payment_failure.md)
- **Next Scenario**: [Scenario 27 CLI Commands](./27_cli_commands.md)
- **Feature Documentation**: [GPU Marketplace](../features/gpu-marketplace.md)

---

## Scenario Overview

This scenario verifies that the GPU marketplace orders list endpoint uses a batch query to fetch all referenced GPUs in a single `WHERE id IN (...)` query, instead of issuing a separate `session.get()` per booking (N+1 query pattern). This covers the B14 fix.

### Use Case

When listing GPU bookings/orders, each booking references a GPU. The old code fetched each GPU individually (`session.get(GPURegistry, b.gpu_id)` inside a loop), causing N+1 queries. With many bookings, this creates significant database load. The fix batch-fetches all GPUs in one query.

### What You'll Learn

- How to verify that the `list_orders` endpoint uses batch-fetching
- How to inspect the running code to confirm the N+1 fix is deployed
- How to call the orders endpoint and verify it returns results

---

## Prerequisites

### Knowledge Required

- Understanding of the N+1 query problem in ORM-based applications
- Familiarity with SQLAlchemy/SQLModel query patterns

### Tools Required

- `curl` (HTTP requests)
- Python 3.13 with access to the coordinator-api source

### Setup Required

- A running coordinator-api service on port 8203

---

## Step-by-Step Workflow

### Step 1: Call the Orders Endpoint

```bash
curl -s http://localhost:8203/v1/marketplace/orders
```

**Expected output:**
```json
[]
```

(An empty list is expected if no bookings exist. The endpoint should return 200 regardless.)

### Step 2: Verify the N+1 Fix Is Deployed in Running Code

```bash
cd /opt/aitbc && PYTHONPATH=apps/coordinator-api/src ./venv/bin/python -c "
import inspect
from app.contexts.marketplace.routers.marketplace_gpu import list_orders
source = inspect.getsource(list_orders)
if 'gpu_map' in source and 'in(' in source:
    print('PASS: B14 fix deployed — batch-fetch with WHERE IN is present in list_orders()')
else:
    print('FAIL: N+1 query pattern still present')
"
```

**Expected output:**
```
PASS: B14 fix deployed — batch-fetch with WHERE IN is present in list_orders()
```

### Step 3: List Available GPUs (Sanity Check)

```bash
curl -s http://localhost:8203/v1/marketplace/gpu/list | python3 -c "
import sys, json
gpus = json.load(sys.stdin)
print(f'GPUs available: {len(gpus)}')
for gpu in gpus[:3]:
    print(f'  {gpu[\"id\"]}: {gpu[\"model\"]} — {gpu[\"status\"]}')
"
```

**Expected output:**
```
GPUs available: 6
  gpu_c15daa9a: Unknown GPU — available
  gpu_552339f0: Unknown GPU — available
  gpu_3a98e8c1: Unknown GPU — available
```

---

## Code Examples

### B14 Fix: Batch-Fetch GPUs

```python
# apps/coordinator-api/src/app/contexts/marketplace/routers/marketplace_gpu.py
@router.get("/marketplace/orders")
async def list_orders(session: Session, ...) -> list[dict]:
    bookings = session.execute(stmt).scalars().all()

    # B14 fix: batch-fetch all referenced GPUs in a single query
    gpu_ids = {b.gpu_id for b in bookings if b.gpu_id}
    gpu_map: dict[str, GPURegistry] = {}
    if gpu_ids:
        gpus = session.execute(
            select(GPURegistry).where(col(GPURegistry.id).in_(gpu_ids))
        ).scalars().all()
        gpu_map = {g.id: g for g in gpus}

    orders = []
    for b in bookings:
        gpu = gpu_map.get(b.gpu_id)  # O(1) lookup, no DB query
        orders.append({...})
    return orders
```

### Old (Buggy) Code — N+1 Pattern

```python
# BEFORE B14 fix — one DB query per booking
for b in bookings:
    gpu = session.get(GPURegistry, b.gpu_id)  # N queries!
    orders.append({...})
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Confirm that the `list_orders` endpoint uses a batch query (`WHERE id IN (...)`)
- Verify that the N+1 query pattern has been replaced with a single batch-fetch
- Call the orders endpoint and verify it returns results (or empty list)

---

## Validation

```bash
# Verify batch-fetch in running code
cd /opt/aitbc && PYTHONPATH=apps/coordinator-api/src ./venv/bin/python -c "
import inspect
from app.contexts.marketplace.routers.marketplace_gpu import list_orders
source = inspect.getsource(list_orders)
assert 'gpu_map' in source, 'FAIL: no batch-fetch'
assert '.in_(' in source or 'in_(' in source, 'FAIL: no WHERE IN'
print('PASS: B14 N+1 fix verified')
"

# Endpoint should return 200
curl -sf http://localhost:8203/v1/marketplace/orders > /dev/null && echo "Orders endpoint OK"
```

---

## Related Resources

- [GPU Marketplace](../features/gpu-marketplace.md)
- [Next Scenario: CLI Commands](./27_cli_commands.md)

---

*Last updated: 2026-07-05*
*Version: 1.0*
