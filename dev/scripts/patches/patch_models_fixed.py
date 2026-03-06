import re

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/models.py", "r") as f:
    content = f.read()

# First fix the `__table_args__` import
content = content.replace(
    "from sqlmodel import Field, Relationship, SQLModel",
    "from sqlmodel import Field, Relationship, SQLModel\nfrom sqlalchemy import UniqueConstraint"
)

# Fix Block model
content = content.replace(
    """class Block(SQLModel, table=True):
    __tablename__ = "block"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    height: int = Field(index=True, unique=True)
    hash: str = Field(index=True, unique=True)""",
    """class Block(SQLModel, table=True):
    __tablename__ = "block"
    __table_args__ = (UniqueConstraint("chain_id", "height", name="uix_block_chain_height"),)
    
    id: Optional[int] = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    height: int = Field(index=True)
    hash: str = Field(index=True, unique=True)"""
)

# Fix Transaction model
content = content.replace(
    """class Transaction(SQLModel, table=True):
    __tablename__ = "transaction"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    tx_hash: str = Field(index=True, unique=True)
    block_height: Optional[int] = Field(
        default=None,
        index=True,
        foreign_key="block.height",
    )""",
    """class Transaction(SQLModel, table=True):
    __tablename__ = "transaction"
    __table_args__ = (UniqueConstraint("chain_id", "tx_hash", name="uix_tx_chain_hash"),)
    
    id: Optional[int] = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    tx_hash: str = Field(index=True)
    block_height: Optional[int] = Field(
        default=None,
        index=True,
    )"""
)

# Fix Receipt model
content = content.replace(
    """class Receipt(SQLModel, table=True):
    __tablename__ = "receipt"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(index=True)
    receipt_id: str = Field(index=True, unique=True)
    block_height: Optional[int] = Field(
        default=None,
        index=True,
        foreign_key="block.height",
    )""",
    """class Receipt(SQLModel, table=True):
    __tablename__ = "receipt"
    __table_args__ = (UniqueConstraint("chain_id", "receipt_id", name="uix_receipt_chain_id"),)
    
    id: Optional[int] = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    job_id: str = Field(index=True)
    receipt_id: str = Field(index=True)
    block_height: Optional[int] = Field(
        default=None,
        index=True,
    )"""
)

# Fix Account model
content = content.replace(
    """class Account(SQLModel, table=True):
    __tablename__ = "account"
    
    address: str = Field(primary_key=True)""",
    """class Account(SQLModel, table=True):
    __tablename__ = "account"
    
    chain_id: str = Field(primary_key=True)
    address: str = Field(primary_key=True)"""
)

# Fix Block relationships sa_relationship_kwargs
content = content.replace(
    """    transactions: List["Transaction"] = Relationship(
        back_populates="block",
        sa_relationship_kwargs={"lazy": "selectin"}
    )""",
    """    transactions: List["Transaction"] = Relationship(
        back_populates="block",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "primaryjoin": "and_(Transaction.block_height==Block.height, Transaction.chain_id==Block.chain_id)",
            "foreign_keys": "[Transaction.block_height, Transaction.chain_id]"
        }
    )"""
)

content = content.replace(
    """    receipts: List["Receipt"] = Relationship(
        back_populates="block",
        sa_relationship_kwargs={"lazy": "selectin"}
    )""",
    """    receipts: List["Receipt"] = Relationship(
        back_populates="block",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "primaryjoin": "and_(Receipt.block_height==Block.height, Receipt.chain_id==Block.chain_id)",
            "foreign_keys": "[Receipt.block_height, Receipt.chain_id]"
        }
    )"""
)

# Fix reverse relationships
content = content.replace(
    """    block: Optional["Block"] = Relationship(back_populates="transactions")""",
    """    block: Optional["Block"] = Relationship(
        back_populates="transactions",
        sa_relationship_kwargs={
            "primaryjoin": "and_(Transaction.block_height==Block.height, Transaction.chain_id==Block.chain_id)",
            "foreign_keys": "[Transaction.block_height, Transaction.chain_id]"
        }
    )"""
)

content = content.replace(
    """    block: Optional["Block"] = Relationship(back_populates="receipts")""",
    """    block: Optional["Block"] = Relationship(
        back_populates="receipts",
        sa_relationship_kwargs={
            "primaryjoin": "and_(Receipt.block_height==Block.height, Receipt.chain_id==Block.chain_id)",
            "foreign_keys": "[Receipt.block_height, Receipt.chain_id]"
        }
    )"""
)


with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/models.py", "w") as f:
    f.write(content)
