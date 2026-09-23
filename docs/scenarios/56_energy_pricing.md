# Energy Pricing & Provider Registry

**Level**: Advanced
**Prerequisites**: Scenario 09 GPU Listing (a registered GPU resource)
**Estimated Time**: 20 minutes
**Last Updated**: 2026-09-16
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Energy Pricing

---

## See Also

- **Previous Scenario**: [Dispute Lifecycle](./55_dispute_lifecycle.md)
- **Next Scenario**: [Coin Requests](./57_coin_requests.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/energy.py`

---

## Scenario Overview

> **Live vs. simulated:** the energy pricing surface is **config-gated, live
> code** — `provider register`/`profile`/`floor` read and write the
> on-chain `IEnergyPricing` contract over `EVM_RPC_URL`, and
> `operator info`/`verify` are local quote-signing operations gated on
> `ENERGY_OPERATOR_ADDRESS`. On the current fleet neither is provisioned, so
> the EVM steps fail closed (`EVM RPC URL not configured`) — that refusal is
> the honest behavior until an EVM endpoint is wired.

This scenario covers how GPU providers register an energy profile, how the
on-chain energy floor for a rental is computed, and how an operator-signed
energy quote is verified.

### Use Case

A shop wants its electricity tariff reflected in GPU rental pricing so the
energy floor tracks real cost instead of a static guess.

### What You'll Learn

- How a provider registers a GPU energy profile (`provider register`)
- How to read a registered profile (`provider profile`)
- How to compute the on-chain energy floor for a rental (`floor`)
- How operator quote signing and verification work (`operator info|verify`)

---

## Prerequisites

- A provider wallet with signing access (`--wallet` / `--wallet-path`)
- `EVM_RPC_URL` pointing at the chain hosting `IEnergyPricing` — required for
  `floor`, `provider register`, `provider profile`, `provider rate`
- `ENERGY_OPERATOR_ADDRESS` configured for `operator info`/`verify`

---

## Steps

### 1. Register an energy profile (provider)

```bash
aitbc energy provider register \
  --resource-id gpu-rtx4090-01 \
  --provider-address 0xYourProvider \
  --model-id rtx-4090 \
  --tbp-watts 450 \
  --eur-per-kwh 0.32 \
  --wallet provider
```

Writes the profile to the `IEnergyPricing` contract. Fails closed with
`EVM RPC URL not configured` when no EVM endpoint is set.

### 2. Read the profile back

```bash
aitbc energy provider profile --resource-id gpu-rtx4090-01
```

### 3. Compute the energy floor for a rental

```bash
aitbc energy floor --resource-id gpu-rtx4090-01 \
  --gpu-count 1 --duration-seconds 3600
```

The floor is the minimum settlement that still covers the provider's energy
cost for the rental duration.

### 4. Operator quote signing and verification

```bash
aitbc energy operator info                          # signing status + address
aitbc energy operator verify --quote-file quote.json  # signature + freshness
aitbc energy operator verify --quote-file quote.json --check-oracle  # + on-chain
```

`operator info` reports `No operator address configured
(ENERGY_OPERATOR_ADDRESS)` until the operator identity is provisioned —
verified live on the fleet.

---

## Verification

- `provider profile --resource-id …` returns the registered TBP and tariff.
- `floor` returns a numeric floor that scales with `--duration-seconds`.

## Troubleshooting

- `EVM RPC URL not configured` — set `EVM_RPC_URL`; the energy contract lives
  on the EVM side.
- `No operator address configured` — set `ENERGY_OPERATOR_ADDRESS` on the
  operator node.
