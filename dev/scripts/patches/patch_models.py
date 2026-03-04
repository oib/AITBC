import re

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/models.py", "r") as f:
    content = f.read()

content = content.replace(
    "from sqlmodel import Field, Relationship, SQLModel",
    "from sqlmodel import Field, Relationship, SQLModel\nfrom sqlalchemy import UniqueConstraint"
)

content = content.replace(
    """class Block(SQLModel, table=True):
    __tablename__ = "block"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    height: int = Field(index=True, unique=True)""",
    """class Block(SQLModel, table=True):
    __tablename__ = "block"
    __table_args__ = (UniqueConstraint("chain_id", "height"),)
    
    id: Optional[int] = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    height: int = Field(index=True)"""
)

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
    
    id: Optional[int] = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    tx_hash: str = Field(index=True, unique=True)
    block_height: Optional[int] = Field(
        default=None,
        index=True,
    )"""
)

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
    
    id: Optional[int] = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    job_id: str = Field(index=True)
    receipt_id: str = Field(index=True, unique=True)
    block_height: Optional[int] = Field(
        default=None,
        index=True,
    )"""
)

content = content.replace(
    """class Account(SQLModel, table=True):
    __tablename__ = "account"
    
    address: str = Field(primary_key=True)""",
    """class Account(SQLModel, table=True):
    __tablename__ = "account"
    
    chain_id: str = Field(primary_key=True)
    address: str = Field(primary_key=True)"""
)

# Fix relationships in Transaction and Receipt to use sa_relationship_kwargs
content = content.replace(
    """block: Optional["Block"] = Relationship(back_populates="transactions")""",
    """block: Optional["Block"] = Relationship(
        back_populates="transactions",
        sa_relationship_kwargs={
            "primaryjoin": "and_(Transaction.block_height==Block.height, Transaction.chain_id==Block.chain_id)",
            "foreign_keys": "[Transaction.block_height, Transaction.chain_id]"
        }
    )"""
)

content = content.replace(
    """block: Optional["Block"] = Relationship(back_populates="receipts")""",
    """block: Optional["Block"] = Relationship(
        back_populates="receipts",
        sa_relationship_kwargs={
            "primaryjoin": "and_(Receipt.block_height==Block.height, Receipt.chain_id==Block.chain_id)",
            "foreign_keys": "[Receipt.block_height, Receipt.chain_id]"
        }
    )"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/models.py", "w") as f:
    f.write(content)
