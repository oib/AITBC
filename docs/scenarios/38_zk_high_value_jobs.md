# Scenario 38: ZK Proofs for High-Value Jobs

**Level**: Intermediate  
**Prerequisites**: Scenario 07 AI Job Submission, Scenario 37 Performance Bonds  
**Estimated Time**: 15 minutes  
**Last Updated**: 2026-08-21  
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > ZK High-Value Jobs

---

## See Also

- **Previous Scenario**: [Scenario 37 On-Chain Performance Bonds](./37_performance_bonds.md)
- **Feature Documentation**: [ZK Proof Service](../../../apps/coordinator-api/src/coordinator_api/contexts/zk_applications/services/zk_proofs.py)

---

## Scenario Overview

This scenario demonstrates how the coordinator requires a Groth16 receipt proof
before releasing escrow for jobs whose payment is above the high-value threshold.

### Use Case

A buyer pays 10 AIT for an inference job. The provider completes the work, but
the escrow is only released after a `receipt_public` ZK proof is generated and
verified by the coordinator.

### What You'll Learn

- Submit a job with a ZK-proof requirement
- Observe `zk_status` in `aitbc ai status`
- Understand the high-value threshold policy
- Verify that escrow release is gated on `zk_status: verified`

---

## Prerequisites

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- Ollama or another AI service running on the shop (`aitbc3`)
- `COORDINATOR_ENABLE_ZK_VERIFICATION=true` on the hub

### Setup Required

- The hub coordinator has `receipt_public_0001.zkey` and `receipt_public.wasm`
- snarkjs is installed under `apps/zk-circuits/node_modules`

---

## Step-by-Step Workflow

### Step 1: Configure the high-value threshold

On `hub.aitbc`, edit `/etc/aitbc/aitbc-coordinator-api.env`:

```text
COORDINATOR_ENABLE_ZK_VERIFICATION=true
COORDINATOR_ZK_HIGH_VALUE_THRESHOLD=10
COORDINATOR_ZK_REQUIRE=true
```

Restart the coordinator:

```bash
sudo systemctl restart aitbc-coordinator-api
```

### Step 2: Submit a high-value job with ZK proof required

```bash
aitbc ai submit --payment 10 --zk-proof-required --prompt "Write a poem about blockchains" --model llama3.2:3b --wait
```

**Expected output:**

```json
{
  "job_id": "...",
  "state": "QUEUED",
  "payment_id": "...",
  "payment_status": "escrowed",
  "zk_status": "pending"
}
```

### Step 3: Wait for the job to complete and check status

```bash
aitbc ai status --job-id <job-id>
```

**Expected output:**

```json
{
  "job_id": "...",
  "state": "COMPLETED",
  "payment_status": "released",
  "zk_status": "verified",
  "zk_proof_id": "receipt_public_..."
}
```

### Step 4: Force a low-value job without a proof

```bash
aitbc ai submit --payment 0.01 --prompt "Say hello" --model llama3.2:3b --wait
aitbc ai status --job-id <job-id>
```

**Expected output:**

```json
{
  "job_id": "...",
  "state": "COMPLETED",
  "payment_status": "released",
  "zk_status": "not_required"
}
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Submit a high-value job and require a ZK receipt proof
- Read `zk_status` from `aitbc ai status`
- Confirm that low-value jobs are not gated
- Understand the `COORDINATOR_ZK_HIGH_VALUE_THRESHOLD` policy

---

## Validation

### Receipt contains a verified ZK proof

```bash
ssh hub.aitbc
curl -s http://localhost:8203/v1/jobs/<job-id>/result | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('receipt',{}).get('zk_status'))"
```

### ZK service is healthy

```bash
curl -s http://localhost:8203/v1/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d)"
```

### Unit tests

```bash
ssh aitbc3
cd /opt/aitbc
PYTHONPATH=/opt/aitbc:/opt/aitbc/apps/coordinator-api/src:/opt/aitbc/packages/py/aitbc-sdk/src:/opt/aitbc/packages/py/aitbc-crypto/src \
  /opt/aitbc/venv/bin/python3 -m pytest apps/coordinator-api/tests/test_zk_receipt.py -q -o addopts=""
```

---

## Related Resources

- [receipt_public circuit](../../../apps/zk-circuits/receipt_public.circom)
- [ZK proof service](../../../apps/coordinator-api/src/coordinator_api/contexts/zk_applications/services/zk_proofs.py)
- [Payment release gate](../../../apps/coordinator-api/src/coordinator_api/contexts/payments/services/payments.py)
- [Miner result submission](../../../apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py)

---

*Last updated: 2026-08-21*  
*Version: 1.0*
