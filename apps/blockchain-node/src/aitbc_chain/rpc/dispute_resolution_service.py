"""Dispute Resolution Service Module"""
from typing import Dict, Any, List, Optional
from ..logger import get_logger
from ..contracts.dispute_resolution import dispute_resolution_contract

logger = get_logger(__name__)


class DisputeResolutionService:
    """Service for interacting with the DisputeResolution smart contract"""
    
    def __init__(self):
        # TODO: Initialize web3 connection and contract instance
        self.contract_address = None
        self.contract = None
    
    def set_contract_address(self, address: str):
        """Set the deployed contract address"""
        self.contract_address = address
        logger.info(f"DisputeResolution contract address set: {address}")
    
    def file_dispute(
        self,
        agreement_id: int,
        respondent: str,
        dispute_type: str,
        reason: str,
        evidence_hash: str,
        sender_address: str
    ) -> Dict[str, Any]:
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
            return dispute_resolution_contract.file_dispute(
                agreement_id=agreement_id,
                respondent=respondent,
                dispute_type=dispute_type,
                reason=reason,
                evidence_hash=evidence_hash,
                sender_address=sender_address
            )
        except Exception as e:
            logger.error(f"Error filing dispute: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def submit_evidence(
        self,
        dispute_id: int,
        evidence_type: str,
        evidence_data: str,
        submitter_address: str
    ) -> Dict[str, Any]:
        """
        Submit evidence for a dispute
        
        Args:
            dispute_id: ID of the dispute
            evidence_type: Type of evidence
            evidence_data: Evidence data (IPFS hash, URL, etc.)
            submitter_address: Address of the evidence submitter
            
        Returns:
            Dictionary with success status and evidence ID
        """
        try:
            return dispute_resolution_contract.submit_evidence(
                dispute_id=dispute_id,
                evidence_type=evidence_type,
                evidence_data=evidence_data,
                submitter_address=submitter_address
            )
        except Exception as e:
            logger.error(f"Error submitting evidence: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def verify_evidence(
        self,
        dispute_id: int,
        evidence_id: int,
        is_valid: bool,
        verification_score: int,
        arbitrator_address: str
    ) -> Dict[str, Any]:
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
                arbitrator_address=arbitrator_address
            )
        except Exception as e:
            logger.error(f"Error verifying evidence: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def submit_arbitration_vote(
        self,
        dispute_id: int,
        vote_in_favor_of_initiator: bool,
        confidence: int,
        reasoning: str,
        arbitrator_address: str
    ) -> Dict[str, Any]:
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
                arbitrator_address=arbitrator_address
            )
        except Exception as e:
            logger.error(f"Error submitting arbitration vote: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def authorize_arbitrator(
        self,
        arbitrator_address: str,
        reputation_score: int,
        owner_address: str
    ) -> Dict[str, Any]:
        """
        Authorize a new arbitrator (admin only)
        
        Args:
            arbitrator_address: Address of the arbitrator
            reputation_score: Initial reputation score
            owner_address: Address of the contract owner
            
        Returns:
            Dictionary with success status
        """
        try:
            return dispute_resolution_contract.authorize_arbitrator(
                arbitrator_address=arbitrator_address,
                reputation_score=reputation_score,
                owner_address=owner_address
            )
        except Exception as e:
            logger.error(f"Error authorizing arbitrator: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_dispute(self, dispute_id: int) -> Dict[str, Any]:
        """
        Get details of a specific dispute
        
        Args:
            dispute_id: ID of the dispute
            
        Returns:
            Dictionary with dispute details
        """
        try:
            return dispute_resolution_contract.get_dispute(dispute_id)
        except Exception as e:
            logger.error(f"Error getting dispute: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_dispute_evidence(self, dispute_id: int) -> Dict[str, Any]:
        """
        Get all evidence submitted for a dispute
        
        Args:
            dispute_id: ID of the dispute
            
        Returns:
            Dictionary with evidence list
        """
        try:
            return dispute_resolution_contract.get_dispute_evidence(dispute_id)
        except Exception as e:
            logger.error(f"Error getting dispute evidence: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_arbitration_votes(self, dispute_id: int) -> Dict[str, Any]:
        """
        Get all arbitration votes for a dispute
        
        Args:
            dispute_id: ID of the dispute
            
        Returns:
            Dictionary with votes list
        """
        try:
            return dispute_resolution_contract.get_arbitration_votes(dispute_id)
        except Exception as e:
            logger.error(f"Error getting arbitration votes: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_user_disputes(self, user_address: str) -> Dict[str, Any]:
        """
        Get all disputes for a specific user
        
        Args:
            user_address: Address of the user
            
        Returns:
            Dictionary with dispute list
        """
        try:
            return dispute_resolution_contract.get_user_disputes(user_address)
        except Exception as e:
            logger.error(f"Error getting user disputes: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_arbitrator_disputes(self, arbitrator_address: str) -> Dict[str, Any]:
        """
        Get all disputes assigned to an arbitrator
        
        Args:
            arbitrator_address: Address of the arbitrator
            
        Returns:
            Dictionary with dispute list
        """
        try:
            return dispute_resolution_contract.get_arbitrator_disputes(arbitrator_address)
        except Exception as e:
            logger.error(f"Error getting arbitrator disputes: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_authorized_arbitrators(self) -> Dict[str, Any]:
        """
        Get all authorized arbitrators
        
        Returns:
            Dictionary with arbitrator list
        """
        try:
            return dispute_resolution_contract.get_authorized_arbitrators()
        except Exception as e:
            logger.error(f"Error getting authorized arbitrators: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_active_disputes(self) -> Dict[str, Any]:
        """
        Get all active disputes
        
        Returns:
            Dictionary with dispute list
        """
        try:
            return dispute_resolution_contract.get_active_disputes()
        except Exception as e:
            logger.error(f"Error getting active disputes: {e}")
            return {
                "success": False,
                "error": str(e)
            }


dispute_resolution_service = DisputeResolutionService()
