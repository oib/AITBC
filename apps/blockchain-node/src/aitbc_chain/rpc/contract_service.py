"""Contract Service Module — queries deployed contracts from the database."""

from typing import Any

from sqlmodel import select

from ..base_models import SmartContract
from ..database import session_scope


class ContractService:
    @staticmethod
    def list_contracts(chain_id: str = "") -> dict[str, Any]:
        """List all deployed contracts from the database."""
        with session_scope(chain_id) as session:
            stmt = select(SmartContract).where(SmartContract.status == "deployed")
            if chain_id:
                stmt = stmt.where(SmartContract.chain_id == chain_id)
            contracts = session.exec(stmt).all()

            return {
                "contracts": [
                    {
                        "address": c.address,
                        "name": c.name,
                        "type": c.contract_type,
                        "status": c.status,
                        "deployer": c.deployer,
                        "deployed_at": c.deployed_at.isoformat() if c.deployed_at else None,
                        "functions": list(c.abi.keys()) if c.abi else [],
                    }
                    for c in contracts
                ],
                "total": len(contracts),
            }


contract_service = ContractService()
