"""Fix transaction block foreign key

Revision ID: fix_transaction_block_foreign_key
Revises: 
Create Date: 2026-01-29 12:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fix_transaction_block_foreign_key'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Drop existing foreign key constraint (unnamed, SQLite auto-generated)
    # In SQLite, we need to recreate the table
    
    # Create new transaction table with correct foreign key
    op.execute("""
        CREATE TABLE transaction_new (
            id INTEGER NOT NULL PRIMARY KEY,
            tx_hash VARCHAR NOT NULL,
            block_height INTEGER,
            sender VARCHAR NOT NULL,
            recipient VARCHAR NOT NULL,
            payload JSON NOT NULL,
            created_at DATETIME NOT NULL,
            FOREIGN KEY(block_height) REFERENCES block(id)
        )
    """)
    
    # Copy data from old table
    op.execute("""
        INSERT INTO transaction_new (id, tx_hash, block_height, sender, recipient, payload, created_at)
        SELECT id, tx_hash, block_height, sender, recipient, payload, created_at FROM transaction
    """)
    
    # Drop old table and rename new one
    op.execute("DROP TABLE transaction")
    op.execute("ALTER TABLE transaction_new RENAME TO transaction")
    
    # Recreate indexes
    op.execute("CREATE UNIQUE INDEX ix_transaction_tx_hash ON transaction (tx_hash)")
    op.execute("CREATE INDEX ix_transaction_block_height ON transaction (block_height)")
    op.execute("CREATE INDEX ix_transaction_created_at ON transaction (created_at)")


def downgrade():
    # Revert back to referencing block.height
    
    # Create new transaction table with old foreign key
    op.execute("""
        CREATE TABLE transaction_new (
            id INTEGER NOT NULL PRIMARY KEY,
            tx_hash VARCHAR NOT NULL,
            block_height INTEGER,
            sender VARCHAR NOT NULL,
            recipient VARCHAR NOT NULL,
            payload JSON NOT NULL,
            created_at DATETIME NOT NULL,
            FOREIGN KEY(block_height) REFERENCES block(height)
        )
    """)
    
    # Copy data from old table
    op.execute("""
        INSERT INTO transaction_new (id, tx_hash, block_height, sender, recipient, payload, created_at)
        SELECT id, tx_hash, block_height, sender, recipient, payload, created_at FROM transaction
    """)
    
    # Drop old table and rename new one
    op.execute("DROP TABLE transaction")
    op.execute("ALTER TABLE transaction_new RENAME TO transaction")
    
    # Recreate indexes
    op.execute("CREATE UNIQUE INDEX ix_transaction_tx_hash ON transaction (tx_hash)")
    op.execute("CREATE INDEX ix_transaction_block_height ON transaction (block_height)")
    op.execute("CREATE INDEX ix_transaction_created_at ON transaction (created_at)")
