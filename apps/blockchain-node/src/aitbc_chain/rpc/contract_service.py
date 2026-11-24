"""Contract Service Module — queries deployed contracts from the database."""

from typing import Any

from sqlalchemy import func
from sqlmodel import col, select

from ..base_models import SmartContract
from ..database import session_scope

_MAX_LIMIT = 500
# Generous on purpose: LIMIT is the real bound — a tight OFFSET cap would
# make rows past ~1000 unreachable. OFFSET scan cost is bounded by table
# size either way.
_MAX_OFFSET = 100_000


class ContractService:
    @staticmethod
    def list_contracts(chain_id: str = "", limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List deployed contracts, newest first, bounded page (#2774).

        The route is public — an unbounded ``.all()`` let the table grow
        without limit. ``total`` is the full matching count so callers can
        paginate.
        """
        limit = max(1, min(int(limit), _MAX_LIMIT))
        offset = max(0, min(int(offset), _MAX_OFFSET))
        with session_scope(chain_id) as session:
            stmt = select(SmartContract).where(SmartContract.status == "deployed")
            count_stmt = select(func.count()).select_from(SmartContract).where(SmartContract.status == "deployed")
            if chain_id:
                stmt = stmt.where(SmartContract.chain_id == chain_id)
                count_stmt = count_stmt.where(SmartContract.chain_id == chain_id)
            total = session.exec(count_stmt).one()
            contracts = session.exec(
                stmt.order_by(col(SmartContract.deployed_at).desc(), col(SmartContract.id)).offset(offset).limit(limit)
            ).all()

            return {
                "scope": "node-local-registry",
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
                "total": total,
                "limit": limit,
                "offset": offset,
            }


contract_service = ContractService()
