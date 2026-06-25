# AI Job Submission

**Level**: Beginner
**Prerequisites**: Scenario 02 Transaction Sending, Scenario 06 Basic Trading
**Estimated Time**: 20 minutes
**Last Updated**: 2026-06-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > AI Job Submission

---

## See Also

- **Previous Scenario**: [Basic Trading](./06_basic_trading.md)
- **Next Scenario**: [Marketplace Bidding](./08_marketplace_bidding.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Feature Documentation**: [AI CLI Commands](../../cli/aitbc_cli/commands/ai.py), [ComputeConsumer](../../packages/py/aitbc-agent-sdk/src/aitbc_agent/compute_consumer.py)

---

## Scenario Overview

This scenario demonstrates how an AI agent submits compute jobs to the AITBC coordinator, lists active jobs, and monitors job status and results. Jobs are submitted to the coordinator API (default `http://localhost:8203`) and tracked through their lifecycle.

### Use Case

An AI agent needs to run an inference or training workload on the AITBC network. It submits a job with a prompt, a payment amount in AIT, and a wallet for signing, then polls the coordinator until the job completes and retrieves the results.

### What You'll Learn

- How to submit an AI job via the `aitbc ai submit` command
- How to list jobs and filter by status
- How to check a single job's status and fetch its results
- How to submit and track jobs programmatically with the `ComputeConsumer` SDK class

---

## Prerequisites

### Knowledge Required

- Scenario 02 (Transaction Sending) — payment is referenced from a wallet
- Scenario 06 (Basic Trading) — you need AIT balance to pay for jobs

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- A wallet with AIT balance (created in Scenario 01)
- Coordinator API reachable at `http://localhost:8203` (override with `--coordinator-url`)

### Setup Required

- Configure the coordinator URL: `aitbc config set coordinator_url http://localhost:8203`
- Ensure the coordinator-api service is running
- Have a wallet name and (optionally) a password file ready

---

## Step-by-Step Workflow

### Step 1: Submit an AI job

Submit a job with a wallet, job type, prompt, and payment amount. The coordinator URL defaults to your CLI config; override with `--coordinator-url`.

```bash
# Submit an inference job paying 5.0 AIT from wallet "agent-wallet"
aitbc ai submit \
  --wallet agent-wallet \
  --type inference \
  --prompt "Summarize the latest AITBC block headers" \
  --payment 5.0 \
  --coordinator-url http://localhost:8203 \
  --format json
```

**Expected output:**
```json
{
  "job_id": "job_7f8e9d0c1b2a3c4d",
  "job_type": "inference",
  "prompt": "Summarize the latest AITBC block headers",
  "payment": 5.0,
  "wallet": "agent-wallet",
  "status": "pending"
}
```

> **Password handling**: Use `--password` to pass the wallet password inline, or `--password-file /path/to/pass.txt` to read it from a file (the file must exist). Use `--chain-id` and `--rpc-url` to override the blockchain target.

### Step 2: List AI jobs

List recent jobs, optionally filtered by status. `--limit` defaults to 10.

```bash
# List the 10 most recent jobs
aitbc ai jobs --limit 10 --format table

# List only pending jobs
aitbc ai jobs --status pending --coordinator-url http://localhost:8203
```

**Expected output:**
```
AI Jobs
=======
Job ID                  Job Type    Status     Payment   Wallet
job_7f8e9d0c1b2a3c4d    inference   pending    5.0       agent-wallet
job_a1b2c3d4e5f67890    training    completed  12.5      agent-wallet
job_0f1e2d3c4b5a6978    inference   running    3.0       agent-wallet
```

### Step 3: Check a single job's status

Use `--job-id` to fetch one job's current state from the coordinator.

```bash
aitbc ai status --job-id job_7f8e9d0c1b2a3c4d --format json
```

**Expected output:**
```json
{
  "job_id": "job_7f8e9d0c1b2a3c4d",
  "status": "running",
  "job_type": "inference",
  "provider_id": "provider_abc123",
  "started_at": "2026-06-25T14:35:12Z",
  "estimated_completion": "2026-06-25T14:37:00Z"
}
```

### Step 4: Fetch job results

Once a job reaches `completed`, retrieve its output with `aitbc ai results`.

```bash
aitbc ai results --job-id job_7f8e9d0c1b2a3c4d --format json
```

**Expected output:**
```json
{
  "job_id": "job_7f8e9d0c1b2a3c4d",
  "status": "completed",
  "output": {
    "summary": "Block 12345: 42 transactions, 1 exchange order matched..."
  },
  "execution_time": 108.4,
  "cost": 5.0,
  "quality_score": 0.92
}
```

### Step 5: Discover available AI services

Before submitting, an agent can inspect which AI services the coordinator exposes.

```bash
# List all services
aitbc ai service list --coordinator-url http://localhost:8203

# Check one service's status
aitbc ai service service-status --name llm-inference --format json

# Ping a service endpoint
aitbc ai service test --name llm-inference
```

---

## Code Examples Using Agent SDK

The `aitbc_agent` package exposes `ComputeConsumer`, an `Agent` subclass for agents that consume compute resources. It submits jobs to the coordinator and polls their status asynchronously.

### Example 1: Create a consumer and submit a job

```python
import asyncio
from aitbc_agent import ComputeConsumer

async def main() -> None:
    # Create a consumer agent with generated RSA identity
    consumer = ComputeConsumer.create(
        name="inference-buyer",
        agent_type="consumer",
        capabilities={
            "compute_type": "inference",
            "performance_score": 0.0,
            "max_concurrent_jobs": 1,
        },
    )
    # Point at the local coordinator API
    consumer.coordinator_url = "http://localhost:8203"

    # Register the consumer on the network
    await consumer.register()

    # Submit a job (returns a job_id string)
    job_id = await consumer.submit_job(
        job_type="inference",
        input_data={"prompt": "Summarize the latest AITBC block headers"},
        requirements={"max_latency_ms": 5000},
        max_price=5.0,
    )
    print(f"Submitted job: {job_id}")

    # Poll status
    status = await consumer.get_job_status(job_id)
    print(f"Status: {status}")

asyncio.run(main())
```

### Example 2: Track a job to completion

```python
import asyncio
from aitbc_agent import ComputeConsumer

async def wait_for_completion(consumer: ComputeConsumer, job_id: str, timeout: float = 300) -> dict:
    """Poll a job until it reaches a terminal state."""
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = await consumer.get_job_status(job_id)
        state = status.get("status")
        if state in ("completed", "failed", "timeout"):
            return status
        await asyncio.sleep(5)
    return {"job_id": job_id, "status": "timeout"}

async def main() -> None:
    consumer = ComputeConsumer.create(
        name="inference-buyer",
        agent_type="consumer",
        capabilities={"compute_type": "inference", "max_concurrent_jobs": 1},
    )
    consumer.coordinator_url = "http://localhost:8203"
    await consumer.register()

    job_id = await consumer.submit_job(
        job_type="inference",
        input_data={"prompt": "Translate this document to French"},
        max_price=3.0,
    )
    result = await wait_for_completion(consumer, job_id)
    print(result)

    # Spending summary
    print(consumer.get_spending_summary())

asyncio.run(main())
```

### Example 3: Cancel a pending job

```python
import asyncio
from aitbc_agent import ComputeConsumer

async def main() -> None:
    consumer = ComputeConsumer.create(
        name="inference-buyer",
        agent_type="consumer",
        capabilities={"compute_type": "inference"},
    )
    consumer.coordinator_url = "http://localhost:8203"
    job_id = await consumer.submit_job("inference", {"prompt": "test"}, max_price=1.0)
    ok = await consumer.cancel_job(job_id)
    print(f"Cancelled {job_id}: {ok}")

asyncio.run(main())
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Submit an AI job to the coordinator with payment and wallet metadata
- List and filter jobs by status
- Poll a single job's status and retrieve its results
- Use the `ComputeConsumer` SDK class to submit, track, and cancel jobs programmatically

---

## Validation

Confirm the job lifecycle end-to-end:

```bash
# Submit a job and capture its job_id
aitbc ai submit --wallet agent-wallet --type inference --prompt "hello" --payment 1.0 --format json

# Poll until status is completed/failed
aitbc ai status --job-id <job_id>

# Fetch the result payload
aitbc ai results --job-id <job_id>

# Confirm the job appears in the list
aitbc ai jobs --status completed --limit 5
```

---

## Related Resources

- Source: `cli/aitbc_cli/commands/ai.py` (submit, jobs, status, results, service group)
- SDK: `packages/py/aitbc-agent-sdk/src/aitbc_agent/compute_consumer.py` (`ComputeConsumer.submit_job`, `get_job_status`, `cancel_job`, `get_spending_summary`)
- [Next Scenario: Marketplace Bidding](./08_marketplace_bidding.md)

---

*Last updated: 2026-06-25*
*Version: 1.0*
