"""
Agent Identity Manager Implementation
High-level manager for agent identity operations and cross-chain management
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, ClassVar
from uuid import uuid4

import secrets

from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger

from coordinator_api.agent_identity.core import AgentIdentityCore
from coordinator_api.agent_identity.registry import CrossChainRegistry
from coordinator_api.agent_identity.wallet_adapter_enhanced import (
    EnhancedWalletAdapter,
    SecurityLevel,
    WalletAdapterFactory,
)
from coordinator_api.config import settings
from ..domain.agent_identity import (
    AgentIdentity,
    AgentIdentityCreate,
    AgentIdentityUpdate,
    AgentWallet,
    AgentWalletUpdate,
    ChainType,
    IdentityStatus,
    VerificationType,
)

logger = get_logger(__name__)


class AgentWalletManager:
    """Manages agent wallets using the enhanced wallet adapter with real RPC calls."""

    _chain_types: ClassVar[dict[int, ChainType]] = {
        1: ChainType.ETHEREUM,
        137: ChainType.POLYGON,
        56: ChainType.BSC,
        42161: ChainType.ARBITRUM,
        10: ChainType.OPTIMISM,
        43114: ChainType.AVALANCHE,
        1000: ChainType.AITBC,
        1001: ChainType.AITBC,
    }

    def __init__(self, session: Session):
        self.session = session
        self.rpc_url = settings.blockchain_rpc_url

    def _get_adapter(self, chain_id: int) -> EnhancedWalletAdapter:
        return WalletAdapterFactory.create_adapter(chain_id, self.rpc_url, SecurityLevel.MEDIUM)

    @staticmethod
    def _security_config() -> dict[str, Any]:
        return {"password": secrets.token_hex(32), "encryption_password": secrets.token_hex(32)}

    async def create_agent_wallet(self, agent_id: str, chain_id: int, owner_address: str) -> AgentWallet:
        """Create an agent wallet on a specific blockchain."""
        adapter = self._get_adapter(chain_id)
        wallet_data = await adapter.create_wallet(owner_address, self._security_config())
        wallet = AgentWallet(
            agent_id=agent_id,
            chain_id=chain_id,
            chain_address=wallet_data["address"],
            wallet_type="agent-wallet",
            contract_address=wallet_data.get("contract_address"),
            is_active=True,
        )
        self.session.add(wallet)
        self.session.commit()
        self.session.refresh(wallet)
        logger.info("Created agent wallet %s for agent %s on chain %s", wallet.id, agent_id, chain_id)
        return wallet

    async def get_wallet_balance(self, agent_id: str, chain_id: int) -> Decimal:
        """Get wallet balance for an agent on a specific chain."""
        stmt = select(AgentWallet).where(
            AgentWallet.agent_id == agent_id, AgentWallet.chain_id == chain_id, AgentWallet.is_active
        )
        result = self.session.execute(stmt)
        wallet: AgentWallet | None = result.scalars().first()
        if wallet is None:
            raise ValueError(f"Active wallet not found for agent {agent_id} on chain {chain_id}")
        adapter = self._get_adapter(chain_id)
        balance_data = await adapter.get_balance(wallet.chain_address)
        balance = balance_data["eth_balance"] if "eth_balance" in balance_data else balance_data.get("balance", Decimal("0"))
        wallet.balance = Decimal(str(balance))
        self.session.commit()
        return wallet.balance

    async def execute_wallet_transaction(
        self,
        agent_id: str,
        chain_id: int,
        to_address: str,
        amount: Decimal,
        data: dict[str, Any] | None = None,
        private_key: str | None = None,
    ) -> dict[str, Any]:
        """Execute a transaction from an agent wallet."""
        stmt = (
            select(AgentWallet)
            .where(AgentWallet.agent_id == agent_id, AgentWallet.chain_id == chain_id, AgentWallet.is_active)
            .with_for_update()
        )
        result = self.session.execute(stmt)
        wallet = result.scalars().first()
        if not wallet:
            raise ValueError(f"Active wallet not found for agent {agent_id} on chain {chain_id}")
        if wallet.spending_limit > 0 and wallet.total_spent + amount > wallet.spending_limit:
            raise ValueError("Transaction amount exceeds spending limit")
        adapter = self._get_adapter(chain_id)
        tx_result = await adapter.execute_transaction(
            wallet.chain_address, to_address, amount, data=data, private_key=private_key
        )
        wallet.total_spent += amount
        wallet.last_transaction = datetime.now(UTC)
        wallet.transaction_count += 1
        self.session.commit()
        logger.info("Executed wallet transaction: %s", tx_result["transaction_hash"])
        return tx_result

    async def get_wallet_transaction_history(
        self, agent_id: str, chain_id: int, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Get transaction history for an agent wallet."""
        stmt = select(AgentWallet).where(
            AgentWallet.agent_id == agent_id, AgentWallet.chain_id == chain_id, AgentWallet.is_active
        )
        result = self.session.execute(stmt)
        wallet = result.scalars().first()
        if not wallet:
            raise ValueError(f"Active wallet not found for agent {agent_id} on chain {chain_id}")
        adapter = self._get_adapter(chain_id)
        return await adapter.get_transaction_history(wallet.chain_address, limit, offset)

    async def update_agent_wallet(self, agent_id: str, chain_id: int, request: AgentWalletUpdate) -> AgentWallet:
        """Update agent wallet settings."""
        stmt = select(AgentWallet).where(AgentWallet.agent_id == agent_id, AgentWallet.chain_id == chain_id)
        result = self.session.execute(stmt)
        wallet = result.scalars().first()
        if not wallet:
            raise ValueError(f"Wallet not found for agent {agent_id} on chain {chain_id}")
        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(wallet, field):
                setattr(wallet, field, value)
        wallet.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(wallet)
        logger.info("Updated agent wallet: %s", wallet.id)
        return wallet  # type: ignore[no-any-return]

    async def get_all_agent_wallets(self, agent_id: str) -> list[AgentWallet]:
        """Get all wallets for an agent across all chains."""
        stmt = select(AgentWallet).where(AgentWallet.agent_id == agent_id)
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    async def deactivate_wallet(self, agent_id: str, chain_id: int) -> bool:
        """Deactivate an agent wallet."""
        stmt = select(AgentWallet).where(AgentWallet.agent_id == agent_id, AgentWallet.chain_id == chain_id)
        result = self.session.execute(stmt)
        wallet = result.scalars().first()
        if not wallet:
            raise ValueError(f"Wallet not found for agent {agent_id} on chain {chain_id}")
        wallet.is_active = False
        wallet.updated_at = datetime.now(UTC)
        self.session.commit()
        logger.info("Deactivated agent wallet: %s", wallet.id)
        return True

    async def get_wallet_statistics(self, agent_id: str) -> dict[str, Any]:
        """Get comprehensive wallet statistics for an agent."""
        wallets = await self.get_all_agent_wallets(agent_id)
        total_balance = Decimal("0")
        total_spent = Decimal("0")
        total_transactions = 0
        active_wallets = 0
        chain_breakdown: dict[str, dict[str, Any]] = {}
        for wallet in wallets:
            try:
                balance = await self.get_wallet_balance(agent_id, wallet.chain_id)
                total_balance += balance
            except Exception as e:
                logger.warning("Failed to get balance for wallet %s: %s", wallet.id, e)
                balance = Decimal("0")
            total_spent += wallet.total_spent
            total_transactions += wallet.transaction_count
            if wallet.is_active:
                active_wallets += 1
            info = WalletAdapterFactory.get_chain_info(wallet.chain_id)
            chain_name = info.get("name", f"Chain {wallet.chain_id}")
            if chain_name not in chain_breakdown:
                chain_breakdown[chain_name] = {
                    "balance": Decimal("0"),
                    "spent": Decimal("0"),
                    "transactions": 0,
                    "active": False,
                }
            chain_breakdown[chain_name]["balance"] += balance
            chain_breakdown[chain_name]["spent"] += wallet.total_spent
            chain_breakdown[chain_name]["transactions"] += wallet.transaction_count
            chain_breakdown[chain_name]["active"] = wallet.is_active
        return {
            "total_wallets": len(wallets),
            "active_wallets": active_wallets,
            "total_balance": total_balance,
            "total_spent": total_spent,
            "total_transactions": total_transactions,
            "average_balance_per_wallet": total_balance / max(len(wallets), 1),
            "chain_breakdown": chain_breakdown,
            "supported_chains": list(chain_breakdown.keys()),
        }

    async def verify_wallet_address(self, chain_id: int, address: str) -> bool:
        """Verify if an address is valid for a specific chain."""
        try:
            adapter = self._get_adapter(chain_id)
            return await adapter.validate_address(address)
        except Exception as e:
            logger.error("Error verifying address %s on chain %s: %s", address, chain_id, e)
            return False

    async def sync_wallet_balances(self, agent_id: str) -> dict[str, Any]:
        """Sync balances for all agent wallets."""
        wallets = await self.get_all_agent_wallets(agent_id)
        sync_results = {}
        for wallet in wallets:
            if not wallet.is_active:
                continue
            try:
                balance = await self.get_wallet_balance(agent_id, wallet.chain_id)
                sync_results[wallet.chain_id] = {"success": True, "balance": balance, "address": wallet.chain_address}
            except Exception as e:
                sync_results[wallet.chain_id] = {"success": False, "error": str(e), "address": wallet.chain_address}
        return sync_results  # type: ignore[return-value]

    def get_supported_chains(self) -> list[dict[str, Any]]:
        """Get list of supported blockchains."""
        return [
            {
                "chain_id": chain_id,
                "chain_type": self._chain_types.get(chain_id, ChainType.CUSTOM),
                "name": WalletAdapterFactory.get_chain_info(chain_id).get("name", f"Chain {chain_id}"),
                "rpc_url": self.rpc_url,
            }
            for chain_id in WalletAdapterFactory.get_supported_chains()
        ]


class AgentIdentityManager:
    """High-level manager for agent identity operations"""

    def __init__(self, session: Session):
        self.session = session
        self.core = AgentIdentityCore(session)
        self.registry = CrossChainRegistry(session)
        self.wallet_adapter = AgentWalletManager(session)

    async def get_identity_by_owner(self, owner_address: str) -> list[AgentIdentity]:
        """Get all identities for an owner."""
        return await self.core.get_identity_by_owner(owner_address)

    async def create_agent_identity(
        self,
        owner_address: str,
        chains: list[int],
        display_name: str = "",
        description: str = "",
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a complete agent identity with cross-chain mappings"""
        agent_id = f"agent_{uuid4().hex[:12]}"
        identity_request = AgentIdentityCreate(
            agent_id=agent_id,
            owner_address=owner_address,
            display_name=display_name,
            description=description,
            supported_chains=chains,
            primary_chain=chains[0] if chains else 1,
            metadata=metadata or {},
            tags=tags or [],
        )
        identity = await self.core.create_identity(identity_request)
        chain_mappings = {}
        for chain_id in chains:
            chain_address = f"0x{secrets.token_hex(20)}"
            chain_mappings[chain_id] = chain_address
        registration_result = await self.registry.register_cross_chain_identity(
            agent_id, chain_mappings, owner_address, VerificationType.BASIC
        )
        wallet_results = []
        for chain_id in chains:
            try:
                wallet = await self.wallet_adapter.create_agent_wallet(agent_id, chain_id, owner_address)
                wallet_results.append(
                    {"chain_id": chain_id, "wallet_id": wallet.id, "wallet_address": wallet.chain_address, "success": True}
                )
            except Exception as e:
                logger.error("Failed to create wallet for chain %s: %s", chain_id, e)
                wallet_results.append({"chain_id": chain_id, "error": "Wallet creation failed", "success": False})
        return {
            "identity_id": identity.id,
            "agent_id": agent_id,
            "owner_address": owner_address,
            "display_name": display_name,
            "supported_chains": chains,
            "primary_chain": identity.primary_chain,
            "registration_result": registration_result,
            "wallet_results": wallet_results,
            "created_at": identity.created_at.isoformat(),
        }

    async def migrate_agent_identity(
        self, agent_id: str, from_chain: int, to_chain: int, new_address: str, verifier_address: str | None = None
    ) -> dict[str, Any]:
        """Migrate agent identity from one chain to another"""
        try:
            migration_result = await self.registry.migrate_agent_identity(
                agent_id, from_chain, to_chain, new_address, verifier_address
            )
            if migration_result["migration_successful"]:
                try:
                    identity = await self.core.get_identity_by_agent_id(agent_id)
                    if identity:
                        wallet = await self.wallet_adapter.create_agent_wallet(agent_id, to_chain, identity.owner_address)
                        migration_result["wallet_created"] = True
                        migration_result["wallet_id"] = wallet.id
                        migration_result["wallet_address"] = wallet.chain_address
                    else:
                        migration_result["wallet_created"] = False
                        migration_result["error"] = "Identity not found"
                except Exception:
                    migration_result["wallet_created"] = False
                    migration_result["wallet_error"] = "Wallet creation failed"
            else:
                migration_result["wallet_created"] = False
            return migration_result
        except Exception as e:
            logger.error("Failed to migrate agent %s from chain %s to %s: %s", agent_id, from_chain, to_chain, e)
            return {
                "agent_id": agent_id,
                "from_chain": from_chain,
                "to_chain": to_chain,
                "migration_successful": False,
                "error": "Migration failed",
            }

    async def sync_agent_reputation(self, agent_id: str) -> dict[str, Any]:
        """Sync agent reputation across all chains"""
        try:
            identity = await self.core.get_identity_by_agent_id(agent_id)
            if not identity:
                raise ValueError(f"Agent identity not found: {agent_id}")
            reputation_scores = await self.registry.sync_agent_reputation(agent_id)
            if reputation_scores:
                verified_mappings = await self.registry.get_verified_mappings(agent_id)
                verified_chains = {m.chain_id for m in verified_mappings}
                total_weight = 0.0
                weighted_sum = 0.0
                for chain_id, score in reputation_scores.items():
                    weight = 2.0 if chain_id in verified_chains else 1.0
                    total_weight += weight
                    weighted_sum += score * weight
                aggregated_score = weighted_sum / total_weight if total_weight > 0 else 0
                await self.core.update_reputation(agent_id, True, 0)
                identity.reputation_score = aggregated_score
                identity.updated_at = datetime.now(UTC)
                self.session.commit()
            else:
                aggregated_score = identity.reputation_score
            return {
                "agent_id": agent_id,
                "aggregated_reputation": aggregated_score,
                "chain_reputations": reputation_scores,
                "verified_chains": list(verified_chains) if "verified_chains" in locals() else [],
                "sync_timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("Failed to sync reputation for agent %s: %s", agent_id, e)
            return {"agent_id": agent_id, "sync_successful": False, "error": "Sync failed"}

    async def get_agent_identity_summary(self, agent_id: str) -> dict[str, Any]:
        """Get comprehensive summary of agent identity"""
        try:
            identity = await self.core.get_identity_by_agent_id(agent_id)
            if not identity:
                return {"agent_id": agent_id, "error": "Identity not found"}
            mappings = await self.registry.get_all_cross_chain_mappings(agent_id)
            wallet_stats = await self.wallet_adapter.get_wallet_statistics(agent_id)
            identity_stats = await self.core.get_identity_statistics(identity.id)
            verified_mappings = await self.registry.get_verified_mappings(agent_id)
            return {
                "identity": {
                    "id": identity.id,
                    "agent_id": identity.agent_id,
                    "owner_address": identity.owner_address,
                    "display_name": identity.display_name,
                    "description": identity.description,
                    "status": identity.status,
                    "verification_level": identity.verification_level,
                    "is_verified": identity.is_verified,
                    "verified_at": identity.verified_at.isoformat() if identity.verified_at else None,
                    "reputation_score": identity.reputation_score,
                    "supported_chains": identity.supported_chains,
                    "primary_chain": identity.primary_chain,
                    "total_transactions": identity.total_transactions,
                    "successful_transactions": identity.successful_transactions,
                    "success_rate": identity.successful_transactions / max(identity.total_transactions, 1),
                    "created_at": identity.created_at.isoformat(),
                    "updated_at": identity.updated_at.isoformat(),
                    "last_activity": identity.last_activity.isoformat() if identity.last_activity else None,
                    "identity_data": identity.identity_data,
                    "tags": identity.tags,
                },
                "cross_chain": {
                    "total_mappings": len(mappings),
                    "verified_mappings": len(verified_mappings),
                    "verification_rate": len(verified_mappings) / max(len(mappings), 1),
                    "mappings": [
                        {
                            "chain_id": m.chain_id,
                            "chain_type": m.chain_type,
                            "chain_address": m.chain_address,
                            "is_verified": m.is_verified,
                            "verified_at": m.verified_at.isoformat() if m.verified_at else None,
                            "wallet_address": m.wallet_address,
                            "transaction_count": m.transaction_count,
                            "last_transaction": m.last_transaction.isoformat() if m.last_transaction else None,
                        }
                        for m in mappings
                    ],
                },
                "wallets": wallet_stats,
                "statistics": identity_stats,
            }
        except Exception as e:
            logger.error("Failed to get identity summary for agent %s: %s", agent_id, e)
            return {"agent_id": agent_id, "error": "Failed to get summary"}

    async def update_agent_identity(self, agent_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Update agent identity and related components"""
        try:
            identity = await self.core.get_identity_by_agent_id(agent_id)
            if not identity:
                raise ValueError(f"Agent identity not found: {agent_id}")
            update_request = AgentIdentityUpdate(**updates)
            updated_identity = await self.core.update_identity(identity.id, update_request)
            cross_chain_updates = updates.get("cross_chain_updates", {})
            if cross_chain_updates:
                for chain_id, chain_update in cross_chain_updates.items():
                    try:
                        await self.registry.update_identity_mapping(
                            agent_id, int(chain_id), chain_update.get("new_address"), chain_update.get("verifier_address")
                        )
                    except Exception as e:
                        logger.error("Failed to update cross-chain mapping for chain %s: %s", chain_id, e)
            wallet_updates = updates.get("wallet_updates", {})
            if wallet_updates:
                for chain_id, wallet_update in wallet_updates.items():
                    try:
                        wallet_request = AgentWalletUpdate(**wallet_update)
                        await self.wallet_adapter.update_agent_wallet(agent_id, int(chain_id), wallet_request)
                    except Exception as e:
                        logger.error("Failed to update wallet for chain %s: %s", chain_id, e)
            return {
                "agent_id": agent_id,
                "identity_id": updated_identity.id,
                "updated_fields": list(updates.keys()),
                "updated_at": updated_identity.updated_at.isoformat(),
            }
        except Exception as e:
            logger.error("Failed to update agent identity %s: %s", agent_id, e)
            return {"agent_id": agent_id, "update_successful": False, "error": "Update failed"}

    async def deactivate_agent_identity(self, agent_id: str, reason: str = "") -> bool:
        """Deactivate an agent identity across all chains"""
        try:
            identity = await self.core.get_identity_by_agent_id(agent_id)
            if not identity:
                raise ValueError(f"Agent identity not found: {agent_id}")
            await self.core.suspend_identity(identity.id, reason)
            wallets = await self.wallet_adapter.get_all_agent_wallets(agent_id)
            for wallet in wallets:
                await self.wallet_adapter.deactivate_wallet(agent_id, wallet.chain_id)
            mappings = await self.registry.get_all_cross_chain_mappings(agent_id)
            for mapping in mappings:
                await self.registry.revoke_verification(identity.id, mapping.chain_id, reason)
            logger.info("Deactivated agent identity: %s, reason: %s", agent_id, reason)
            return True
        except Exception as e:
            logger.error("Failed to deactivate agent identity %s: %s", agent_id, e)
            return False

    async def search_agent_identities(
        self,
        query: str = "",
        chains: list[int] | None = None,
        status: IdentityStatus | None = None,
        verification_level: VerificationType | None = None,
        min_reputation: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Search agent identities with advanced filters"""
        try:
            identities = await self.core.search_identities(
                query=query, status=status, verification_level=verification_level, limit=limit, offset=offset
            )
            filtered_identities = []
            for identity in identities:
                if chains:
                    identity_chains = [int(chain_id) for chain_id in identity.supported_chains]
                    if not any(chain in identity_chains for chain in chains):
                        continue
                if min_reputation is not None and identity.reputation_score < min_reputation:
                    continue
                filtered_identities.append(identity)
            results = []
            for identity in filtered_identities:
                try:
                    mappings = await self.registry.get_all_cross_chain_mappings(identity.agent_id)
                    verified_count = len([m for m in mappings if m.is_verified])
                    wallet_stats = await self.wallet_adapter.get_wallet_statistics(identity.agent_id)
                    results.append(
                        {
                            "identity_id": identity.id,
                            "agent_id": identity.agent_id,
                            "owner_address": identity.owner_address,
                            "display_name": identity.display_name,
                            "description": identity.description,
                            "status": identity.status,
                            "verification_level": identity.verification_level,
                            "is_verified": identity.is_verified,
                            "reputation_score": identity.reputation_score,
                            "supported_chains": identity.supported_chains,
                            "primary_chain": identity.primary_chain,
                            "total_transactions": identity.total_transactions,
                            "success_rate": identity.successful_transactions / max(identity.total_transactions, 1),
                            "cross_chain_mappings": len(mappings),
                            "verified_mappings": verified_count,
                            "total_wallets": wallet_stats["total_wallets"],
                            "total_balance": wallet_stats["total_balance"],
                            "created_at": identity.created_at.isoformat(),
                            "last_activity": identity.last_activity.isoformat() if identity.last_activity else None,
                        }
                    )
                except Exception as e:
                    logger.error("Error getting details for identity %s: %s", identity.id, e)
                    continue
            return {
                "results": results,
                "total_count": len(results),
                "query": query,
                "filters": {
                    "chains": chains,
                    "status": status,
                    "verification_level": verification_level,
                    "min_reputation": min_reputation,
                },
                "pagination": {"limit": limit, "offset": offset},
            }
        except Exception as e:
            logger.error("Failed to search agent identities: %s", e)
            return {"results": [], "total_count": 0, "error": "Search failed"}

    async def get_registry_health(self) -> dict[str, Any]:
        """Get health status of the identity registry"""
        try:
            registry_stats = await self.registry.get_registry_statistics()
            cleaned_count = await self.registry.cleanup_expired_verifications()
            supported_chains = self.wallet_adapter.get_supported_chains()
            issues = []
            if registry_stats["verification_rate"] < 0.5:
                issues.append("Low verification rate")
            if registry_stats["total_mappings"] == 0:
                issues.append("No cross-chain mappings found")
            return {
                "status": "healthy" if not issues else "degraded",
                "registry_statistics": registry_stats,
                "supported_chains": supported_chains,
                "cleaned_verifications": cleaned_count,
                "issues": issues,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("Failed to get registry health: %s", e)
            return {"status": "error", "error": "Health check failed", "timestamp": datetime.now(UTC).isoformat()}

    async def export_agent_identity(self, agent_id: str, format: str = "json") -> dict[str, Any]:
        """Export agent identity data for backup or migration"""
        try:
            summary = await self.get_agent_identity_summary(agent_id)
            if "error" in summary:
                return summary
            export_data = {
                "export_version": "1.0",
                "export_timestamp": datetime.now(UTC).isoformat(),
                "agent_id": agent_id,
                "identity": summary["identity"],
                "cross_chain_mappings": summary["cross_chain"]["mappings"],
                "wallet_statistics": summary["wallets"],
                "identity_statistics": summary["statistics"],
            }
            if format.lower() == "json":
                return export_data
            else:
                return {"error": f"Format {format} not supported"}
        except Exception as e:
            logger.error("Failed to export agent identity %s: %s", agent_id, e)
            return {"agent_id": agent_id, "export_successful": False, "error": "Export failed"}

    async def import_agent_identity(self, export_data: dict[str, Any]) -> dict[str, Any]:
        """Import agent identity data from backup or migration"""
        try:
            if "export_version" not in export_data or "agent_id" not in export_data:
                raise ValueError("Invalid export data format")
            agent_id = export_data["agent_id"]
            identity_data = export_data["identity"]
            existing = await self.core.get_identity_by_agent_id(agent_id)
            if existing:
                return {"agent_id": agent_id, "import_successful": False, "error": "Identity already exists"}
            identity_request = AgentIdentityCreate(
                agent_id=agent_id,
                owner_address=identity_data["owner_address"],
                display_name=identity_data["display_name"],
                description=identity_data["description"],
                supported_chains=[int(chain_id) for chain_id in identity_data["supported_chains"]],
                primary_chain=identity_data["primary_chain"],
                metadata=identity_data["metadata"],
                tags=identity_data["tags"],
            )
            identity = await self.core.create_identity(identity_request)
            mappings = export_data.get("cross_chain_mappings", [])
            chain_mappings = {}
            for mapping in mappings:
                chain_mappings[mapping["chain_id"]] = mapping["chain_address"]
            if chain_mappings:
                await self.registry.register_cross_chain_identity(
                    agent_id, chain_mappings, identity_data["owner_address"], VerificationType.BASIC
                )
            for chain_id in chain_mappings.keys():
                try:
                    await self.wallet_adapter.create_agent_wallet(agent_id, chain_id, identity_data["owner_address"])
                except Exception as e:
                    logger.error("Failed to restore wallet for chain %s: %s", chain_id, e)
            return {
                "agent_id": agent_id,
                "identity_id": identity.id,
                "import_successful": True,
                "restored_mappings": len(chain_mappings),
                "import_timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("Failed to import agent identity: %s", e)
            return {"import_successful": False, "error": "Import failed"}
