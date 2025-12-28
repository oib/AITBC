from __future__ import annotations

from datetime import datetime
import re
from typing import Optional

from pydantic import field_validator
from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, Relationship, SQLModel
from sqlalchemy.orm import Mapped

_HEX_PATTERN = re.compile(r"^(0x)?[0-9a-fA-F]+$")


def _validate_hex(value: str, field_name: str) -> str:
    if not _HEX_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a hex-encoded string")
    return value.lower()


def _validate_optional_hex(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return value
    return _validate_hex(value, field_name)


class Block(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    height: int = Field(index=True, unique=True)
    hash: str = Field(index=True, unique=True)
    parent_hash: str
    proposer: str
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    tx_count: int = 0
    state_root: Optional[str] = None

    @field_validator("hash", mode="before")
    @classmethod
    def _hash_is_hex(cls, value: str) -> str:
        return _validate_hex(value, "Block.hash")

    @field_validator("parent_hash", mode="before")
    @classmethod
    def _parent_hash_is_hex(cls, value: str) -> str:
        return _validate_hex(value, "Block.parent_hash")

    @field_validator("state_root", mode="before")
    @classmethod
    def _state_root_is_hex(cls, value: Optional[str]) -> Optional[str]:
        return _validate_optional_hex(value, "Block.state_root")


class Transaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tx_hash: str = Field(index=True, unique=True)
    block_height: Optional[int] = Field(
        default=None,
        index=True,
        foreign_key="block.height",
    )
    sender: str
    recipient: str
    payload: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    @field_validator("tx_hash", mode="before")
    @classmethod
    def _tx_hash_is_hex(cls, value: str) -> str:
        return _validate_hex(value, "Transaction.tx_hash")


class Receipt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(index=True)
    receipt_id: str = Field(index=True, unique=True)
    block_height: Optional[int] = Field(
        default=None,
        index=True,
        foreign_key="block.height",
    )
    payload: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    miner_signature: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    coordinator_attestations: list[dict] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    minted_amount: Optional[int] = None
    recorded_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    @field_validator("receipt_id", mode="before")
    @classmethod
    def _receipt_id_is_hex(cls, value: str) -> str:
        return _validate_hex(value, "Receipt.receipt_id")


class Account(SQLModel, table=True):
    address: str = Field(primary_key=True)
    balance: int = 0
    nonce: int = 0
    updated_at: datetime = Field(default_factory=datetime.utcnow)
