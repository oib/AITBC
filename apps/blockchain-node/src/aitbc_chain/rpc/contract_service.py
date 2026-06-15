"""Contract Service Module"""

from typing import Any


class ContractService:
    @staticmethod
    def list_contracts() -> dict[str, Any]:
        return {
            "contracts": [
                {
                    "address": "0xguardian_001",
                    "name": "Guardian Contract",
                    "status": "deployed",
                    "functions": ["storeValue", "getValue", "setGuardian"],
                }
            ],
            "total": 1,
        }


contract_service = ContractService()
