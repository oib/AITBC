# Pricing & Costs
Understand the cost structure for using AITBC.

## Cost Structure

### Per-Job Pricing

| Resource | Unit | Price |
|----------|------|-------|
| GPU (V100) | per hour | 0.05 AITBC |
| GPU (A100) | per hour | 0.10 AITBC |
| GPU (RTX3090) | per hour | 0.03 AITBC |
| Storage | per GB/day | 0.001 AITBC |

### Priority Pricing

| Priority | Multiplier |
|----------|------------|
| Low | 0.8x |
| Normal | 1.0x |
| High | 1.5x |
| Urgent | 2.0x |

## Cost Examples

### Small Job (V100, 1 hour)

```
Base: 0.05 AITBC
Normal priority: 1.0x
Total: 0.05 AITBC
```

### Large Job (A100, 4 GPUs, 4 hours)

```
Base: 0.10 AITBC × 4 GPUs × 4 hours = 1.60 AITBC
High priority: 1.5x
Total: 2.40 AITBC
```

## Free Tier

- 10 GPU hours per month
- 1 GB storage
- Limited to V100 GPUs

## Enterprise Plans

| Feature | Basic | Pro | Enterprise |
|---------|-------|-----|------------|
| GPU hours/month | 100 | 500 | Unlimited |
| Priority | Normal | High | Urgent |
| Support | Email | 24/7 Chat | Dedicated |
| SLA | 99% | 99.9% | 99.99% |

## Next Steps

- [Billing](./5_pricing-billing.md) - Billing and invoices
- [Wallet](./4_wallet.md) - Managing your wallet
- [Job Submission](./2_job-submission.md) - Submitting jobs

---
Manage billing and view invoices.

## View Invoices

```bash
aitbc billing list
```

### Filter by Date

```bash
aitbc billing list --from 2026-01-01 --to 2026-01-31
```

### Download Invoice

```bash
aitbc billing download --invoice-id <INV_ID>
```

## Payment Methods

### Add Payment Method

```bash
aitbc billing add-card --number 4111111111111111 --expiry 12/26 --cvc 123
```

### Set Default

```bash
aitbc billing set-default --card-id <CARD_ID>
```

## Auto-Pay

```bash
# Enable auto-pay
aitbc billing auto-pay enable

# Disable auto-pay
aitbc billing auto-pay disable
```

## Billing Alerts

```bash
# Set spending limit
aitbc billing alert --limit 100 --email you@example.com
```

## Next Steps

- [Pricing](./5_pricing-billing.md) - Cost structure
- [Wallet](./4_wallet.md) - Managing your wallet
- [Job Submission](./2_job-submission.md) - Submitting jobs
