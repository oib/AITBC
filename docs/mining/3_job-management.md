# Job Management

Accept and complete jobs on the the network.

## Overview

Jobs are assigned to miners based on GPU availability, price, and reputation.
On a miner node, job polling, acceptance, execution, and result submission are
handled automatically by the `aitbc-miner` service (`production_miner.py`),
which polls the coordinator API for work. The CLI is used to inspect jobs and
handle failures/refunds.

## Daemon Operation

```bash
# Start / stop the job-polling miner daemon
sudo systemctl start aitbc-miner
sudo systemctl stop aitbc-miner

# Follow its logs
journalctl -u aitbc-miner -f
```

Job polling and acceptance are automatic once the daemon is running — there is
no separate `accept`/`auto-accept` CLI step on the miner side. Concurrency and
GPU targeting are configured in the service environment.

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
aitbc ai status --job-id <JOB_ID>
```

### List Jobs

```bash
# Recent jobs (optionally filter by state)
aitbc ai jobs --status running --limit 20
```

### Fetch Results

```bash
aitbc ai results --job-id <JOB_ID>
```

## Handle Failures

### Cancel a Job

```bash
aitbc ai cancel --job-id <JOB_ID> --wallet my-miner-wallet
```

### Refund an Escrowed Payment

```bash
aitbc ai refund --job-id <JOB_ID> --reason gpu-error
```

### Retry

Failed jobs are retried by resubmitting or letting the daemon pick the job up
again; watch `journalctl -u aitbc-miner` for retry activity.

## Next

- [Earnings](./4_earnings.md) — Earnings tracking
- [GPU Setup](./5_gpu-setup.md) — GPU configuration
- [Monitoring](./6_monitoring.md) - Monitor your miner
