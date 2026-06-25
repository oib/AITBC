from pydantic import BaseModel, ConfigDict, Field

from ..contexts.wallet.domain.wallet import TransactionStatus, WalletType


class WalletCreate(BaseModel):
    agent_id: str
    wallet_type: WalletType = WalletType.EOA
    metadata: dict[str, str] = Field(default_factory=dict)


class WalletResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: str
    address: str
    public_key: str
    wallet_type: WalletType
    is_active: bool


class TransactionRequest(BaseModel):
    chain_id: int
    to_address: str
    value: float = 0.0
    data: str | None = None
    gas_limit: int | None = None
    gas_price: float | None = None


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chain_id: int
    tx_hash: str | None
    status: TransactionStatus
