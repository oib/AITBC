"""Give escrow a chain_id and point its account foreign keys at the composite key.

`50fb6691025c` moved the chain to a multi-chain schema: account, block, transaction
and receipt each gained a `chain_id`, and account's primary key became
`(chain_id, address)`. Escrow was not in that migration and kept

    FOREIGN KEY(buyer)    REFERENCES account (address)
    FOREIGN KEY(provider) REFERENCES account (address)

which references a column that is no longer unique on its own. SQLite does not
reject that at CREATE time -- it fails when the constraint is used, and
`PRAGMA foreign_key_check` fails for the *whole database*:

    Error: in prepare, foreign key mismatch - "escrow" referencing "account"

so no table in the chain database could be integrity-checked. V23-64 restored
these foreign keys on purpose; this gives them the shape that actually resolves.

Escrow rows carry no chain marker, so the backfill takes the chain the node's own
blocks were produced on (falling back to account, then to CHAIN_ID/SUPPORTED_CHAINS).

Revision ID: c9a4f1e2b73d
Revises: b7f3c1a90d24
"""

import os

import sqlalchemy as sa
from alembic import op

revision: str = "c9a4f1e2b73d"
down_revision: str | None = "b7f3c1a90d24"
branch_labels: str | None = None
depends_on: str | None = None

BUYER_FK = "fk_escrow_buyer_account"
PROVIDER_FK = "fk_escrow_provider_account"
CHAIN_ID_INDEX = "ix_escrow_chain_id"

# `copy_from` rather than reflection: SQLAlchemy would have to reflect the broken
# constraint to rebuild the table, and what is listed here is what the rebuilt table
# gets -- so the two single-column foreign keys are simply absent from it.
_ESCROW = sa.Table(
    "escrow",
    sa.MetaData(),
    sa.Column("job_id", sa.String(), primary_key=True, nullable=False),
    sa.Column("chain_id", sa.String(), nullable=True),
    sa.Column("buyer", sa.String()),
    sa.Column("provider", sa.String()),
    sa.Column("amount", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("released_at", sa.DateTime()),
    sa.Column("job_tx_hash", sa.String()),
    sa.Column("refunded_at", sa.DateTime()),
    sa.Column("refund_tx_hash", sa.String()),
)


def _resolve_chain_id(bind: sa.engine.Connection) -> str:
    """The chain these escrows belong to.

    Blocks first: a node only ever writes blocks for the chain it runs. Accounts can
    hold rows for a remote chain (`cross_chain/bridge_transfer.py` creates them under
    `record.source_chain` / `record.target_chain`), so they are the weaker signal.
    """
    for table in ("block", "account"):
        try:
            found = bind.execute(
                sa.text(f"SELECT chain_id FROM {table} GROUP BY chain_id ORDER BY count(*) DESC LIMIT 1")  # nosec B608  # noqa: S608
            ).scalar()
        except sa.exc.DatabaseError:
            found = None
        if found:
            return str(found)
    env = os.getenv("CHAIN_ID") or os.getenv("SUPPORTED_CHAINS")
    if not env:
        raise RuntimeError(
            "Cannot tell which chain the escrow rows belong to: no blocks, no accounts, "
            "and neither CHAIN_ID nor SUPPORTED_CHAINS is set."
        )
    return env.split(",")[0].strip()


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column("escrow", sa.Column("chain_id", sa.String(), nullable=True))
    chain_id = _resolve_chain_id(bind)
    bind.execute(sa.text("UPDATE escrow SET chain_id = :chain_id WHERE chain_id IS NULL"), {"chain_id": chain_id})

    with op.batch_alter_table("escrow", schema=None, copy_from=_ESCROW, recreate="always") as batch_op:
        batch_op.alter_column("chain_id", existing_type=sa.String(), nullable=False)
        batch_op.create_index(CHAIN_ID_INDEX, ["chain_id"], unique=False)
        batch_op.create_foreign_key(BUYER_FK, "account", ["chain_id", "buyer"], ["chain_id", "address"])
        batch_op.create_foreign_key(PROVIDER_FK, "account", ["chain_id", "provider"], ["chain_id", "address"])


def downgrade() -> None:
    # Deliberately not symmetric: the pre-upgrade table declared foreign keys against
    # `account.address`, and re-creating them would make `PRAGMA foreign_key_check`
    # unusable across the whole database again. Escrow goes back to having no account
    # foreign keys instead.
    with op.batch_alter_table("escrow", schema=None, recreate="always") as batch_op:
        batch_op.drop_constraint(BUYER_FK, type_="foreignkey")
        batch_op.drop_constraint(PROVIDER_FK, type_="foreignkey")
        batch_op.drop_index(CHAIN_ID_INDEX)
        batch_op.drop_column("chain_id")
