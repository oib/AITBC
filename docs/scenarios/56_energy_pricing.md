# Energy Pricing & Provider Registry

**Level**: Advanced
**Prerequisites**: Scenario 09 GPU Listing (a registered GPU resource)
**Estimated Time**: 20 minutes
**Last Updated**: 2026-11-21
**Version**: 1.1

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

> **Live vs. simulated:** the energy pricing surface is **live code on the
> native rail** — with no `EVM_RPC_URL`/`IEnergyPricing` configured (the
> fleet case), `provider register`/`profile`/`rate`/`floor` route to the
> coordinator's `/v1/market/native-energy/*` endpoints (miner credential
> for writes), and `operator info`/`verify` are local quote-signing
> operations gated on `ENERGY_OPERATOR_ADDRESS`.
>
> **Descoped 21 Nov 2026 (operator ruling):** the fleet settles on the
> native energy rail; the `IEnergyPricing` EVM contract path is descoped
> until an EVM endpoint is wired. Steps below describe the native path;
> the EVM contract variant is retained in the CLI but out of scope for
> fleet replay.

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
- Reachability of the hub coordinator's `/v1/market/native-energy/*`
  endpoints — the canonical fleet rail (descoped EVM path would instead
  need `EVM_RPC_URL` + `energy_pricing_contract_address`)
- A miner-tier credential for `provider register`/`rate --publish`
  writes; client credential suffices for reads
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

Posts the profile to the coordinator's native-energy rail
(`POST /v1/market/native-energy/profile`, miner auth). The descoped EVM
variant would instead write `IEnergyPricing` over `EVM_RPC_URL`.

### 2. Suggest a profile from detected hardware

```bash
aitbc energy suggest --region de
```

Probes the node (`nvidia-smi` power limit = the card's real TBP, `lscpu` for
the CPU), sums the whole-node draw — GPU board power + CPU + board/RAM/fan
overhead, divided by PSU efficiency — applies the regional EUR/kWh tariff
(static table; `--eur-per-kwh` or `ENERGY_EUR_PER_KWH` override), and prints:

- the watts to register (`register_watts` — per-GPU-equivalent: platform draw
  is shared across the node's GPUs because the floor formula multiplies watts
  by `--gpu-count`),
- the resulting energy floor in AIT/hour,
- the suggested market price (`multiplier × 1 AIT/h`, the EUR 0.25
  compute-hour reference) when the GPU model has a multiplier entry.

`--register` submits the printed `provider register` transaction directly
(requires `--resource-id --provider-address` and a wallet).

### 3. Read the profile back

```bash
aitbc energy provider profile --resource-id gpu-rtx4090-01
```

Reads via `GET /v1/market/native-energy/profile/{resource_id}` on the
native rail (the descoped EVM path reads `IEnergyPricing` instead).

### 4. Compute the energy floor for a rental

```bash
aitbc energy floor --resource-id gpu-rtx4090-01 \
  --gpu-count 1 --duration-seconds 3600
```

The floor is the minimum settlement that still covers the provider's energy
cost for the rental duration.

### 5. Operator quote signing and verification

```bash
aitbc energy operator info                          # signing status + address
aitbc energy operator verify --quote-file quote.json  # signature + freshness
aitbc energy operator verify --quote-file quote.json --check-oracle  # + on-chain
```

`operator info` reports `No operator address configured
(ENERGY_OPERATOR_ADDRESS)` until the operator identity is provisioned —
verified live on the fleet.

---


---

<!-- PLAY3 coverage extension: uncovered CLI leaves folded into this scenario (issue #438) -->

### 6. Read the provider AIT/EUR rate

Prints the provider's configured AIT-per-EUR rate via
`GET /v1/market/native-energy/rate`; with `--publish` it writes
`POST /v1/market/native-energy/rate` (miner auth) — this pass reads only.

```bash
aitbc energy provider rate
```

---

## Verification

- `provider profile --resource-id …` returns the registered TBP and tariff.
- `floor` returns a numeric floor that scales with `--duration-seconds`.

## Troubleshooting

- `401/403` on native-energy writes — the write endpoints require a
  miner-tier credential; reads work with the client credential.
- `No operator address configured` — set `ENERGY_OPERATOR_ADDRESS` on the
  operator node.
- (Descoped EVM path) `EVM RPC URL not configured` — the `IEnergyPricing`
  contract path is out of scope for fleet replay per the 21 Nov ruling.
