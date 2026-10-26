# Developer Registry

**Level**: Beginner
**Prerequisites**: Scenario 01 Wallet Basics
**Estimated Time**: 10 minutes
**Last Updated**: 2026-10-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Developer Registry

---

## See Also

- **Previous Scenario**: [Reinvest Policy](./71_reinvest_policy.md)
- **Next Scenario**: [Contract Deploy & Call](./73_contract_deploy_call.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/developer.py`

---

## Scenario Overview

> **Live vs. simulated:** `aitbc developer` calls the coordinator's
> `/v1/developers` endpoints — real registry records, no simulated
> fallback. `register` creates a real record keyed to a wallet address.

This scenario covers the DAO developer registry: registering a developer
by wallet address and listing the registry. Registered developers are the
`--developer-id` input for `aitbc grant create` (scenario 67).

### Use Case

Before a contributor can file a DAO grant, their wallet must exist in the
developer registry with name/GitHub metadata for accountability.

### What You'll Learn

- `developer register` — add a developer record
- `developer list` — page and filter the registry

---

## Prerequisites

- Coordinator reachable
- A wallet address for the developer being registered

---

## Steps

### 1. List the registry (read-only)

```bash
aitbc developer list
aitbc developer list --active-only --limit 50 --offset 0
aitbc developer list --format json
```

**Expected output:** registered developers with wallet address, name,
GitHub handle, and active flag.

### 2. Register a developer (write — operator line)

```bash
aitbc developer register --wallet-address 0x<dev-wallet> \
    --name Alice --github-handle alice --email alice@example.org
```

Creates a real registry record — not played without the operator's line;
only `--wallet-address` is required.

---

## Cost Table

| Step | Spend |
|---|---|
| `developer list` | 0 AIT |
| `developer register` | registry record — 0 AIT spend, but a write; not played |

---

## Verification

- `developer list` shows the new record after `register`.
- The returned developer id can be passed to `aitbc grant create
  --developer-id` (scenario 67).

## Troubleshooting

- `Network error` — coordinator unreachable; no fallback.
