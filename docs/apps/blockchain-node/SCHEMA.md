# Blockchain Node Database Schema

This document describes the SQLModel schema for the AITBC blockchain node.

## Overview

The blockchain node uses SQLite for local storage with SQLModel (SQLAlchemy + Pydantic).

## Tables

### Block

Stores blockchain blocks.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY | Auto-increment ID |
| `chain_id` | VARCHAR | INDEX, UNIQUE(chain_id, height), UNIQUE(chain_id, hash) | Chain this block belongs to |
| `height` | INTEGER | INDEX | Block height |
| `hash` | VARCHAR | INDEX | Block hash (hex) |
| `parent_hash` | VARCHAR | INDEX | Parent block hash |
| `proposer` | VARCHAR | | Block proposer address |
| `timestamp` | DATETIME | INDEX | Block timestamp |
| `tx_count` | INTEGER | | Transaction count |
| `state_root` | VARCHAR | NULLABLE | State root hash |
| `bridge_state_root` | VARCHAR | NULLABLE | Bridge event trie root (used for Merkle proof verification) |
| `block_metadata` | VARCHAR | NULLABLE | JSON metadata (consensus stamps, versions) |
| `signature` | VARCHAR | | Proposer secp256k1 signature over the block hash (v0.7.1+; empty on legacy blocks) |

`height` and `hash` are **not globally unique** — the unique constraints are
the composite `(chain_id, height)` and `(chain_id, hash)`.

**Relationships:**

- `transactions` → Transaction (one-to-many, joined on `block_height` + `chain_id`)
- `receipts` → Receipt (one-to-many, joined on `block_height` + `chain_id`)

### Transaction

Stores transactions.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY | Auto-increment ID |
| `chain_id` | VARCHAR | INDEX, UNIQUE(chain_id, tx_hash), INDEX(chain_id, block_height) | Chain this tx belongs to |
| `tx_hash` | VARCHAR | INDEX | Transaction hash (hex) |
| `block_height` | INTEGER | NULLABLE, INDEX | Block containing this tx (joined to Block via `(chain_id, block_height)`, not a column FK) |
| `sender` | VARCHAR | INDEX | Sender address — verbatim column (`from` in the signed message) |
| `recipient` | VARCHAR | INDEX | Recipient address — verbatim column (`to` in the signed message) |
| `payload` | JSON | | Transaction data |
| `created_at` | DATETIME | INDEX | Creation timestamp |
| `nonce` | INTEGER | | Sender nonce |
| `value` | INTEGER | | Transfer amount in compute-units (1 AIT = 36,000,000) |
| `fee` | INTEGER | | Fee in compute-units |
| `type` | VARCHAR | INDEX | `TRANSFER`, `MESSAGE`, `RECEIPT_CLAIM`, `GPU_MARKETPLACE`, `EXCHANGE`, ... |
| `status` | VARCHAR | | `pending`, `confirmed`, ... |
| `timestamp` | VARCHAR | NULLABLE | Client-supplied timestamp |
| `tx_metadata` | VARCHAR | NULLABLE | JSON metadata |

`sender`/`recipient` are stored verbatim — normalising them would change the
signed message bytes and break signature recovery; lookups canonicalise the
search value instead.

**Relationships:**

- `block` → Block (many-to-one, composite join on `block_height` + `chain_id`)

### Receipt

Stores job completion receipts.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY | Auto-increment ID |
| `chain_id` | VARCHAR | INDEX, UNIQUE(chain_id, receipt_id) | Chain this receipt belongs to |
| `job_id` | VARCHAR | INDEX | Job identifier |
| `receipt_id` | VARCHAR | INDEX | Receipt hash (hex) |
| `block_height` | INTEGER | NULLABLE, INDEX | Block containing receipt (composite join, not a column FK) |
| `payload` | JSON | | Receipt payload |
| `miner_signature` | JSON | | Miner's signature |
| `coordinator_attestations` | JSON | | Coordinator attestations |
| `minted_amount` | INTEGER | NULLABLE | Tokens minted (compute-units) |
| `recorded_at` | DATETIME | INDEX | Recording timestamp |
| `status` | VARCHAR | INDEX | `pending`, `claimed`, `invalid` |
| `claimed_at` | DATETIME | NULLABLE | When the receipt was claimed |
| `claimed_by` | VARCHAR | NULLABLE | Address that claimed it |

**Relationships:**

- `block` → Block (many-to-one)

### Account

Stores account balances.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `chain_id` | VARCHAR | PRIMARY KEY (composite) | Chain this account row belongs to |
| `address` | VARCHAR (EvmAddress) | PRIMARY KEY (composite) | Account address — canonicalised to EIP-55 `0x` 40-hex on write and read |
| `balance` | BIGINT | | Token balance in compute-units (1 AIT = 36,000,000) |
| `nonce` | BIGINT | | Transaction nonce |
| `updated_at` | DATETIME | | Last update time |

The primary key is the composite `(chain_id, address)` — the same address can
hold a balance on every chain. `address` uses the `EvmAddress` type
decorator, so all inserts and lookups are normalised to the EIP-55 checksum
spelling.

## Entity Relationship Diagram

```
┌──────────────────┐
│   Block          │
├──────────────────┤
│ id (PK)          │
│ chain_id         │◄─────────────┐
│ height           │  UQ(chain_id,│  ┌────────────────┐
│ hash             │    height)   │  │ UQ(chain_id,   │
│ parent_hash      │              │  │   hash)        │
│ proposer         │              │  └────────────────┘
│ timestamp        │              │
│ tx_count         │              │
│ state_root       │              │
│ bridge_state_root│              │
│ block_metadata   │              │
│ signature        │              │
└──────────────────┘              │
      │                           │
      │ 1:N (chain_id,            │ 1:N (chain_id,
      │      block_height)        │      block_height)
      ▼                           ▼
┌──────────────┐          ┌──────────────┐
│ Transaction  │          │   Receipt    │
├──────────────┤          ├──────────────┤
│ id (PK)      │          │ id (PK)      │
│ chain_id     │          │ chain_id     │
│ tx_hash      │          │ job_id       │
│ block_height │          │ receipt_id   │
│ sender       │          │ block_height │
│ recipient    │          │ payload      │
│ payload      │          │ miner_sig    │
│ nonce        │          │ attestations │
│ value        │          │ minted_amt   │
│ fee          │          │ recorded_at  │
│ type         │          │ status       │
│ status       │          │ claimed_at   │
│ created_at   │          │ claimed_by   │
└──────────────┘          └──────────────┘

┌──────────────────┐
│   Account        │
├──────────────────┤
│ chain_id (PK)    │
│ address (PK)     │  PK = (chain_id, address)
│ balance          │
│ nonce            │
│ updated_at       │
└──────────────────┘
```

## Validation

**Important:** SQLModel with `table=True` does not run Pydantic field validators on model instantiation. Validation must be performed at the API/service layer before creating model instances.

See: https://github.com/tiangolo/sqlmodel/issues/52

### Hex Validation

The following fields should be validated as hex strings before insertion:

- `Block.hash`
- `Block.parent_hash`
- `Block.state_root`
- `Block.bridge_state_root`
- `Transaction.tx_hash`
- `Receipt.receipt_id`

## Migrations

### Initial Setup

```python
from aitbc_chain.database import init_db
init_db(chain_id)  # Creates all tables for the given chain
```

### Alembic (Production)

Alembic is the production migration path. Migrations live in
`apps/blockchain-node/migrations/` (`migrations/versions/` for the revisions)
with `alembic.ini` at `apps/blockchain-node/`. Existing revisions cover the
`(chain_id, address)` composite account key (`50fb6691025c`), block
relationships (`80bc0020bde2`), the transaction payload job-id index
(`b7f3c1a90d24`), and the chain-scoped escrow FKs (`c9a4f1e2b73d`), among
others.

```bash
cd /opt/aitbc/apps/blockchain-node

# Apply all pending migrations
/opt/aitbc/venv/bin/alembic upgrade head

# Generate a new migration
alembic revision --autogenerate -m "description"
```

Each chain database (`<AITBC_DATA_DIR>/data/<chain_id>/chain.db`) is migrated
independently.

## Usage Examples

### Creating a Block with Transactions

```python
from aitbc_chain.base_models import Block, Transaction
from aitbc_chain.database import session_scope

with session_scope("ait-mainnet") as session:
    block = Block(
        chain_id="ait-mainnet",
        height=1,
        hash="0x" + "a" * 64,
        parent_hash="0x" + "0" * 64,
        proposer="0x" + "c" * 40,
    )
    session.add(block)
    session.commit()

    tx = Transaction(
        chain_id="ait-mainnet",
        tx_hash="0x" + "b" * 64,
        block_height=block.height,
        sender="0x" + "d" * 40,
        recipient="0x" + "e" * 40,
        value=100,
        fee=360000,
        payload={"amount": 100}
    )
    session.add(tx)
    session.commit()
```

### Querying with Relationships

```python
from sqlmodel import select

with session_scope("ait-mainnet") as session:
    # Get block with transactions
    block = session.exec(
        select(Block).where(
            Block.chain_id == "ait-mainnet", Block.height == 1
        )
    ).first()

    # Access related transactions (lazy loaded)
    for tx in block.transactions:
        print(f"TX: {tx.tx_hash}")
```
