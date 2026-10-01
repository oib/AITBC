# AIT Value Model — Compute-Backed Currency

**Level**: All Levels
**Prerequisites**: None
**Last Updated**: 2026-08-24

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

The reference rig is an island-level choice, not a protocol constant — the
canonical deployment anchors on this hardware because it is what the
operator runs. An island cloning AITBC can re-anchor on its own rig by
re-running `scripts/ops/ait-reference-price.py` with its own `--component`
entries and rescaling `GPU_COMPUTE_MULTIPLIER` in
`aitbc/market/hardware_catalog.py` so the chosen rig's GPU is 1.0×.

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

Derived by `scripts/ops/ait-reference-price.py` (committed artifact:
`website/reference.json`, rendered on the exchange page under "How the
Reference Is Calculated"):

| Cost Component | Derivation | Per Hour |
|----------------|------------|----------|
| Electricity | 384 W wall draw × €0.30/kWh | €0.115 |
| Hardware wear | €1,530 BOM ÷ 26,280 bookable hours | €0.058 |
| **Cost floor** | | **€0.173** |

Assumptions: 3-year hardware replacement cycle, fully booked (every
lifetime hour is a sold hour — lower utilization would raise wear per sold
hour).

Reference price: ≈ **€0.25** per compute hour (+44 % over the cost floor —
the margin is operator policy, not a cost passthrough).

Re-derive after changing the rig, tariff, or assumptions:

```bash
venv/bin/python scripts/ops/ait-reference-price.py --write-json website/reference.json
```

## Multi-GPU Scaling

| Hardware | Multiplier |
|----------|------------|
| RTX 3060 | 0.7× |
| RTX 4060 Ti 16GB | 1.0× |
| RTX 3090 | 1.5× |
| RTX 4090 | 2.5× |
| H100 | 10× |

This table is code-backed in `aitbc/market/hardware_catalog.py`
(`GPU_COMPUTE_MULTIPLIER`); `aitbc energy suggest` uses it together with the
per-model TBP table (`GPU_TBP_W`) to derive a shop's suggested AIT/hour.
Keep both files in sync when adjusting the model.

## Unit System

**Important**: The blockchain internally uses **compute-units** as the base unit, where **1 AIT = 36,000,000 compute-units**.

- **Internal representation**: All on-chain values (balances, amounts, fees) are stored as integer compute-units
- **User-facing display**: The CLI, APIs, and explorer convert compute-units → AIT for readability
- **Transaction creation**: When you send "100 AIT", the CLI converts it to 3,600,000,000 compute-units internally

This enables precise billing for sub-AIT AI work while maintaining user-friendly AIT display.

## Transaction Fees

AITBC keeps fees simple and almost invisible.

| Fee Type | Rate | Detail |
|----------|------|--------|
| Wallet Transfers | 0.01 AIT (fixed) | ≈ €0.0025 per transaction (360,000 compute-units internally) |
| AI Compute Market | 0.5% | Service fee on compute jobs (19.9 AIT → provider, 0.1 AIT → network) |

### Fee Distribution

| Allocation | Share | Purpose |
|------------|-------|---------|
| Burn | 50% | Reduces supply, rewards long-term holders |
| Treasury | 50% | Community airdrops, hosting, model downloads, development |

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
- [Exchange Tool](https://hub.example.net/exchange.html)
- [Setup Guide](./SETUP.md)
