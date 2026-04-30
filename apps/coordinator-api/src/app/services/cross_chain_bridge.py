"""
Cross-Chain Bridge Service

Secure cross-chain asset transfer protocol with ZK proof validation.
Enables bridging of assets between different blockchain networks.
"""

from __future__ import annotations

from datetime import datetime, UTC, timedelta

from aitbc import get_logger
from fastapi import HTTPException
from sqlalchemy import select
from sqlmodel import Session

from ..blockchain.contract_interactions import ContractInteractionService
from ..crypto.merkle_tree import MerkleTreeService
from ..crypto.zk_proofs import ZKProofService
from ..domain.cross_chain_bridge import (
    BridgeRequest,
    BridgeRequestStatus,
    BridgeTransaction,
    ChainConfig,
    MerkleProof,
    SupportedToken,
    Validator,
)
from ..monitoring.bridge_monitor import BridgeMonitor
from ..schemas.cross_chain_bridge import (
    BridgeCompleteRequest,
    BridgeConfirmRequest,
    BridgeCreateRequest,
    BridgeResponse,
    BridgeStatusResponse,
    ChainSupportRequest,
    TokenSupportRequest,
)

logger = logging.getLogger(__name__)


class CrossChainBridgeService:
    """Secure cross-chain asset transfer protocol"""

    def __init__(
        self,
        session: Session,
        contract_service: ContractInteractionService,
        zk_proof_service: ZKProofService,
        merkle_tree_service: MerkleTreeService,
        bridge_monitor: BridgeMonitor,
    ) -> None:
        self.session = session
        self.contract_service = contract_service
        self.zk_proof_service = zk_proof_service
        self.merkle_tree_service = merkle_tree_service
        self.bridge_monitor = bridge_monitor

        # Configuration
        self.bridge_fee_percentage = 0.5  # 0.5% bridge fee
        self.max_bridge_amount = 1000000  # Max 1M tokens per bridge
        self.min_confirmations = 3
        self.bridge_timeout = 24 * 60 * 60  # 24 hours
        self.validator_threshold = 0.67  # 67% of validators required

    async def initiate_transfer(self, transfer_request: BridgeCreateRequest, sender_address: str) -> BridgeResponse:
        """Initiate cross-chain asset transfer with ZK proof validation"""

        try:
            # Validate transfer request
            validation_result = await self._validate_transfer_request(transfer_request, sender_address)
            if not validation_result.is_valid:
                raise HTTPException(status_code=400, detail=validation_result.error_message)

            # Get supported token configuration
            token_config = await self._get_supported_token(transfer_request.source_token)
            if not token_config or not token_config.is_active:
                raise HTTPException(status_code=400, detail="Source token not supported for bridging")

            # Get chain configuration
            source_chain = await self._get_chain_config(transfer_request.source_chain_id)
            target_chain = await self._get_chain_config(transfer_request.target_chain_id)

            if not source_chain or not target_chain:
                raise HTTPException(status_code=400, detail="Unsupported blockchain network")

            # Calculate bridge fee
            bridge_fee = (transfer_request.amount * self.bridge_fee_percentage) / 100
            total_amount = transfer_request.amount + bridge_fee

            # Check bridge limits
            if transfer_request.amount > token_config.bridge_limit:
                raise HTTPException(status_code=400, detail=f"Amount exceeds bridge limit of {token_config.bridge_limit}")

            # Generate ZK proof for transfer
            zk_proof = await self._generate_transfer_zk_proof(transfer_request, sender_address)

            # Create bridge request on blockchain
            contract_request_id = await self.contract_service.initiate_bridge(
                transfer_request.source_token,
                transfer_request.target_token,
                transfer_request.amount,
                transfer_request.target_chain_id,
                transfer_request.recipient_address,
            )

            # Create bridge request record
            bridge_request = BridgeRequest(
                contract_request_id=str(contract_request_id),
                sender_address=sender_address,
                recipient_address=transfer_request.recipient_address,
                source_token=transfer_request.source_token,
                target_token=transfer_request.target_token,
                source_chain_id=transfer_request.source_chain_id,
                target_chain_id=transfer_request.target_chain_id,
                amount=transfer_request.amount,
                bridge_fee=bridge_fee,
                total_amount=total_amount,
                status=BridgeRequestStatus.PENDING,
                zk_proof=zk_proof.proof,
                created_at=datetime.now(datetime.UTC),
                expires_at=datetime.now(datetime.UTC) + timedelta(seconds=self.bridge_timeout),
            )

            self.session.add(bridge_request)
            self.session.commit()
            self.session.refresh(bridge_request)

            # Start monitoring the bridge request
            await self.bridge_monitor.start_monitoring(bridge_request.id)

            logger.info(f"Initiated bridge transfer {bridge_request.id} from {sender_address}")

            return BridgeResponse.from_orm(bridge_request)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error initiating bridge transfer: {str(e)}")
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    async def monitor_bridge_status(self, request_id: int) -> BridgeStatusResponse:
        """Real-time bridge status monitoring across multiple chains"""

        try:
            # Get bridge request
            bridge_request = self.session.get(BridgeRequest, request_id)
            if not bridge_request:
                raise HTTPException(status_code=404, detail="Bridge request not found")

            # Get current status from blockchain
            contract_status = await self.contract_service.get_bridge_status(bridge_request.contract_request_id)

            # Update local status if different
            if contract_status.status != bridge_request.status.value:
                bridge_request.status = BridgeRequestStatus(contract_status.status)
                bridge_request.updated_at = datetime.now(datetime.UTC)
                self.session.commit()

            # Get confirmation details
            confirmations = await self._get_bridge_confirmations(request_id)

            # Get transaction details
            transactions = await self._get_bridge_transactions(request_id)

            # Calculate estimated completion time
            estimated_completion = await self._calculate_estimated_completion(bridge_request)

            status_response = BridgeStatusResponse(
                request_id=request_id,
                status=bridge_request.status,
                source_chain_id=bridge_request.source_chain_id,
                target_chain_id=bridge_request.target_chain_id,
                amount=bridge_request.amount,
                created_at=bridge_request.created_at,
                updated_at=bridge_request.updated_at,
                confirmations=confirmations,
                transactions=transactions,
                estimated_completion=estimated_completion,
            )

            return status_response

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error monitoring bridge status: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def dispute_resolution(self, dispute_data: dict) -> dict:
        """Automated dispute resolution for failed transfers"""

        try:
            request_id = dispute_data.get("request_id")
            dispute_reason = dispute_data.get("reason")

            # Get bridge request
            bridge_request = self.session.get(BridgeRequest, request_id)
            if not bridge_request:
                raise HTTPException(status_code=404, detail="Bridge request not found")

            # Check if dispute is valid
            if bridge_request.status != BridgeRequestStatus.FAILED:
                raise HTTPException(status_code=400, detail="Dispute only available for failed transfers")

            # Analyze failure reason
            failure_analysis = await self._analyze_bridge_failure(bridge_request)

            # Determine resolution action
            resolution_action = await self._determine_resolution_action(bridge_request, failure_analysis)

            # Execute resolution
            resolution_result = await self._execute_resolution(bridge_request, resolution_action)

            # Record dispute resolution
            bridge_request.dispute_reason = dispute_reason
            bridge_request.resolution_action = resolution_action.action_type
            bridge_request.resolved_at = datetime.now(datetime.UTC)
            bridge_request.status = BridgeRequestStatus.RESOLVED

            self.session.commit()

            logger.info(f"Resolved dispute for bridge request {request_id}")

            return resolution_result

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error resolving dispute: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def confirm_bridge_transfer(self, confirm_request: BridgeConfirmRequest, validator_address: str) -> dict:
        """Confirm bridge transfer by validator"""

        try:
            # Validate validator
            validator = await self._get_validator(validator_address)
            if not validator or not validator.is_active:
                raise HTTPException(status_code=403, detail="Not an active validator")

            # Get bridge request
            bridge_request = self.session.get(BridgeRequest, confirm_request.request_id)
            if not bridge_request:
                raise HTTPException(status_code=404, detail="Bridge request not found")

            if bridge_request.status != BridgeRequestStatus.PENDING:
                raise HTTPException(status_code=400, detail="Bridge request not in pending status")

            # Verify validator signature
            signature_valid = await self._verify_validator_signature(confirm_request, validator_address)
            if not signature_valid:
                raise HTTPException(status_code=400, detail="Invalid validator signature")

            # Check if already confirmed by this validator
            existing_confirmation = self.session.execute(
                select(BridgeTransaction).where(
                    BridgeTransaction.bridge_request_id == bridge_request.id,
                    BridgeTransaction.validator_address == validator_address,
                    BridgeTransaction.transaction_type == "confirmation",
                )
            ).first()

            if existing_confirmation:
                raise HTTPException(status_code=400, detail="Already confirmed by this validator")

            # Record confirmation
            confirmation = BridgeTransaction(
                bridge_request_id=bridge_request.id,
                validator_address=validator_address,
                transaction_type="confirmation",
                transaction_hash=confirm_request.lock_tx_hash,
                signature=confirm_request.signature,
                confirmed_at=datetime.now(datetime.UTC),
            )

            self.session.add(confirmation)

            # Check if we have enough confirmations
            total_confirmations = await self._count_confirmations(bridge_request.id)
            required_confirmations = await self._get_required_confirmations(bridge_request.source_chain_id)

            if total_confirmations >= required_confirmations:
                # Update bridge request status
                bridge_request.status = BridgeRequestStatus.CONFIRMED
                bridge_request.confirmed_at = datetime.now(datetime.UTC)

                # Generate Merkle proof for completion
                merkle_proof = await self._generate_merkle_proof(bridge_request)
                bridge_request.merkle_proof = merkle_proof.proof_hash

                logger.info(f"Bridge request {bridge_request.id} confirmed by validators")

            self.session.commit()

            return {
                "request_id": bridge_request.id,
                "confirmations": total_confirmations,
                "required": required_confirmations,
                "status": bridge_request.status.value,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error confirming bridge transfer: {str(e)}")
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    async def complete_bridge_transfer(self, complete_request: BridgeCompleteRequest, executor_address: str) -> dict:
        """Complete bridge transfer on target chain"""

        try:
            # Get bridge request
            bridge_request = self.session.get(BridgeRequest, complete_request.request_id)
            if not bridge_request:
                raise HTTPException(status_code=404, detail="Bridge request not found")

            if bridge_request.status != BridgeRequestStatus.CONFIRMED:
                raise HTTPException(status_code=400, detail="Bridge request not confirmed")

            # Verify Merkle proof
            proof_valid = await self._verify_merkle_proof(complete_request.merkle_proof, bridge_request)
            if not proof_valid:
                raise HTTPException(status_code=400, detail="Invalid Merkle proof")

            # Complete bridge on blockchain
            await self.contract_service.complete_bridge(
                bridge_request.contract_request_id, complete_request.unlock_tx_hash, complete_request.merkle_proof
            )

            # Record completion transaction
            completion = BridgeTransaction(
                bridge_request_id=bridge_request.id,
                validator_address=executor_address,
                transaction_type="completion",
                transaction_hash=complete_request.unlock_tx_hash,
                merkle_proof=complete_request.merkle_proof,
                completed_at=datetime.now(datetime.UTC),
            )

            self.session.add(completion)

            # Update bridge request status
            bridge_request.status = BridgeRequestStatus.COMPLETED
            bridge_request.completed_at = datetime.now(datetime.UTC)
            bridge_request.unlock_tx_hash = complete_request.unlock_tx_hash

            self.session.commit()

            # Stop monitoring
            await self.bridge_monitor.stop_monitoring(bridge_request.id)

            logger.info(f"Completed bridge transfer {bridge_request.id}")

            return {
                "request_id": bridge_request.id,
                "status": "completed",
                "unlock_tx_hash": complete_request.unlock_tx_hash,
                "completed_at": bridge_request.completed_at,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error completing bridge transfer: {str(e)}")
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    async def add_supported_token(self, token_request: TokenSupportRequest) -> dict:
        """Add support for new token"""

        try:
            # Check if token already supported
            existing_token = await self._get_supported_token(token_request.token_address)
            if existing_token:
                raise HTTPException(status_code=400, detail="Token already supported")

            # Create supported token record
            supported_token = SupportedToken(
                token_address=token_request.token_address,
                token_symbol=token_request.token_symbol,
                bridge_limit=token_request.bridge_limit,
                fee_percentage=token_request.fee_percentage,
                requires_whitelist=token_request.requires_whitelist,
                is_active=True,
                created_at=datetime.now(datetime.UTC),
            )

            self.session.add(supported_token)
            self.session.commit()
            self.session.refresh(supported_token)

            logger.info(f"Added supported token {token_request.token_symbol}")

            return {"token_id": supported_token.id, "status": "supported"}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error adding supported token: {str(e)}")
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    async def add_supported_chain(self, chain_request: ChainSupportRequest) -> dict:
        """Add support for new blockchain"""

        try:
            # Check if chain already supported
            existing_chain = await self._get_chain_config(chain_request.chain_id)
            if existing_chain:
                raise HTTPException(status_code=400, detail="Chain already supported")

            # Create chain configuration
            chain_config = ChainConfig(
                chain_id=chain_request.chain_id,
                chain_name=chain_request.chain_name,
                chain_type=chain_request.chain_type,
                bridge_contract_address=chain_request.bridge_contract_address,
                min_confirmations=chain_request.min_confirmations,
                avg_block_time=chain_request.avg_block_time,
                is_active=True,
                created_at=datetime.now(datetime.UTC),
            )

            self.session.add(chain_config)
            self.session.commit()
            self.session.refresh(chain_config)

            logger.info(f"Added supported chain {chain_request.chain_name}")

            return {"chain_id": chain_config.id, "status": "supported"}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error adding supported chain: {str(e)}")
            self.session.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    # Private helper methods

    async def _validate_transfer_request(self, transfer_request: BridgeCreateRequest, sender_address: str) -> ValidationResult:
        """Validate bridge transfer request"""

        # Check addresses
        if not self._is_valid_address(sender_address):
            return ValidationResult(is_valid=False, error_message="Invalid sender address")

        if not self._is_valid_address(transfer_request.recipient_address):
            return ValidationResult(is_valid=False, error_message="Invalid recipient address")

        # Check amount
        if transfer_request.amount <= 0:
            return ValidationResult(is_valid=False, error_message="Amount must be greater than 0")

        if transfer_request.amount > self.max_bridge_amount:
            return ValidationResult(
                is_valid=False, error_message=f"Amount exceeds maximum bridge limit of {self.max_bridge_amount}"
            )

        # Check chains
        if transfer_request.source_chain_id == transfer_request.target_chain_id:
            return ValidationResult(is_valid=False, error_message="Source and target chains must be different")

        return ValidationResult(is_valid=True)

    def _is_valid_address(self, address: str) -> bool:
        """Validate blockchain address"""
        return address.startswith("0x") and len(address) == 42 and all(c in "0123456789abcdefABCDEF" for c in address[2:])

    async def _get_supported_token(self, token_address: str) -> SupportedToken | None:
        """Get supported token configuration"""
        return self.session.execute(select(SupportedToken).where(SupportedToken.token_address == token_address)).first()

    async def _get_chain_config(self, chain_id: int) -> ChainConfig | None:
        """Get chain configuration"""
        return self.session.execute(select(ChainConfig).where(ChainConfig.chain_id == chain_id)).first()

    async def _generate_transfer_zk_proof(self, transfer_request: BridgeCreateRequest, sender_address: str) -> dict:
        """Generate ZK proof for transfer"""

        # Create proof inputs
        proof_inputs = {
            "sender": sender_address,
            "recipient": transfer_request.recipient_address,
            "amount": transfer_request.amount,
            "source_chain": transfer_request.source_chain_id,
            "target_chain": transfer_request.target_chain_id,
            "timestamp": int(datetime.now(datetime.UTC).timestamp()),
        }

        # Generate ZK proof
        zk_proof = await self.zk_proof_service.generate_proof("bridge_transfer", proof_inputs)

        return zk_proof

    async def _get_bridge_confirmations(self, request_id: int) -> list[dict]:
        """Get bridge confirmations"""

        confirmations = self.session.execute(
            select(BridgeTransaction).where(
                BridgeTransaction.bridge_request_id == request_id, BridgeTransaction.transaction_type == "confirmation"
            )
        ).all()

        return [
            {
                "validator_address": conf.validator_address,
                "transaction_hash": conf.transaction_hash,
                "confirmed_at": conf.confirmed_at,
            }
            for conf in confirmations
        ]

    async def _get_bridge_transactions(self, request_id: int) -> list[dict]:
        """Get all bridge transactions"""

        transactions = self.session.execute(
            select(BridgeTransaction).where(BridgeTransaction.bridge_request_id == request_id)
        ).all()

        return [
            {
                "transaction_type": tx.transaction_type,
                "validator_address": tx.validator_address,
                "transaction_hash": tx.transaction_hash,
                "created_at": tx.created_at,
            }
            for tx in transactions
        ]

    async def _calculate_estimated_completion(self, bridge_request: BridgeRequest) -> datetime | None:
        """Calculate estimated completion time"""

        if bridge_request.status in [BridgeRequestStatus.COMPLETED, BridgeRequestStatus.FAILED]:
            return None

        # Get chain configuration
        source_chain = await self._get_chain_config(bridge_request.source_chain_id)
        target_chain = await self._get_chain_config(bridge_request.target_chain_id)

        if not source_chain or not target_chain:
            return None

        # Estimate based on block times and confirmations
        source_confirmation_time = source_chain.avg_block_time * source_chain.min_confirmations
        target_confirmation_time = target_chain.avg_block_time * target_chain.min_confirmations

        total_estimated_time = source_confirmation_time + target_confirmation_time + 300  # 5 min buffer

        return bridge_request.created_at + timedelta(seconds=total_estimated_time)

    async def _analyze_bridge_failure(self, bridge_request: BridgeRequest) -> dict:
        """Analyze bridge failure reason"""

        # This would integrate with monitoring and analytics
        # For now, return basic analysis
        return {"failure_type": "timeout", "failure_reason": "Bridge request expired", "recoverable": True}

    async def _determine_resolution_action(self, bridge_request: BridgeRequest, failure_analysis: dict) -> dict:
        """Determine resolution action for failed bridge"""

        if failure_analysis.get("recoverable", False):
            return {
                "action_type": "refund",
                "refund_amount": bridge_request.total_amount,
                "refund_to": bridge_request.sender_address,
            }
        else:
            return {"action_type": "manual_review", "escalate_to": "support_team"}

    async def _execute_resolution(self, bridge_request: BridgeRequest, resolution_action: dict) -> dict:
        """Execute resolution action"""

        if resolution_action["action_type"] == "refund":
            # Process refund on blockchain
            refund_result = await self.contract_service.process_bridge_refund(
                bridge_request.contract_request_id, resolution_action["refund_amount"], resolution_action["refund_to"]
            )

            return {
                "resolution_type": "refund_processed",
                "refund_tx_hash": refund_result.transaction_hash,
                "refund_amount": resolution_action["refund_amount"],
            }

        return {"resolution_type": "escalated"}

    async def _get_validator(self, validator_address: str) -> Validator | None:
        """Get validator information"""
        return self.session.execute(select(Validator).where(Validator.validator_address == validator_address)).first()

    async def _verify_validator_signature(self, confirm_request: BridgeConfirmRequest, validator_address: str) -> bool:
        """Verify validator signature"""

        # This would implement proper signature verification
        # For now, return True for demonstration
        return True

    async def _count_confirmations(self, request_id: int) -> int:
        """Count confirmations for bridge request"""

        confirmations = self.session.execute(
            select(BridgeTransaction).where(
                BridgeTransaction.bridge_request_id == request_id, BridgeTransaction.transaction_type == "confirmation"
            )
        ).all()

        return len(confirmations)

    async def _get_required_confirmations(self, chain_id: int) -> int:
        """Get required confirmations for chain"""

        chain_config = await self._get_chain_config(chain_id)
        return chain_config.min_confirmations if chain_config else self.min_confirmations

    async def _generate_merkle_proof(self, bridge_request: BridgeRequest) -> MerkleProof:
        """Generate Merkle proof for bridge completion"""

        # Create leaf data
        leaf_data = {
            "request_id": bridge_request.id,
            "sender": bridge_request.sender_address,
            "recipient": bridge_request.recipient_address,
            "amount": bridge_request.amount,
            "target_chain": bridge_request.target_chain_id,
        }

        # Generate Merkle proof
        merkle_proof = await self.merkle_tree_service.generate_proof(leaf_data)

        return merkle_proof

    async def _verify_merkle_proof(self, merkle_proof: list[str], bridge_request: BridgeRequest) -> bool:
        """Verify Merkle proof"""

        # Recreate leaf data
        leaf_data = {
            "request_id": bridge_request.id,
            "sender": bridge_request.sender_address,
            "recipient": bridge_request.recipient_address,
            "amount": bridge_request.amount,
            "target_chain": bridge_request.target_chain_id,
        }

        # Verify proof
        return await self.merkle_tree_service.verify_proof(leaf_data, merkle_proof)


class ValidationResult:
    """Validation result for requests"""

    def __init__(self, is_valid: bool, error_message: str = ""):
        self.is_valid = is_valid
        self.error_message = error_message
