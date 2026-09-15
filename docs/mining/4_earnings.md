# Earnings & Payouts

Track and manage your mining earnings.

## Earnings Overview

Mining payouts arrive as ordinary transfers into your miner wallet. Check the
balance and incoming transactions:

```bash
aitbc wallet balance --name my-miner-wallet
aitbc wallet transactions --name my-miner-wallet --limit 50
```

Shows:

- Total earned (incoming transfers)
- Current balance
- Transaction history

## Earnings Breakdown

| Source | Description |
|--------|-------------|
| job_completion | Payment for completed jobs |
| block_reward | PoA block production rewards |
| bonus | Performance bonuses |

## Payout Schedule

| Plan | Schedule | Minimum |
|------|----------|---------|
| Automatic | Per job / per block | Settled on-chain |

## Send Earnings to Another Wallet

```bash
aitbc wallet --wallet-name my-miner-wallet send \
  --to-address <RECIPIENT_ADDRESS> \
  --amount 100
```

## Performance Metrics

```bash
# Mining loop status
aitbc mining status

# Job statistics from the coordinator
aitbc ai stats
```

Shows:

- Success rate
- Average completion time
- Total jobs completed

## Next

- [Job Management](./3_job-management.md) — Job management
- [Monitoring](./6_monitoring.md) - Monitor your miner
- [GPU Setup](./5_gpu-setup.md) — GPU configuration
