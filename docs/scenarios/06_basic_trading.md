# Basic Trading

**Level**: Beginner
**Prerequisites**: Scenario 02 Transaction Sending, Scenario 05 Island Creation
**Estimated Time**: 20 minutes
**Last Updated**: 2026-08-21
**Version**: 1.3

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

> **Live vs. simulated:** `aitbc exchange-island` commands are **live** when the exchange service (port 8106) is running. If the exchange is unreachable, the CLI returns `(Simulated)` orderbook/orders.

This scenario demonstrates how to trade AIT against **ETH** on the island exchange via `aitbc exchange-island`. The live CLI pair set is `AIT/ETH` only (`SUPPORTED_PAIRS`). `buy` / `sell` / `cancel` sign the exchange transaction with a wallet (`--wallet`, defaults to the active wallet); `rates`, `orderbook`, and `orders` do not.

### Use Case

A customer wants to inspect the AIT/ETH book and, given a signing wallet, place a limit buy or sell.

### What You'll Learn

- How to read `aitbc exchange-island rates` / `orderbook --pair AIT/ETH` / `orders`
- How to place a buy (`ETH`) or sell with a min price and `--wallet`
- How to cancel an open order

---

## Prerequisites

### Knowledge Required

- Scenario 02 (Transaction Sending) — orders are submitted as blockchain transactions
- Scenario 05 (Island Creation) — you must have joined an island and have island credentials

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- Island credentials saved (run `aitbc node island join` first)
- A wallet with a usable private key (e.g. `default` under `/var/lib/aitbc/wallets/`) — your order `user_id` is the wallet address

### Setup Required

- Join an island and load credentials (`aitbc node island join`)
- Confirm the island RPC endpoint is reachable (default `http://localhost:8202`)
- Pass `--wallet <name>` (and `--password` if the wallet is encrypted); the exchange commands sign with it and use its address as `user_id`

---

## Step-by-Step Workflow

> **Command group note**: The island trading commands live in the `exchange-island` command group (source: `cli/aitbc_cli/commands/exchange_island.py`, registered in `cli/aitbc_cli/core/main.py`). The separate `exchange` group is the AMM exchange service and does not contain `buy`/`sell`. Use `aitbc exchange-island <subcommand>`.

### Step 1: View current exchange rates

Before placing an order, check the best bid/ask for `AIT/ETH`.

```bash
# Rates are computed from open exchange orders on your island
aitbc exchange-island rates
```

**Expected output:**

```
Exchange Rates
==============
Pair        Best Bid       Best Ask       Mid Price      Buy Orders  Sell Orders
AIT/ETH     0.00023456     0.00023510     0.00023483     4           6
```

### Step 2: Inspect the order book for a pair

Drill into one pair to see the asks (sell orders, sorted ascending by `min_price`) and bids (buy orders, sorted descending by `max_price`).

```bash
# --limit controls the order book depth (default 20)
aitbc exchange-island orderbook --pair AIT/ETH --limit 10
```

**Expected output:**

```
Sell Orders (Asks) - AIT/ETH
============================
Price          Amount         Total              User            Order
0.00023510     50.0000 AIT    0.01175500 ETH     a1b2c3d4e5f6... exchange_sell_...

Buy Orders (Bids) - AIT/ETH
===========================
Price          Amount         Total              User            Order
0.00023456     80.0000 AIT    0.01876480 ETH     1a2b3c4d5e6f... exchange_buy_...

Spread: 0.00000054
Best Bid: 0.00023456 ETH/AIT
Best Ask: 0.00023510 ETH/AIT
```

### Step 3: Place a buy order

Buy AIT using ETH. The `quote_currency` argument must be `ETH`. Use `--max-price` to set a limit; omit it for a market order. Aborts if the wallet has no usable private key.

```bash
# Buy 100 AIT with ETH, willing to pay at most 0.00023510 ETH per AIT
aitbc exchange-island buy --ait-amount 100 --quote-currency ETH --max-price 0.00023510
```

**Expected output:**

```
Buy order created successfully!
Order ID: exchange_buy_20260625143012_a1b2c3d4
Buying 100 AIT with ETH
Max price: 0.00023510 ETH/AIT

Order ID    exchange_buy_20260625143012_a1b2c3d4
Pair        AIT/ETH
Side        BUY
Amount      100 AIT
Max Price   0.00023510 ETH/AIT
Status      open
User        a1b2c3d4e5f67890...
Island      island_abc123def456...
```

### Step 4: Place a sell order

Sell AIT for ETH with a minimum acceptable price.

```bash
# Sell 50 AIT for ETH, require at least 0.00023400 ETH per AIT
aitbc exchange-island sell --ait-amount 50 --quote-currency ETH --min-price 0.00023400
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
aitbc exchange-island orders --status open

# Only your AIT/ETH orders
aitbc exchange-island orders --pair AIT/ETH --user a1b2c3d4e5f67890...
```

**Expected output:**

```
Exchange Orders (island_abc123def456...)
Order ID                Pair      Side   Amount        Price          Status    User
exchange_buy_20260...   AIT/ETH   BUY    100.0000 AIT  0.00023510     open      a1b2c3d4...
exchange_sell_20260...  AIT/ETH   SELL   50.0000 AIT   0.00023400     open      a1b2c3d4...
```

### Step 6: Cancel an order

Cancel an open order by its order ID. The cancel is submitted as a signed exchange transaction with `action: cancel` and `status: cancelled` — the signing wallet must be the order's owner.

```bash
aitbc exchange-island cancel --order-id exchange_buy_20260625143012_a1b2c3d4 --wallet default
```

**Expected output:**

```
Order exchange_buy_20260625143012_a1b2c3d4 cancelled successfully! tx: 0x…
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
book = run(["exchange-island", "orderbook", "--pair", "AIT/ETH", "--limit", "5"])
print(book)

# 2. Place a limit buy: 100 AIT with ETH at max 0.00023510
run(["exchange-island", "buy", "--ait-amount", "100", "--quote-currency", "ETH", "--max-price", "0.00023510"])

# 3. Confirm the order is open
orders = run(["exchange-island", "orders", "--status", "open"])
print(orders)
```

### Example 2: Cancel all of your open sell orders

```python
import subprocess
import re

def run(cmd: list[str]) -> str:
    return subprocess.run(["aitbc", *cmd], capture_output=True, text=True, check=True).stdout

# List open sell orders, then cancel each by Order ID
listing = run(["exchange-island", "orders", "--status", "open"])
for line in listing.splitlines():
    if "SELL" in line:
        order_id = line.split()[0]
        run(["exchange-island", "cancel", "--order-id", order_id])
        print(f"Cancelled {order_id}")
```

---


---

<!-- PLAY3 coverage extension: uncovered CLI leaves folded into this scenario (issue #438) -->

### Step 7: List configured exchanges

Shows the exchanges registered in the local configuration.

```bash
aitbc exchange list
```

### Step 8: Monitor an exchange

Streams order-book and trade updates for a pair.

```bash
aitbc exchange monitor --pair AIT/USDC --exchange local
```

### Step 9: List exchange nodes

Lists exchange nodes known to the coordinator.

```bash
aitbc exchange node list
```

### Step 10: Read the order book

Prints the current order book.

```bash
aitbc exchange order book
```

### Step 11: Check sell-admin status

Reads the exchange sell-side admin service status from the hub.

```bash
aitbc exchange sell_admin status
```

### Step 12: Check one exchange's status

Prints health and configuration of a named exchange.

```bash
aitbc exchange status --exchange-name local
```

### Step 13: Verify exchange accounting

Runs the exchange's financial-consistency verification over its databases.

```bash
aitbc exchange verify
```

### Step 14: Register an external exchange

`aitbc exchange register --name ext --api-key REDACTED` is stores external exchange API credentials — a key/secret operation; not played, needs the operator's line.

### Step 15: Add liquidity to a pair

Adds liquidity to an exchange pair.

Cost: 36_000_000 units (1 AIT at UNITS_PER_AIT = 36_000_000) locked in the pool.

```bash
aitbc exchange add-liquidity --pair AIT/USDC --amount 36000000 --side both
```

### Step 16: Create a trading pair

Creates a new pair on the named exchange.

Cost: 0 units — config write only.

```bash
aitbc exchange create-pair --base-asset AIT --quote-asset USDC --exchange local
```

### Step 17: Fund a prepared order

Pays the escrowed funds for a prepared order.

Cost: order amount in units (UNITS_PER_AIT = 36_000_000) plus fee.

```bash
aitbc exchange order fund ord-123
```

### Step 18: Make a prepay deposit

Sends an ETH prepayment into the exchange deposit contract.

Cost: 0.001 ETH = 1_000_000_000_000_000 wei.

```bash
aitbc exchange prepay deposit --amount-eth 0.001 --send
```

### Step 19: Set the node payout address

Registers the Ethereum address exchange payouts settle to.

Cost: 0 units — config write only.

```bash
aitbc exchange node set-payout --eth-address 0xPayoutAddress
```

### Step 20: Start trading on a pair

Enables trading on a pair that was created halted.

Cost: liquidity budgets in units (UNITS_PER_AIT = 36_000_000) when --base-liquidity/--quote-liquidity are passed.

```bash
aitbc exchange start-trading --pair AIT/USDC
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Read the AIT/ETH order book and rates through `aitbc exchange-island`
- Place buy/sell orders with a signing wallet
- List and cancel your own exchange orders

---

## Validation

Verify your orders are recorded on-chain by re-listing them and confirming the order book reflects your new orders.

```bash
# Your open orders should include the ones you just placed
aitbc exchange-island orders --status open

# The order book should show your bid/ask
aitbc exchange-island orderbook --pair AIT/ETH

# Rates should reflect the updated book
aitbc exchange-island rates
```

---

## Related Resources

- Source: `cli/aitbc_cli/commands/exchange_island.py` (buy, sell, orderbook, rates, orders, cancel)
- Registration: `cli/aitbc_cli/core/main.py` (`cli.add_command(exchange-island)`)
- [Next Scenario: AI Job Submission](./07_ai_job_submission.md)

---

*Last updated: 2026-08-21*
*Version: 1.3*
