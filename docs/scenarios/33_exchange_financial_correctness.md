# Exchange Financial Correctness

**Level**: Intermediate
**Prerequisites**: [Scenario 32 Hardcoded Secrets Fail-Fast](./32_hardcoded_secrets_failfast.md)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-08-21
**Version**: 1.3

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Exchange Financial Correctness

---

## See Also

- **Previous Scenario**: [Scenario 32 Hardcoded Secrets Fail-Fast](./32_hardcoded_secrets_failfast.md)
- **Next Scenario**: [Scenario 34 Hub↔Customer Node End-to-End](./34_hub_customer_node_e2e.md)
- **Related beginner play**: [Scenario 06 Basic Trading](./06_basic_trading.md)

---

## Scenario Overview

> **Live vs. simulated:** `aitbc exchange-island` commands are **live** when the exchange service (port 8106) is running. If the exchange is unreachable, the CLI returns `(Simulated)` orders and transactions.

The live hub exchange is `apps/exchange/simple_exchange` on port 8106 (API-key auth, Decimal/TEXT money columns, `BEGIN IMMEDIATE` matching — B1/B2/B3). Operators trade through `aitbc exchange-island`, not raw `/v1/exchange/orderbook` (that path 404s).

`buy` / `sell` / `cancel` still need `/var/lib/aitbc/keystore/validator_keys.json`. `orderbook`, `rates`, and `orders` work without it.

### Use Case

A customer inspects the book and rates with the CLI; placing orders is gated on the validator keystore (documented gap, DESIGN_CYCLE P0.6).

### What You'll Learn

- The live CLI group (`aitbc exchange-island`) and the stale HTTP paths to avoid
- Which subcommands work without the keystore
- How to run the Decimal/race unit tests as validation

---

## Prerequisites

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`

### Setup Required

- Hub exchange running (or CLI config `exchange_service_url` pointing at it)
- Shop/follower CLIs fall back to `exchange_service_url` when island credentials lack an RPC (`e1cd871dd`)

---

## Step-by-Step Workflow

### Step 1: Rates and order book (no keystore)

```bash
aitbc exchange-island rates
aitbc exchange-island orderbook AIT/ETH --limit 10
aitbc exchange-island orders --status open
```

**Expected output:** rate rows and a (possibly empty) book. Simulated deterministic output is acceptable on a shop node if the exchange RPC is unreachable — label it simulated.

Do **not** call `GET /v1/exchange/orderbook` or `POST /v1/exchange/orders`. Live contract:

- `GET /api/orders/orderbook`
- `POST /api/orders` with `X-Api-Key`

The CLI wraps that surface.

### Step 2: Place a buy only if the keystore exists

```bash
aitbc exchange-island buy 1 ETH --max-price 0.00001260
```

**Expected output:** an order id if `validator_keys.json` is present. Otherwise a clear abort (`Keystore not found at /var/lib/aitbc/keystore/validator_keys.json`). That abort is the current product, not a scenario failure.

### Step 3: List again

```bash
aitbc exchange-island orders --status open
aitbc exchange-island cancel <order-id>   # only if Step 2 created one
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Read rates, book, and orders through `aitbc exchange-island`
- Know that buy/sell need the validator keystore
- Avoid the retired `/v1/exchange/*` paths

---

## Validation

```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/cli/test_exchange_signs_transactions.py -q
# optional implementation tests, if present:
# ./venv/bin/python -m pytest apps/exchange/tests/test_simple_exchange_b1_b2_b3.py -q -o addopts=""
```

Schema/Decimal/BEGIN IMMEDIATE checks belong in those tests, not in an operator `sqlite3` session.

---

## Related Resources

- [Scenario 06 Basic Trading](./06_basic_trading.md)
- [Next Scenario: Hub↔Customer Node End-to-End](./34_hub_customer_node_e2e.md)

---

*Last updated: 2026-08-21*
*Version: 1.3*
