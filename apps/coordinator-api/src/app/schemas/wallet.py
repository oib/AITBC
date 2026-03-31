
from pydantic import BaseModel, Field

from .wallet import TransactionStatus, WalletType


class WalletCreate(BaseModel):
    agent_id: str
    wallet_type: WalletType = WalletType.EOA
    metadata: dict[str, str] = Field(default_factory=dict)


class WalletResponse(BaseModel):
    id: int
    agent_id: str
    address: str
    public_key: str
    wallet_type: WalletType
    is_active: bool

    class Config:
        orm_mode = True


class TransactionRequest(BaseModel):
    chain_id: int
    to_address: str
    value: float = 0.0
    data: str | None = None
    gas_limit: int | None = None
    gas_price: float | None = None


class TransactionResponse(BaseModel):
    id: int
    chain_id: int
    tx_hash: str | None
    status: TransactionStatus

    class Config:
        orm_mode = True
