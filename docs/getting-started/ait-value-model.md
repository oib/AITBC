# AIT Value Model — Compute-Backed Currency

**Level**: All Levels
**Prerequisites**: None
**Last Updated**: 2026-06-23

## Navigation

Home → Docs → Getting Started → AIT Value Model

---

## What AIT Represents

1 AIT represents AI inference compute contributed by the network. Unlike speculative cryptocurrencies, AIT is designed around real-world AI computation.

The reference value of AIT is derived from:

- Electricity cost
- Hardware depreciation
- Inference throughput
- Community contribution

## Reference Value

| Metric | Value |
|--------|-------|
| 1 AIT | ≈ 1 Compute Hour |
| Reference price | ≈ €0.25 |
| Pricing currency | EUR (reference only) |

EUR serves only as a pricing reference. AIT represents compute, not fiat currency.

## Reference Hardware

| Component | Specification |
|-----------|---------------|
| GPU | RTX 4060 Ti 16GB |
| CPU | Ryzen 5950X |
| RAM | 64 GB |

Average models served:

- Llama 3.1 8B
- Gemma 3 12B
- Qwen 3 8B

## Performance

| Metric | Value |
|--------|-------|
| Throughput | ≈ 60 tokens/sec |
| Hourly throughput | ≈ 216,000 tokens/hour |

## Operating Cost

| Cost Component | Per Hour |
|----------------|----------|
| Electricity | €0.08 |
| Hardware wear | €0.14 |
| **Total** | **€0.22** |

Reference value: ≈ €0.25 per compute hour.

## Multi-GPU Scaling

| Hardware | Multiplier |
|----------|------------|
| RTX 3060 | 0.7× |
| RTX 4060 Ti 16GB | 1.0× |
| RTX 3090 | 1.5× |
| RTX 4090 | 2.5× |
| H100 | 10× |

## Unit System

**Important**: The blockchain internally uses compute-seconds as the base unit, where 1 AIT = 3600 seconds (1 hour of compute).

- **Internal representation**: All on-chain values (balances, amounts, fees) are stored as integer seconds
- **User-facing display**: The CLI, APIs, and explorer convert seconds → AIT for readability
- **Transaction creation**: When you send "100 AIT", the CLI converts it to 360,000 seconds internally

This enables precise billing at the second level while maintaining user-friendly AIT display.

## Transaction Fees

AITBC keeps fees simple and almost invisible.

| Fee Type | Rate | Detail |
|----------|------|--------|
| Wallet Transfers | 0.01 AIT (fixed) | ≈ €0.0025 per transaction (36 compute-seconds internally) |
| AI Compute Marketplace | 0.5% | Service fee on compute jobs (19.9 AIT → provider, 0.1 AIT → network) |

### Fee Distribution

| Allocation | Share | Purpose |
|------------|-------|---------|
| Burn | 50% | Reduces supply, rewards long-term holders |
| Treasury | 50% | Faucet giveaways, hosting, model downloads, development |

## Why Not Peg to ETH?

| Option | Verdict | Reason |
|--------|---------|--------|
| ETH | Volatile | Price swings make it unsuitable as a stable compute reference. |
| USD | Stable, but not energy-based | Doesn't reflect real electricity or hardware costs. |
| EUR Reference | Matches electricity costs in Europe | EUR is used only as a pricing reference — AIT is compute, not fiat. |

## Long-Term Vision

Compute becomes currency.

The more AI work contributed, the more value is created. AIT aims to connect humans, hardware, and artificial intelligence through a shared compute economy.

---

## See Also

- [Free AIT — Early Adopter Program](./free-ait.md)
- [Exchange Tool](https://hub.aitbc.bubuit.net/exchange.html)
- [Setup Guide](./SETUP.md)
