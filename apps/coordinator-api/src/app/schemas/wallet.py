from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from .wallet import WalletType, NetworkType, TransactionStatus

class WalletCreate(BaseModel):
    agent_id: str
    wallet_type: WalletType = WalletType.EOA
    metadata: Dict[str, str] = Field(default_factory=dict)

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
    data: Optional[str] = None
    gas_limit: Optional[int] = None
    gas_price: Optional[float] = None

class TransactionResponse(BaseModel):
    id: int
    chain_id: int
    tx_hash: Optional[str]
    status: TransactionStatus
    
    class Config:
        orm_mode = True
