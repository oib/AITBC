# Job Management
Accept and complete jobs on the AITBC network.

## Overview

Jobs are assigned to miners based on GPU availability, price, and reputation.

## Accept Jobs

### Manual Acceptance

```bash
aitbc miner jobs --available
aitbc miner accept --job-id <JOB_ID>
```

### Auto-Accept

```bash
aitbc miner auto-accept enable --max-concurrent 4
```

### Auto-Accept Settings

```bash
# Set GPU requirements
aitbc miner auto-accept --gpu v100 --gpu-count 1-4

# Set price range
aitbc miner auto-accept --min-price 0.08 --max-price 0.12
```

## Job States

| State | Description |
|-------|-------------|
| assigned | Job assigned, waiting to start |
| starting | Preparing environment |
| running | Executing job |
| uploading | Uploading results |
| completed | Job finished successfully |
| failed | Job error occurred |

## Monitor Jobs

### Check Status

```bash
aitbc miner job-status --job-id <JOB_ID>
```

### Watch Progress

```bash
aitbc miner watch --job-id <JOB_ID>
```

### List Active Jobs

```bash
aitbc miner jobs --active
```

## Complete Jobs

### Manual Completion

```bash
aitbc miner complete --job-id <JOB_ID>
```

### Upload Results

```bash
aitbc miner upload --job-id <JOB_ID> --path ./results
```

## Handle Failures

### Retry Job

```bash
aitbc miner retry --job-id <JOB_ID>
```

### Report Issue

```bash
aitbc miner report --job-id <JOB_ID> --reason "gpu-error"
```

## Next

- [Earnings](./4_earnings.md) — Earnings tracking
- [GPU Setup](./5_gpu-setup.md) — GPU configuration
- [Monitoring](./6_monitoring.md) - Monitor your miner
