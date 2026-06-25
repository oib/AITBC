# Basic Trading

**Level**: Beginner
**Prerequisites**: Scenario 02 Transaction Sending, Scenario 05 Island Creation
**Estimated Time**: 20 minutes
**Last Updated**: 2026-06-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Basic Trading

---

## See Also

- **Previous Scenario**: [Island Creation](./05_island_creation.md)
- **Next Scenario**: [AI Job Submission](./07_ai_job_submission.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Feature Documentation**: [Exchange Island Commands](../../cli/aitbc_cli/commands/exchange_island.py)

---

## Scenario Overview

This scenario demonstrates how an AI agent trades AIT coin against BTC and ETH on the island exchange. All exchange orders are submitted as blockchain transactions to the island RPC endpoint and matched against the on-chain order book.

### Use Case

An AI agent holds BTC or ETH and wants to acquire AIT to pay for compute jobs, or holds AIT and wants to sell it for BTC/ETH. The agent places limit orders with an optional max/min price, inspects the order book, checks current rates, lists its own open orders, and cancels orders that are no longer needed.

### What You'll Learn

- How to place a buy order for AIT with BTC or ETH
- How to place a sell order for AIT with a minimum price floor
- How to read the order book and current exchange rates for `AIT/BTC` and `AIT/ETH`
- How to list and cancel your own exchange orders

---

## Prerequisites

### Knowledge Required

- Scenario 02 (Transaction Sending) — orders are submitted as blockchain transactions
- Scenario 05 (Island Creation) — you must have joined an island and have island credentials

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- Island credentials saved (run `aitbc node island join` first)
- A validator keystore at `/var/lib/aitbc/keystore/validator_keys.json` (used to derive your node/user ID)

### Setup Required

- Join an island and load credentials (`aitbc node island join`)
- Confirm the island RPC endpoint is reachable (default `http://localhost:8202`)
- Ensure the keystore contains a `public_key_pem` entry — the exchange commands derive your `user_id` from `hostname:ip:p2p_port:public_key_pem`

---

## Step-by-Step Workflow

> **Command group note**: The island trading commands live in the `exchange_island` command group (source: `cli/aitbc_cli/commands/exchange_island.py`, registered in `cli/aitbc_cli/core/main.py`). The separate `exchange` group is the AMM exchange service and does not contain `buy`/`sell`. Use `aitbc exchange_island <subcommand>`.

### Step 1: View current exchange rates

Before placing an order, check the best bid/ask and mid price for both supported pairs (`AIT/BTC`, `AIT/ETH`).

```bash
# Rates are computed from open exchange orders on your island
aitbc exchange_island rates
```

**Expected output:**
```
Exchange Rates
==============
Pair        Best Bid       Best Ask       Mid Price      Buy Orders  Sell Orders
AIT/BTC     0.00001234     0.00001256     0.00001245     7           5
AIT/ETH     0.00023456     0.00023510     0.00023483     4           6
```

### Step 2: Inspect the order book for a pair

Drill into one pair to see the asks (sell orders, sorted ascending by `min_price`) and bids (buy orders, sorted descending by `max_price`).

```bash
# --limit controls the order book depth (default 20)
aitbc exchange_island orderbook AIT/BTC --limit 10
```

**Expected output:**
```
Sell Orders (Asks) - AIT/BTC
============================
Price          Amount         Total              User            Order
0.00001256     50.0000 AIT    0.00062800 BTC     a1b2c3d4e5f6... exchange_sell_...
0.00001270     120.0000 AIT   0.00152400 BTC     f7e8d9c0b1a2... exchange_sell_...

Buy Orders (Bids) - AIT/BTC
===========================
Price          Amount         Total              User            Order
0.00001234     80.0000 AIT    0.00098720 BTC     1a2b3c4d5e6f... exchange_buy_...
0.00001210     200.0000 AIT   0.00242000 BTC     7f8e9d0c1b2a... exchange_buy_...

Spread: 0.00000022 (0.0018%)
Best Bid: 0.00001234 BTC/AIT
Best Ask: 0.00001256 BTC/AIT
```

### Step 3: Place a buy order

Buy AIT using BTC. The `quote_currency` argument must be `BTC` or `ETH`. Use `--max-price` to set a limit; omit it for a market order.

```bash
# Buy 100 AIT with BTC, willing to pay at most 0.00001260 BTC per AIT
aitbc exchange_island buy 100 BTC --max-price 0.00001260
```

**Expected output:**
```
Buy order created successfully!
Order ID: exchange_buy_20260625143012_a1b2c3d4
Buying 100 AIT with BTC
Max price: 0.00001260 BTC/AIT

Order ID    exchange_buy_20260625143012_a1b2c3d4
Pair        AIT/BTC
Side        BUY
Amount      100 AIT
Max Price   0.00001260 BTC/AIT
Status      open
User        a1b2c3d4e5f67890...
Island      island_abc123def456...
```

### Step 4: Place a sell order

Sell AIT for ETH with a minimum acceptable price.

```bash
# Sell 50 AIT for ETH, require at least 0.00023400 ETH per AIT
aitbc exchange_island sell 50 ETH --min-price 0.00023400
```

**Expected output:**
```
Sell order created successfully!
Order ID: exchange_sell_20260625143105_e5f6a7b8
Selling 50 AIT for ETH
Min price: 0.00023400 ETH/AIT

Order ID    exchange_sell_20260625143105_e5f6a7b8
Pair        AIT/ETH
Side        SELL
Amount      50 AIT
Min Price   0.00023400 ETH/AIT
Status      open
User        a1b2c3d4e5f67890...
Island      island_abc123def456...
```

### Step 5: List your exchange orders

Filter the on-chain exchange transactions by status, pair, or user.

```bash
# All open orders on your island
aitbc exchange_island orders --status open

# Only your AIT/ETH orders
aitbc exchange_island orders --pair AIT/ETH --user a1b2c3d4e5f67890...
```

**Expected output:**
```
Exchange Orders (island_abc123def456...)
Order ID                Pair      Side   Amount        Price          Status    User
exchange_buy_20260...   AIT/BTC   BUY    100.0000 AIT  0.00001260     open      a1b2c3d4...
exchange_sell_20260...  AIT/ETH   SELL   50.0000 AIT   0.00023400     open      a1b2c3d4...
```

### Step 6: Cancel an order

Cancel an open order by its order ID. The cancel is submitted as an exchange transaction with `action: cancel` and `status: cancelled`.

```bash
aitbc exchange_island cancel exchange_buy_20260625143012_a1b2c3d4
```

**Expected output:**
```
Order exchange_buy_20260625143012_a1b2c3d4 cancelled successfully!
```

---

## Code Examples Using Agent SDK

The exchange workflow is CLI-driven (orders are blockchain transactions). An AI agent automates it by shelling out to the real `aitbc` CLI. There is no dedicated exchange class in the `aitbc_agent` SDK, so agents use the CLI through their standard operation runner.

### Example 1: Place a buy order and read the order book programmatically

```python
import subprocess
import json

def run(cmd: list[str]) -> str:
    """Run a real aitbc CLI command and return stdout."""
    return subprocess.run(["aitbc", *cmd], capture_output=True, text=True, check=True).stdout

# 1. Inspect the order book (JSON output for parsing)
book = run(["exchange_island", "orderbook", "AIT/BTC", "--limit", "5"])
print(book)

# 2. Place a limit buy: 100 AIT with BTC at max 0.00001260
run(["exchange_island", "buy", "100", "BTC", "--max-price", "0.00001260"])

# 3. Confirm the order is open
orders = run(["exchange_island", "orders", "--status", "open"])
print(orders)
```

### Example 2: Cancel all of your open sell orders

```python
import subprocess
import re

def run(cmd: list[str]) -> str:
    return subprocess.run(["aitbc", *cmd], capture_output=True, text=True, check=True).stdout

# List open sell orders, then cancel each by Order ID
listing = run(["exchange_island", "orders", "--status", "open"])
for line in listing.splitlines():
    if "SELL" in line:
        order_id = line.split()[0]
        run(["exchange_island", "cancel", order_id])
        print(f"Cancelled {order_id}")
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Place buy and sell limit orders for AIT against BTC and ETH on your island
- Read the order book and compute the spread for a trading pair
- Query current exchange rates across both supported pairs
- List and cancel your own exchange orders

---

## Validation

Verify your orders are recorded on-chain by re-listing them and confirming the order book reflects your new orders.

```bash
# Your open orders should include the ones you just placed
aitbc exchange_island orders --status open

# The order book should show your bid/ask
aitbc exchange_island orderbook AIT/BTC
aitbc exchange_island orderbook AIT/ETH

# Rates should reflect the updated book
aitbc exchange_island rates
```

---

## Related Resources

- Source: `cli/aitbc_cli/commands/exchange_island.py` (buy, sell, orderbook, rates, orders, cancel)
- Registration: `cli/aitbc_cli/core/main.py` (`cli.add_command(exchange_island)`)
- [Next Scenario: AI Job Submission](./07_ai_job_submission.md)

---

*Last updated: 2026-06-25*
*Version: 1.0*
