# Earnings & Payouts
Track and manage your mining earnings.

## Earnings Overview

```bash
aitbc miner earnings
```

Shows:
- Total earned
- Pending balance
- Last payout

## Earnings Breakdown

| Source | Description |
|--------|-------------|
| job_completion | Payment for completed jobs |
| bonus | Performance bonuses |
| referral | Referral rewards |

## Payout Schedule

| Plan | Schedule | Minimum |
|------|----------|---------|
| Automatic | Daily | 10 AITBC |
| Manual | On request | 1 AITBC |

## Request Payout

```bash
aitbc wallet withdraw --amount 100 --address <WALLET_ADDRESS>
```

## Earnings History

```bash
aitbc miner earnings --history --days 30
```

## Performance Metrics

```bash
aitbc miner stats
```

Shows:
- Success rate
- Average completion time
- Total jobs completed
- Earnings per GPU/hour

## Tax Reporting

```bash
aitbc miner earnings --export --year 2026
```

Export for tax purposes.

## Next

- [Job Management](./3_job-management.md) — Job management
- [Monitoring](./6_monitoring.md) - Monitor your miner
- [GPU Setup](./5_gpu-setup.md) — GPU configuration
