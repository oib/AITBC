# Bridge RPC Input Validation

**Level**: Intermediate
**Prerequisites**: [Scenario 21 Service Startup & Connectivity](./21_service_startup_connectivity.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-07-05
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Bridge RPC Input Validation

---

## See Also

- **Previous Scenario**: [Scenario 21 Service Startup & Connectivity](./21_service_startup_connectivity.md)
- **Next Scenario**: [Scenario 23 Mempool Eviction Order](./23_mempool_eviction_order.md)
- **Feature Documentation**: [Bridge Security Audit](../releases/AUDIT.md)

---

## Scenario Overview

This scenario verifies that all bridge RPC endpoints reject invalid input with HTTP 422 (Pydantic validation errors) instead of accepting malformed requests or returning generic 400 errors. This covers the B13 fix: Pydantic request models were added to all 7 bridge RPC endpoints.

### Use Case

A node operator or external client sends invalid bridge requests (zero amounts, empty strings, missing required fields). The bridge RPC must reject these with structured 422 responses so clients can display meaningful error messages.

### What You'll Learn

- How to test bridge RPC input validation with `curl`
- What HTTP 422 Pydantic validation responses look like
- How to verify that all required fields are enforced (amount > 0, non-empty strings, required signatures)

---

## Prerequisites

### Knowledge Required

- Basic familiarity with the bridge RPC API
- Understanding of HTTP status codes (200, 400, 422)

### Tools Required

- `curl` (HTTP requests)

### Setup Required

- A running blockchain-node RPC service on port 8202

---

## Step-by-Step Workflow

### Step 1: Test Zero Amount Rejection on /rpc/bridge/lock

The `amount` field must be greater than 0:

```bash
curl -s -w "\nHTTP %{http_code}" -X POST http://localhost:8202/rpc/bridge/lock \
  -H "Content-Type: application/json" \
  -d '{"target_chain":"chain2","sender":"0xabc","recipient":"0xdef","amount":0,"signature":"0x123"}'
```

**Expected output:**

```
{"detail":[{"type":"greater_than","loc":["body","amount"],"msg":"Input should be greater than 0","input":0,"ctx":{"gt":0}}]}
HTTP 422
```

### Step 2: Test Empty String Rejection on /rpc/bridge/lock

The `target_chain` field must have at least 1 character:

```bash
curl -s -w "\nHTTP %{http_code}" -X POST http://localhost:8202/rpc/bridge/lock \
  -H "Content-Type: application/json" \
  -d '{"target_chain":"","sender":"0xabc","recipient":"0xdef","amount":10,"signature":"0x123"}'
```

**Expected output:**

```
{"detail":[{"type":"string_too_short","loc":["body","target_chain"],"msg":"String should have at least 1 character","input":"","ctx":{"min_length":1}}]}
HTTP 422
```

### Step 3: Test Missing Required Field on /rpc/bridge/lock

The `signature` field is required:

```bash
curl -s -w "\nHTTP %{http_code}" -X POST http://localhost:8202/rpc/bridge/lock \
  -H "Content-Type: application/json" \
  -d '{"target_chain":"chain2","sender":"0xabc","recipient":"0xdef","amount":10}'
```

**Expected output:**

```
{"detail":[{"type":"missing","loc":["body","signature"],"msg":"Field required","input":{"target_chain":"chain2","sender":"0xabc","recipient":"0xdef","amount":10}}]}
HTTP 422
```

### Step 4: Test Empty transfer_id on /rpc/bridge/confirm

```bash
curl -s -w "\nHTTP %{http_code}" -X POST http://localhost:8202/rpc/bridge/confirm \
  -H "Content-Type: application/json" \
  -d '{"transfer_id":"","proof":"test","signature":"0x123"}'
```

**Expected output:**

```
{"detail":[{"type":"string_too_short","loc":["body","transfer_id"],"msg":"String should have at least 1 character","input":"","ctx":{"min_length":1}}]}
HTTP 422
```

### Step 5: Test Missing proof on /rpc/bridge/confirm

```bash
curl -s -w "\nHTTP %{http_code}" -X POST http://localhost:8202/rpc/bridge/confirm \
  -H "Content-Type: application/json" \
  -d '{"transfer_id":"tx1","signature":"0x123"}'
```

**Expected output:**

```
{"detail":[{"type":"missing","loc":["body","proof"],"msg":"Field required","input":{"transfer_id":"tx1","signature":"0x123"}}]}
HTTP 422
```

### Step 6: Verify Valid Requests Still Work

```bash
curl -s http://localhost:8202/rpc/bridge/health
```

**Expected output:**

```json
{"success":true,"status":"healthy","bridge_initialized":true,...}
```

---

## Code Examples

### Pydantic Request Models (B13)

The bridge router now uses Pydantic models for all endpoints:

```python
# apps/blockchain-node/src/aitbc_chain/rpc/routers/bridge.py
class BridgeLockRequest(BaseModel):
    target_chain: str = Field(..., min_length=1, description="Target chain ID")
    sender: str = Field(..., min_length=1, description="Sender address")
    recipient: str = Field(..., min_length=1, description="Recipient address")
    amount: int = Field(..., gt=0, description="Amount to bridge (positive integer)")
    signature: str = Field(..., min_length=1, description="Sender signature authorizing the lock")

@router.post("/lock")
async def bridge_lock_route(request: Request, lock_data: BridgeLockRequest) -> dict[str, Any]:
    return await bridge_lock(request, lock_data.model_dump(exclude_none=True))
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Confirm that all bridge RPC endpoints reject invalid input with HTTP 422
- Verify that Pydantic validation errors include field location, error type, and message
- Confirm that valid requests still succeed (no false positives)

---

## Validation

```bash
# All 5 validation tests should return 422
for test in "zero_amount" "empty_chain" "missing_sig" "empty_txid" "missing_proof"; do
  echo "Testing $test..."
done

# Valid health check should return 200
curl -sf http://localhost:8202/rpc/bridge/health > /dev/null && echo "Bridge healthy"
```

---

## Related Resources

- [Bridge Security Audit](../releases/AUDIT.md)
- [Next Scenario: Mempool Eviction Order](./23_mempool_eviction_order.md)

---

*Last updated: 2026-07-05*
*Version: 1.0*
