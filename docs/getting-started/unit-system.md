# AITBC Unit System — Compute-Units

**Level**: All Levels
**Prerequisites**: None
**Last Updated**: 2026-08-24

## Navigation

Home → Docs → Getting Started → Unit System

---

## Overview

The AITBC blockchain uses **compute-units** as its base accounting unit. The conversion is fixed:

**1 AIT = 36,000,000 compute-units**

A compute-unit is an **integer** on the wire. User-facing tools and APIs still work in AIT; the CLI and display layer convert AIT to and from compute-units.

## Why 36,000,000?

The previous `1 AIT = 3600` (compute-seconds) scale was too coarse:

- The smallest representable payment was `0.000277... AIT`, which loses sub-second AI work.
- The marketplace platform fee (2.5%) could not be represented for small jobs.
- Sub-AIT escrow values truncated to zero in the `Escrow` DB table.

The 36,000,000 scale keeps the integer-money design but adds 10,000× precision:

- Smallest unit: `1 / 36,000,000 AIT` ≈ `2.78 × 10⁻⁸ AIT`
- 1 Ollama token at `0.001 AIT / 1000 tokens` = `0.000001 AIT` = `36` compute-units
- 2.5% fee on 1 token = `0.9` compute-units → round up to `1` compute-unit

## Unit Conversion

### Base Units

| Unit | Value | Description |
|------|-------|-------------|
| 1 AIT | 36,000,000 units | Base conversion |
| 1 unit | 2.78 × 10⁻⁸ AIT | Smallest representable amount |

### Transaction Fee

| Metric | Value | Notes |
|--------|-------|-------|
| Transaction fee | 360,000 units (0.01 AIT) | Default network fee |
| Minimum fee | 360,000 units | Enforced by consensus |

### Common Amounts

| User-Facing | Internal (units) | Description |
|-------------|------------------|-------------|
| 0.01 AIT | 360,000 | Transaction fee |
| 1 AIT | 36,000,000 | Base unit |
| 100 AIT | 3,600,000,000 | Free grant amount |
| 1,000 AIT | 36,000,000,000 | Typical stake |
| 1,000,000 AIT | 36,000,000,000,000,000 | Faucet default |

## How It Works

### On-Chain Storage

All blockchain data is stored as integer compute-units:

```sql
-- Account balances
account.balance = 3600000000  -- 100 AIT stored as 3,600,000,000 units

-- Transaction values
transaction.value = 72000000  -- 2 AIT stored as 72,000,000 units
transaction.fee = 360000      -- 0.01 AIT stored as 360,000 units

-- Escrow amounts
escrow.amount = 180000000     -- 5 AIT stored as 180,000,000 units
```

### Display Layer Conversion

User-facing interfaces convert units → AIT:

```python
from aitbc.utils import format_ait

# Display balance
balance_units = 3600000000
print(format_ait(balance_units))  # Output: "100 AIT"

# Display transaction fee
fee_units = 360000
print(format_ait(fee_units))  # Output: "0.01 AIT"

# Display a single compute-unit
print(format_ait(1))  # Output: "0.00000003 AIT"
```

### Transaction Creation

When users create transactions, the CLI converts AIT → compute-units:

```bash
# User sends 100 AIT
aitbc wallet send --to address --amount 100

# CLI converts internally
amount_units = 100 * 36000000 = 3600000000
fee_units = 0.01 * 36000000 = 360000

# Blockchain receives integer units
transaction = {
    "value": 3600000000,
    "fee": 360000
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
# Specify amount in AIT (CLI converts to units)
aitbc wallet send --to address --amount 50 --fee 0.01
# CLI sends: amount=1800000000 units, fee=360000 units
```

### Transaction History

```bash
# Amounts shown in AIT
aitbc wallet transactions
# Output: value: 50 AIT, fee: 0.01 AIT
```

## API Responses

API responses include both raw compute-units and formatted AIT where useful:

```json
{
  "balance": 3600000000,
  "balance_ait": "100 AIT",
  "value": 72000000,
  "value_ait": "2 AIT",
  "fee": 360000,
  "fee_ait": "0.01 AIT"
}
```

## Blockchain Explorer

The explorer displays values in AIT:

- Account balances: `100 AIT` (not `3600000000`)
- Transaction values: `2 AIT` (not `72000000`)
- Transaction fees: `0.01 AIT` (not `360000`)

## Migration (v0.24.0 Hard Fork)

The v0.24.0 release replaced the `1 AIT = 3600` compute-seconds scale with `1 AIT = 36,000,000` compute-units. Because this changes the wire value of every transaction and state root, it requires a coordinated chain reset:

- **Before v0.24.0**: 1 AIT stored as `3600` compute-seconds
- **After v0.24.0**: 1 AIT stored as `36,000,000` compute-units

Nodes must be upgraded together, old chain databases must be wiped, and a new genesis block must be generated before services restart. The old `scripts/migration/scale_balances_3600x.py` script is **not** used; a new genesis is created instead.

## Implementation Details

### Conversion Utilities

The `aitbc.utils.units` module provides conversion functions:

```python
from aitbc.utils import UNITS_PER_AIT, ait_to_units, units_to_ait, format_ait

# Constants
UNITS_PER_AIT = 36_000_000
DEFAULT_TX_FEE_UNITS = 360_000  # 0.01 AIT
LIQUIDITY_FEE_UNITS = 36_000_000  # 1 AIT
DEFAULT_FAUCET_UNITS = 36_000_000_000_000_000  # 1,000,000 AIT

# Convert units to AIT (Decimal)
ait = units_to_ait(36000000)  # Returns: Decimal("1")

# Convert AIT to units (int)
units = ait_to_units("1.5")  # Returns: 54000000

# Format as human-readable string
formatted = format_ait(36000000)   # Returns: "1 AIT"
formatted = format_ait(360000)     # Returns: "0.01 AIT"
formatted = format_ait(1)          # Returns: "0.00000003 AIT"
```

### Database Schema

All amount/fee/balance columns use `INTEGER` type (compute-units):

```sql
CREATE TABLE account (
    address TEXT PRIMARY KEY,
    balance INTEGER NOT NULL,  -- in compute-units
    nonce INTEGER DEFAULT 0
);

CREATE TABLE transaction (
    tx_hash TEXT PRIMARY KEY,
    value INTEGER NOT NULL,    -- in compute-units
    fee INTEGER NOT NULL,      -- in compute-units
    ...
);
```

## Best Practices

### For Developers

1. **Always store units**: Database columns and blockchain state use integer compute-units
2. **Convert for display**: Use `format_ait()` when showing values to users
3. **Convert input**: Use `ait_to_units()` when processing user input in AIT
4. **Document units**: Add comments like `# in compute-units (1 AIT = 36_000_000)`

### For Users

1. **Think in AIT**: Use AIT values in CLI commands and API calls
2. **Ignore raw units**: The display layer handles conversion automatically
3. **Check explorer**: Use the blockchain explorer to verify values in AIT

## Common Questions

### Q: Why not use floating-point AIT on-chain?

**A**: Floating-point arithmetic can cause rounding errors and consensus issues. Integer compute-units are deterministic and precise.

### Q: How do I read raw blockchain data?

**A**: Divide by `36,000,000` to convert units to AIT. For example, `balance / 36_000_000 = AIT`.

### Q: What happens if I send a fractional AIT amount?

**A**: The CLI converts it to compute-units (e.g., `0.5 AIT → 18,000,000 units`). The blockchain stores the integer value.

### Q: Can I send less than 0.01 AIT?

**A**: The minimum transaction fee is 0.01 AIT (360,000 units), but you can send smaller amounts (e.g., `0.000001 AIT = 36 units`). Positive sub-fee payments round up to `1` compute-unit when necessary.

## See Also

- [AIT Value Model](./ait-value-model.md) - AIT pricing and economic model
- [Blockchain Architecture](../architecture/4_blockchain-node.md) - Technical implementation
- [v0.24.0 Release Notes](../releases/v0.24.0/change.log) - Hard fork details

---

**Last Updated**: 2026-08-24
**Version**: 2.0
**Status**: Active documentation
