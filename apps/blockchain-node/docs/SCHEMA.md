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
| `height` | INTEGER | UNIQUE, INDEX | Block height |
| `hash` | VARCHAR | UNIQUE, INDEX | Block hash (hex) |
| `parent_hash` | VARCHAR | | Parent block hash |
| `proposer` | VARCHAR | | Block proposer address |
| `timestamp` | DATETIME | INDEX | Block timestamp |
| `tx_count` | INTEGER | | Transaction count |
| `state_root` | VARCHAR | NULLABLE | State root hash |

**Relationships:**
- `transactions` → Transaction (one-to-many)
- `receipts` → Receipt (one-to-many)

### Transaction

Stores transactions.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY | Auto-increment ID |
| `tx_hash` | VARCHAR | UNIQUE, INDEX | Transaction hash (hex) |
| `block_height` | INTEGER | FK → block.height, INDEX | Block containing this tx |
| `sender` | VARCHAR | | Sender address |
| `recipient` | VARCHAR | | Recipient address |
| `payload` | JSON | | Transaction data |
| `created_at` | DATETIME | INDEX | Creation timestamp |

**Relationships:**
- `block` → Block (many-to-one)

### Receipt

Stores job completion receipts.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY | Auto-increment ID |
| `job_id` | VARCHAR | INDEX | Job identifier |
| `receipt_id` | VARCHAR | UNIQUE, INDEX | Receipt hash (hex) |
| `block_height` | INTEGER | FK → block.height, INDEX | Block containing receipt |
| `payload` | JSON | | Receipt payload |
| `miner_signature` | JSON | | Miner's signature |
| `coordinator_attestations` | JSON | | Coordinator attestations |
| `minted_amount` | INTEGER | NULLABLE | Tokens minted |
| `recorded_at` | DATETIME | INDEX | Recording timestamp |

**Relationships:**
- `block` → Block (many-to-one)

### Account

Stores account balances.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `address` | VARCHAR | PRIMARY KEY | Account address |
| `balance` | INTEGER | | Token balance |
| `nonce` | INTEGER | | Transaction nonce |
| `updated_at` | DATETIME | | Last update time |

## Entity Relationship Diagram

```
┌─────────────┐
│   Block     │
├─────────────┤
│ id          │
│ height (UK) │◄──────────────┐
│ hash (UK)   │               │
│ parent_hash │               │
│ proposer    │               │
│ timestamp   │               │
│ tx_count    │               │
│ state_root  │               │
└─────────────┘               │
      │                       │
      │ 1:N                   │ 1:N
      ▼                       ▼
┌─────────────┐       ┌─────────────┐
│ Transaction │       │   Receipt   │
├─────────────┤       ├─────────────┤
│ id          │       │ id          │
│ tx_hash(UK) │       │ job_id      │
│ block_height│       │ receipt_id  │
│ sender      │       │ block_height│
│ recipient   │       │ payload     │
│ payload     │       │ miner_sig   │
│ created_at  │       │ attestations│
└─────────────┘       │ minted_amt  │
                      │ recorded_at │
                      └─────────────┘

┌─────────────┐
│   Account   │
├─────────────┤
│ address(PK) │
│ balance     │
│ nonce       │
│ updated_at  │
└─────────────┘
```

## Validation

**Important:** SQLModel with `table=True` does not run Pydantic field validators on model instantiation. Validation must be performed at the API/service layer before creating model instances.

See: https://github.com/tiangolo/sqlmodel/issues/52

### Hex Validation

The following fields should be validated as hex strings before insertion:
- `Block.hash`
- `Block.parent_hash`
- `Block.state_root`
- `Transaction.tx_hash`
- `Receipt.receipt_id`

## Migrations

### Initial Setup

```python
from aitbc_chain.database import init_db
init_db()  # Creates all tables
```

### Alembic (Future)

For production, use Alembic for migrations:

```bash
# Initialize Alembic
alembic init migrations

# Generate migration
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head
```

## Usage Examples

### Creating a Block with Transactions

```python
from aitbc_chain.models import Block, Transaction
from aitbc_chain.database import session_scope

with session_scope() as session:
    block = Block(
        height=1,
        hash="0x" + "a" * 64,
        parent_hash="0x" + "0" * 64,
        proposer="validator1"
    )
    session.add(block)
    session.commit()
    
    tx = Transaction(
        tx_hash="0x" + "b" * 64,
        block_height=block.height,
        sender="alice",
        recipient="bob",
        payload={"amount": 100}
    )
    session.add(tx)
    session.commit()
```

### Querying with Relationships

```python
from sqlmodel import select

with session_scope() as session:
    # Get block with transactions
    block = session.exec(
        select(Block).where(Block.height == 1)
    ).first()
    
    # Access related transactions (lazy loaded)
    for tx in block.transactions:
        print(f"TX: {tx.tx_hash}")
```
