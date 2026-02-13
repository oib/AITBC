# Job Status Guide
Understand job states and how to track progress.

## Job States

| State | Description | Actions |
|-------|-------------|---------|
| pending | Job queued, waiting for miner | Wait |
| assigned | Miner assigned, starting soon | Wait |
| running | Job executing | Monitor |
| completed | Job finished successfully | Download |
| failed | Job error occurred | Retry/Contact |
| canceled | Job cancelled by user | None |

## Check Status

### Using CLI

```bash
aitbc client status --job-id <JOB_ID>
```

### Using API

```python
import requests

response = requests.get(
    "http://localhost:8000/v1/jobs/{job_id}",
    headers={"X-Api-Key": "your-key"}
)
print(response.json())
```

## Status Response Example

```json
{
  "job_id": "job_abc123",
  "status": "running",
  "progress": 45,
  "miner_id": "miner_xyz789",
  "created_at": "2026-02-13T10:00:00Z",
  "started_at": "2026-02-13T10:01:00Z",
  "estimated_completion": "2026-02-13T10:30:00Z"
}
```

## Progress Tracking

### Real-time Updates

```bash
aitbc client watch --job-id <JOB_ID>
```

### WebSocket Updates

```python
import websocket

def on_message(ws, message):
    print(message)

ws = websocket.WebSocketApp(
    "ws://localhost:8000/v1/jobs/ws",
    on_message=on_message
)
ws.run_forever()
```

## State Transitions

```
pending → assigned → running → completed
    ↓           ↓          ↓
  failed    failed     failed
    ↓           ↓          ↓
  canceled  canceled   canceled
```

## Next Steps

- [Job Submission](./2_job-submission.md) - Submitting jobs
- [Results](./3_job-lifecycle.md) - Managing results
- [Job History](./3_job-lifecycle.md) - Viewing past jobs

---
Learn how to download and manage job results.

## Overview

Results are stored after job completion. This guide covers downloading and managing outputs.

## Download Results

### Using CLI

```bash
aitbc client download --job-id <JOB_ID> --output ./results
```

### Using API

```python
import requests

response = requests.get(
    "http://localhost:8000/v1/jobs/{job_id}/download",
    headers={"X-Api-Key": "your-key"}
)

with open("output.zip", "wb") as f:
    f.write(response.content)
```

## Result Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| JSON | `.json` | Structured data output |
| Text | `.txt` | Plain text output |
| Binary | `.bin` | Model weights, tensors |
| Archive | `.zip` | Multiple files |

## Result Contents

A typical result package includes:

```
job_<ID>/
├── output.json          # Job metadata and status
├── result.txt           # Main output
├── logs/                # Execution logs
│   ├── stdout.log
│   └── stderr.log
└── artifacts/           # Model files, etc.
    └── model.bin
```

## Result Retention

| Plan | Retention |
|------|-----------|
| Free | 7 days |
| Pro | 30 days |
| Enterprise | 90 days |

## Sharing Results

### Generate Share Link

```bash
aitbc client share --job-id <JOB_ID>
```

### Set Expiration

```bash
aitbc client share --job-id <JOB_ID> --expires 7d
```

## Verify Results

### Check Integrity

```bash
aitbc client verify --job-id <JOB_ID>
```

### Compare Checksums

```bash
# Download checksum file
aitbc client download --job-id <JOB_ID> --checksum

# Verify
sha256sum -c output.sha256
```

## Delete Results

```bash
aitbc client delete --job-id <JOB_ID>
```

## Next Steps

- [Job Status](./3_job-lifecycle.md) - Understanding job states
- [Job Submission](./2_job-submission.md) - Submitting jobs
- [Billing](./5_pricing-billing.md) - Understanding charges

---
View and manage your past jobs.

## List All Jobs

```bash
aitbc client list
```

### Filter by Status

```bash
# Running jobs
aitbc client list --status running

# Completed jobs
aitbc client list --status completed

# Failed jobs
aitbc client list --status failed
```

### Filter by Date

```bash
# Last 7 days
aitbc client list --days 7

# Specific date range
aitbc client list --from 2026-01-01 --to 2026-01-31
```

## Job Details

```bash
aitbc client get --job-id <JOB_ID>
```

## Export History

```bash
# Export to JSON
aitbc client export --format json --output jobs.json

# Export to CSV
aitbc client export --format csv --output jobs.csv
```

## Statistics

```bash
aitbc client stats
```

Shows:
- Total jobs submitted
- Success rate
- Average completion time
- Total spent

## Next Steps

- [Job Status](./3_job-lifecycle.md) - Understanding job states
- [Job Cancellation](./3_job-lifecycle.md) - Canceling jobs
- [Billing](./5_pricing-billing.md) - Understanding charges

---
How to cancel jobs and manage running operations.

## Cancel a Job

```bash
aitbc client cancel --job-id <JOB_ID>
```

## Confirmation

```bash
aitbc client cancel --job-id <JOB_ID> --force
```

## Cancellation States

| State | Description |
|-------|-------------|
| canceling | Cancellation requested |
| canceled | Job successfully canceled |
| failed | Cancellation failed |

## Effects

- Job stops immediately
- Partial results may be available
- Charges apply for resources used

## Next Steps

- [Job Submission](./2_job-submission.md) - Submitting jobs
- [Job History](./3_job-lifecycle.md) - Viewing past jobs
- [Pricing](./5_pricing-billing.md) - Cost structure
