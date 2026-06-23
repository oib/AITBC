# AITBC Unit System — Compute-Seconds

**Level**: All Levels
**Prerequisites**: None
**Last Updated**: 2026-06-23

## Navigation

Home → Docs → Getting Started → Unit System

---

## Overview

The AITBC blockchain uses a compute-seconds based unit system where **1 AIT = 3600 seconds** (1 hour of compute). This enables precise billing at the second level while maintaining user-friendly AIT values for display.

## Why Compute-Seconds?

Traditional cryptocurrencies use arbitrary units (satoshi, wei) that don't map to real-world value. AITBC is different:

- **AIT represents compute time**: 1 AIT = 1 hour of AI inference compute
- **Second-level precision**: Bill compute resources by the second, not by arbitrary units
- **Natural math**: Seconds are integers, no floating-point arithmetic at the transaction layer
- **User-friendly**: Display layer converts seconds → AIT for readability

## Unit Conversion

### Base Units

| Unit | Value | Description |
|------|-------|-------------|
| 1 AIT | 3600 seconds | 1 hour of compute |
| 1 minute | 60 seconds | Minimum practical billing unit |
| 1 second | 1 unit | Smallest billable unit |

### Transaction Fee

| Metric | Value | Notes |
|--------|-------|-------|
| Transaction fee | 36 seconds (0.01 AIT) | ≈ €0.0025 at €0.25/AIT |
| Minimum fee | 36 seconds | Enforced by consensus |

### Common Amounts

| User-Facing | Internal (seconds) | Description |
|-------------|-------------------|-------------|
| 0.01 AIT | 36 | Transaction fee |
| 1 AIT | 3,600 | 1 hour of compute |
| 100 AIT | 360,000 | Free grant amount |
| 1,000 AIT | 3,600,000 | Typical stake |
| 1,000,000 AIT | 3,600,000,000 | Faucet default |

## How It Works

### On-Chain Storage

All blockchain data is stored as integer seconds:

```sql
-- Account balances
account.balance = 360000  -- 100 AIT stored as 360,000 seconds

-- Transaction values
transaction.value = 7200  -- 2 AIT stored as 7,200 seconds
transaction.fee = 36      -- 0.01 AIT stored as 36 seconds

-- Escrow amounts
escrow.amount = 18000     -- 5 AIT stored as 18,000 seconds
```

### Display Layer Conversion

User-facing interfaces convert seconds → AIT:

```python
from aitbc.utils import format_ait

# Display balance
balance_seconds = 360000
print(format_ait(balance_seconds))  # Output: "100 AIT"

# Display transaction fee
fee_seconds = 36
print(format_ait(fee_seconds))  # Output: "0.01 AIT"
```

### Transaction Creation

When users create transactions, the CLI converts AIT → seconds:

```bash
# User sends 100 AIT
aitbc wallet send --to address --amount 100

# CLI converts internally
amount_seconds = 100 * 3600 = 360000
fee_seconds = 0.01 * 3600 = 36

# Blockchain receives integer seconds
transaction = {
    "value": 360000,
    "fee": 36
}
```

## CLI Usage

### Checking Balances

```bash
# Balance is displayed in AIT
aitbc wallet balance
# Output: Balance: 100 AIT
```

### Sending Transactions

```bash
# Specify amount in AIT (CLI converts to seconds)
aitbc wallet send --to address --amount 50 --fee 0.01
# CLI sends: amount=180000 seconds, fee=36 seconds
```

### Transaction History

```bash
# Amounts shown in AIT
aitbc wallet transactions
# Output: value: 50 AIT, fee: 0.01 AIT
```

## API Responses

API responses include both raw seconds and formatted AIT:

```json
{
  "balance": 360000,
  "balance_ait": "100 AIT",
  "value": 7200,
  "value_ait": "2 AIT",
  "fee": 36,
  "fee_ait": "0.01 AIT"
}
```

## Blockchain Explorer

The explorer displays values in AIT:

- Account balances: `100 AIT` (not `360000`)
- Transaction values: `2 AIT` (not `7200`)
- Transaction fees: `0.01 AIT` (not `36`)

## Migration (v0.5.10 Hard Fork)

The v0.5.10 release introduced the compute-seconds unit system. All existing on-chain data was migrated by multiplying values by 3600:

- **Before**: 1 AIT stored as `1` (raw AIT)
- **After**: 1 AIT stored as `3600` (seconds)

### Migration Script

The migration script `scripts/migration/scale_balances_3600x.py` handles the conversion:

```bash
# Run migration on each node
python3 scripts/migration/scale_balances_3600x.py --chain-id ait-hub.aitbc.bubuit.net

# Flush Redis cache after migration
redis-cli FLUSHDB
```

### What Was Migrated

- Account balances: `balance * 3600`
- Transaction values: `value * 3600`
- Transaction fees: `fee * 3600`
- Receipt minted amounts: `minted_amount * 3600`
- Escrow amounts: `amount * 3600`
- Cross-chain transfers: `amount * 3600`
- Stakes: `amount * 3600`
- Genesis allocations: `balance * 3600`

## Implementation Details

### Conversion Utilities

The `aitbc.utils.units` module provides conversion functions:

```python
from aitbc.utils import SECONDS_PER_AIT, seconds_to_ait, ait_to_seconds, format_ait

# Constants
SECONDS_PER_AIT = 3600

# Convert seconds to AIT (float)
ait = seconds_to_ait(3600)  # Returns: 1.0

# Convert AIT to seconds (int)
seconds = ait_to_seconds(1.0)  # Returns: 3600

# Format as human-readable string
formatted = format_ait(3600)  # Returns: "1 AIT"
formatted = format_ait(36)   # Returns: "0.01 AIT"
```

### Database Schema

All amount/fee/balance columns use `INTEGER` type (seconds):

```sql
CREATE TABLE account (
    address TEXT PRIMARY KEY,
    balance INTEGER NOT NULL,  -- in seconds
    nonce INTEGER DEFAULT 0
);

CREATE TABLE transaction (
    tx_hash TEXT PRIMARY KEY,
    value INTEGER NOT NULL,    -- in seconds
    fee INTEGER NOT NULL,      -- in seconds
    ...
);
```

## Best Practices

### For Developers

1. **Always store seconds**: Database columns and blockchain state use integer seconds
2. **Convert for display**: Use `format_ait()` when showing values to users
3. **Convert input**: Use `ait_to_seconds()` when processing user input in AIT
4. **Document units**: Add comments like `# in compute-seconds (1 AIT = 3600)`

### For Users

1. **Think in AIT**: Use AIT values in CLI commands and API calls
2. **Ignore raw seconds**: The display layer handles conversion automatically
3. **Check explorer**: Use the blockchain explorer to verify values in AIT

## Common Questions

### Q: Why not use floating-point AIT on-chain?

**A**: Floating-point arithmetic can cause rounding errors and consensus issues. Integer seconds are deterministic and precise.

### Q: How do I read raw blockchain data?

**A**: Divide by 3600 to convert seconds to AIT. For example, `balance / 3600 = AIT`.

### Q: What happens if I send a fractional AIT amount?

**A**: The CLI converts it to seconds (e.g., `0.5 AIT → 1800 seconds`). The blockchain stores the integer value.

### Q: Can I send less than 0.01 AIT?

**A**: The minimum transaction fee is 0.01 AIT (36 seconds), but you can send smaller amounts (e.g., 0.001 AIT = 3.6 seconds, rounded to 4 seconds).

## See Also

- [AIT Value Model](./ait-value-model.md) - AIT pricing and economic model
- [Blockchain Architecture](../architecture/4_blockchain-node.md) - Technical implementation
- [v0.5.10 Release Notes](../releases/v0.5.10/change.log) - Hard fork details

---

**Last Updated**: 2026-06-23
**Version**: 1.0
**Status**: Active documentation
