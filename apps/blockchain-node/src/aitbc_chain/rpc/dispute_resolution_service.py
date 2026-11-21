"""Dispute Resolution Service Module"""

import os
from typing import Any

from eth_typing import HexStr
from eth_utils import keccak

from ..contracts.dispute_resolution import dispute_resolution_contract
from ..logger import get_logger

logger = get_logger(__name__)

# Optional on-chain agreement binding for dispute filing (#2052). When both
# env vars are set, file_dispute validates the agreement_id against the real
# AIPowerRental contract on the configured EVM RPC — mirroring
# DisputeResolution.sol: the agreement must exist and the caller/respondent
# must be its provider/consumer pair. Unset -> legacy in-memory sim behavior.
_AGREEMENT_RPC_URL_ENV = "AITBC_DISPUTE_AGREEMENT_RPC_URL"
_AGREEMENT_CONTRACT_ENV = "AITBC_DISPUTE_AGREEMENT_CONTRACT"

# Static head of AIPowerRental.getRentalAgreement's return tuple:
# (agreementId, provider, consumer, duration, price, startTime, endTime,
#  platformFee, status) — 9 x 32 bytes before the dynamic tail.
_GET_RENTAL_AGREEMENT_SELECTOR = "0x" + keccak(text="getRentalAgreement(uint256)")[:4].hex()
_AGREEMENT_HEAD_TYPES = [
    "uint256",
    "address",
    "address",
    "uint256",
    "uint256",
    "uint256",
    "uint256",
    "uint256",
    "uint8",
]
_AGREEMENT_HEAD_LEN = 9 * 32


def _agreement_gate_enabled() -> bool:
    return bool(os.getenv(_AGREEMENT_RPC_URL_ENV) and os.getenv(_AGREEMENT_CONTRACT_ENV))


class DisputeResolutionService:
    """Service for interacting with the DisputeResolution smart contract"""

    def __init__(self) -> None:
        self.contract_address: str | None = None
        self.contract = None
        self._web3 = None
        logger.info("DisputeResolutionService initialized (using in-memory contract implementation)")

    def set_contract_address(self, address: str) -> None:
        """Set the deployed contract address"""
        self.contract_address = address
        logger.info("DisputeResolution contract address set: %s", address)

    def file_dispute(
        self, agreement_id: int, respondent: str, dispute_type: str, reason: str, evidence_hash: str, sender_address: str
    ) -> dict[str, Any]:
        """
        File a new dispute on the blockchain

        Args:
            agreement_id: ID of the agreement being disputed
            respondent: Address of the respondent
            dispute_type: Type of dispute (Performance, Payment, ServiceQuality, Availability, Other)
            reason: Reason for the dispute
            evidence_hash: Hash of initial evidence
            sender_address: Address of the dispute filer

        Returns:
            Dictionary with success status and dispute ID
        """
        try:
            gate_error = self._verify_evm_agreement(agreement_id, sender_address, respondent)
            if gate_error is not None:
                return {"success": False, "error": gate_error}
            return dispute_resolution_contract.file_dispute(
                agreement_id=agreement_id,
                respondent=respondent,
                dispute_type=dispute_type,
                reason=reason,
                evidence_hash=evidence_hash,
                sender_address=sender_address,
            )
        except (LookupError, ValueError, TypeError, AttributeError) as e:
            logger.error("Error filing dispute: %s", e)
            return {"success": False, "error": str(e)}

    @staticmethod
    def _verify_evm_agreement(agreement_id: int, sender_address: str, respondent: str) -> str | None:
        """Validate ``agreement_id`` against AIPowerRental when configured.

        Returns an error string on rejection, ``None`` when the gate is
        disabled or the agreement checks out. Fails closed: any RPC or
        decode error rejects the filing rather than falling back to the
        unverified sim path.
        """
        if not _agreement_gate_enabled():
            return None
        rpc_url = os.environ[_AGREEMENT_RPC_URL_ENV]
        contract_address = os.environ[_AGREEMENT_CONTRACT_ENV]
        gate_errors: tuple[type[BaseException], ...] = (
            ValueError,
            TypeError,
            AttributeError,
            LookupError,
            OSError,
        )
        try:
            from eth_abi import decode, encode
            from eth_utils import to_checksum_address
            from requests.exceptions import RequestException
            from web3 import Web3
            from web3.exceptions import Web3Exception

            gate_errors += (Web3Exception, RequestException)
        except ImportError as e:
            logger.warning("EVM agreement gate dependencies unavailable: %s", e)
            return "Agreement verification unavailable: missing EVM dependencies"
        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))
            if not w3.is_connected():
                return f"Agreement verification unavailable: cannot reach EVM RPC {rpc_url}"
            call_data = HexStr(_GET_RENTAL_AGREEMENT_SELECTOR + encode(["uint256"], [agreement_id]).hex())
            raw = w3.eth.call({"to": to_checksum_address(contract_address), "data": call_data})
            head = decode(_AGREEMENT_HEAD_TYPES, raw[:_AGREEMENT_HEAD_LEN])
            _, provider, consumer = head[0], head[1].lower(), head[2].lower()
        except gate_errors as e:  # RPC unreachable, revert (agreementExists), decode failure
            logger.warning("EVM agreement check failed for agreement %s: %s", agreement_id, e)
            return f"Agreement {agreement_id} not found or unverifiable on AIPowerRental"

        sender = sender_address.lower()
        respondent_l = respondent.lower()
        if sender not in (provider, consumer):
            return "Filer is not a participant of the agreement"
        counterparty = consumer if sender == provider else provider
        if respondent_l != counterparty:
            return "Respondent must be the counterparty of the agreement"
        return None

    def submit_evidence(
        self,
        dispute_id: int,
        evidence_type: str,
        evidence_data: str,
        submitter_address: str,
        evidence_hash: str = "",
    ) -> dict[str, Any]:
        """
        Submit evidence for a dispute

        Args:
            dispute_id: ID of the dispute
            evidence_type: Type of evidence
            evidence_data: Evidence data (IPFS hash, URL, etc.)
            submitter_address: Address of the evidence submitter
            evidence_hash: Content hash supplied by the submitter (#2387)

        Returns:
            Dictionary with success status and evidence ID
        """
        try:
            return dispute_resolution_contract.submit_evidence(
                dispute_id=dispute_id,
                evidence_type=evidence_type,
                evidence_data=evidence_data,
                submitter_address=submitter_address,
                evidence_hash=evidence_hash,
            )
        except (LookupError, ValueError, TypeError, AttributeError) as e:
            logger.error("Error submitting evidence: %s", e)
            return {"success": False, "error": str(e)}

    def verify_evidence(
        self, dispute_id: int, evidence_id: int, is_valid: bool, verification_score: int, arbitrator_address: str
    ) -> dict[str, Any]:
        """
        Verify evidence submitted in a dispute (arbitrator only)

        Args:
            dispute_id: ID of the dispute
            evidence_id: ID of the evidence
            is_valid: Whether the evidence is valid
            verification_score: Verification score (0-100)
            arbitrator_address: Address of the arbitrator

        Returns:
            Dictionary with success status
        """
        try:
            return dispute_resolution_contract.verify_evidence(
                dispute_id=dispute_id,
                evidence_id=evidence_id,
                is_valid=is_valid,
                verification_score=verification_score,
                arbitrator_address=arbitrator_address,
            )
        except (LookupError, ValueError, TypeError, AttributeError) as e:
            logger.error("Error verifying evidence: %s", e)
            return {"success": False, "error": str(e)}

    def submit_arbitration_vote(
        self, dispute_id: int, vote_in_favor_of_initiator: bool, confidence: int, reasoning: str, arbitrator_address: str
    ) -> dict[str, Any]:
        """
        Submit an arbitration vote for a dispute (arbitrator only)

        Args:
            dispute_id: ID of the dispute
            vote_in_favor_of_initiator: Vote for initiator
            confidence: Confidence level (0-100)
            reasoning: Reasoning for the vote
            arbitrator_address: Address of the arbitrator

        Returns:
            Dictionary with success status
        """
        try:
            return dispute_resolution_contract.submit_arbitration_vote(
                dispute_id=dispute_id,
                vote_in_favor_of_initiator=vote_in_favor_of_initiator,
                confidence=confidence,
                reasoning=reasoning,
                arbitrator_address=arbitrator_address,
            )
        except (LookupError, ValueError, TypeError, AttributeError) as e:
            logger.error("Error submitting arbitration vote: %s", e)
            return {"success": False, "error": str(e)}

    def authorize_arbitrator(
        self, arbitrator_address: str, reputation_score: int, owner_address: str, owner_signature: str | None = None
    ) -> dict[str, Any]:
        """
        Authorize a new arbitrator (admin only)

        Args:
            arbitrator_address: Address of the arbitrator
            reputation_score: Initial reputation score
            owner_address: Address of the contract owner
            owner_signature: Signature from the owner proving authorization

        Returns:
            Dictionary with success status
        """
        try:
            return dispute_resolution_contract.authorize_arbitrator(
                arbitrator_address=arbitrator_address,
                reputation_score=reputation_score,
                owner_address=owner_address,
                owner_signature=owner_signature,
            )
        except (LookupError, ValueError, TypeError, AttributeError) as e:
            logger.error("Error authorizing arbitrator: %s", e)
            return {"success": False, "error": str(e)}

    def get_dispute(self, dispute_id: int) -> dict[str, Any]:
        """
        Get details of a specific dispute

        Args:
            dispute_id: ID of the dispute

        Returns:
            Dictionary with dispute details
        """
        try:
            return dispute_resolution_contract.get_dispute(dispute_id)
        except (LookupError, ValueError, TypeError, AttributeError) as e:
            logger.error("Error getting dispute: %s", e)
            return {"success": False, "error": str(e)}

    def get_dispute_evidence(self, dispute_id: int) -> dict[str, Any]:
        """
        Get all evidence submitted for a dispute

        Args:
            dispute_id: ID of the dispute

        Returns:
            Dictionary with evidence list
        """
        try:
            return dispute_resolution_contract.get_dispute_evidence(dispute_id)
        except (LookupError, ValueError, TypeError, AttributeError) as e:
            logger.error("Error getting dispute evidence: %s", e)
            return {"success": False, "error": str(e)}

    def get_arbitration_votes(self, dispute_id: int) -> dict[str, Any]:
        """
        Get all arbitration votes for a dispute

        Args:
            dispute_id: ID of the dispute

        Returns:
            Dictionary with votes list
        """
        try:
            return dispute_resolution_contract.get_arbitration_votes(dispute_id)
        except (LookupError, ValueError, TypeError, AttributeError) as e:
            logger.error("Error getting arbitration votes: %s", e)
            return {"success": False, "error": str(e)}

    def get_user_disputes(self, user_address: str) -> dict[str, Any]:
        """
        Get all disputes for a specific user

        Args:
            user_address: Address of the user

        Returns:
            Dictionary with dispute list
        """
        try:
            return dispute_resolution_contract.get_user_disputes(user_address)
        except (LookupError, ValueError, TypeError, AttributeError) as e:
            logger.error("Error getting user disputes: %s", e)
            return {"success": False, "error": str(e)}

    def get_arbitrator_disputes(self, arbitrator_address: str) -> dict[str, Any]:
        """
        Get all disputes assigned to an arbitrator

        Args:
            arbitrator_address: Address of the arbitrator

        Returns:
            Dictionary with dispute list
        """
        try:
            return dispute_resolution_contract.get_arbitrator_disputes(arbitrator_address)
        except (LookupError, ValueError, TypeError, AttributeError) as e:
            logger.error("Error getting arbitrator disputes: %s", e)
            return {"success": False, "error": str(e)}

    def get_authorized_arbitrators(self) -> dict[str, Any]:
        """
        Get all authorized arbitrators

        Returns:
            Dictionary with arbitrator list
        """
        try:
            return dispute_resolution_contract.get_authorized_arbitrators()
        except (LookupError, ValueError, TypeError, AttributeError) as e:
            logger.error("Error getting authorized arbitrators: %s", e)
            return {"success": False, "error": str(e)}

    def get_active_disputes(self) -> dict[str, Any]:
        """
        Get all active disputes

        Returns:
            Dictionary with dispute list
        """
        try:
            return dispute_resolution_contract.get_active_disputes()
        except (LookupError, ValueError, TypeError, AttributeError) as e:
            logger.error("Error getting active disputes: %s", e)
            return {"success": False, "error": str(e)}


dispute_resolution_service = DisputeResolutionService()
