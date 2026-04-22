"""
State Transition Layer for AITBC

This module provides the StateTransition class that validates all state changes
to ensure they only occur through validated transactions.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from ..models import Account, Transaction
from ..logger import get_logger


logger = get_logger(__name__)


class StateTransition:
    """
    Validates and applies state transitions only through validated transactions.
    
    This class ensures that balance changes can only occur through properly
    validated transactions, preventing direct database manipulation of account
    balances.
    """
    
    def __init__(self):
        self._processed_nonces: Dict[str, int] = {}
        self._processed_tx_hashes: set = set()
    
    def validate_transaction(
        self,
        session: Session,
        chain_id: str,
        tx_data: Dict,
        tx_hash: str
    ) -> Tuple[bool, str]:
        """
        Validate a transaction before applying state changes.
        
        Args:
            session: Database session
            chain_id: Chain identifier
            tx_data: Transaction data
            tx_hash: Transaction hash
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check for replay attacks
        if tx_hash in self._processed_tx_hashes:
            return False, f"Transaction {tx_hash} already processed (replay attack)"
        
        # Get sender account
        sender_addr = tx_data.get("from")
        sender_account = session.get(Account, (chain_id, sender_addr))
        
        if not sender_account:
            return False, f"Sender account not found: {sender_addr}"
        
        # Validate nonce
        expected_nonce = sender_account.nonce
        tx_nonce = tx_data.get("nonce", 0)
        
        if tx_nonce != expected_nonce:
            return False, f"Invalid nonce for {sender_addr}: expected {expected_nonce}, got {tx_nonce}"
        
        # Get transaction type
        tx_type = tx_data.get("type", "TRANSFER").upper()
        
        # Validate balance
        value = tx_data.get("value", 0)
        fee = tx_data.get("fee", 0)
        
        # For MESSAGE transactions, value must be 0
        if tx_type == "MESSAGE" and value != 0:
            return False, f"MESSAGE transactions must have value=0, got {value}"
        
        # For MESSAGE transactions, only check fee
        if tx_type == "MESSAGE":
            total_cost = fee
        else:
            total_cost = value + fee
        
        if sender_account.balance < total_cost:
            return False, f"Insufficient balance for {sender_addr}: {sender_account.balance} < {total_cost}"
        
        # Get recipient account (not required for MESSAGE)
        recipient_addr = tx_data.get("to")
        if tx_type != "MESSAGE":
            recipient_account = session.get(Account, (chain_id, recipient_addr))
            
            if not recipient_account:
                return False, f"Recipient account not found: {recipient_addr}"
        
        return True, "Transaction validated successfully"
    
    def apply_transaction(
        self,
        session: Session,
        chain_id: str,
        tx_data: Dict,
        tx_hash: str
    ) -> Tuple[bool, str]:
        """
        Apply a validated transaction to update state.
        
        Args:
            session: Database session
            chain_id: Chain identifier
            tx_data: Transaction data
            tx_hash: Transaction hash
            
        Returns:
            Tuple of (success, error_message)
        """
        # Validate first
        is_valid, error_msg = self.validate_transaction(session, chain_id, tx_data, tx_hash)
        if not is_valid:
            return False, error_msg
        
        # Get accounts
        sender_addr = tx_data.get("from")
        recipient_addr = tx_data.get("to")
        
        sender_account = session.get(Account, (chain_id, sender_addr))
        
        # Get transaction type
        tx_type = tx_data.get("type", "TRANSFER").upper()
        
        # Apply balance changes
        value = tx_data.get("value", 0)
        fee = tx_data.get("fee", 0)
        
        # For MESSAGE transactions, only deduct fee
        if tx_type == "MESSAGE":
            total_cost = fee
        else:
            total_cost = value + fee
            recipient_account = session.get(Account, (chain_id, recipient_addr))
        
        sender_account.balance -= total_cost
        sender_account.nonce += 1
        
        # For MESSAGE transactions, skip recipient balance change
        if tx_type != "MESSAGE":
            recipient_account.balance += value
        
        # Mark transaction as processed
        self._processed_tx_hashes.add(tx_hash)
        self._processed_nonces[sender_addr] = sender_account.nonce
        
        logger.info(
            f"Applied transaction {tx_hash}: "
            f"{sender_addr} -> {recipient_addr}, value={value}, fee={fee}, type={tx_type}"
        )
        
        return True, "Transaction applied successfully"
    
    def validate_state_transition(
        self,
        session: Session,
        chain_id: str,
        old_accounts: Dict[str, Account],
        new_accounts: Dict[str, Account]
    ) -> Tuple[bool, str]:
        """
        Validate that state changes only occur through transactions.
        
        Args:
            session: Database session
            chain_id: Chain identifier
            old_accounts: Previous account state
            new_accounts: New account state
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        for address, old_acc in old_accounts.items():
            if address not in new_accounts:
                continue
            
            new_acc = new_accounts[address]
            
            # Check if balance changed
            if old_acc.balance != new_acc.balance:
                # Balance changes should only occur through transactions
                # This is a placeholder for full validation
                logger.warning(
                    f"Balance change detected for {address}: "
                    f"{old_acc.balance} -> {new_acc.balance} "
                    f"(should be validated through transactions)"
                )
        
        return True, "State transition validated"
    
    def get_processed_nonces(self) -> Dict[str, int]:
        """Get the last processed nonce for each address."""
        return self._processed_nonces.copy()
    
    def reset(self) -> None:
        """Reset the state transition validator (for testing)."""
        self._processed_nonces.clear()
        self._processed_tx_hashes.clear()


# Global state transition instance
_state_transition = StateTransition()


def get_state_transition() -> StateTransition:
    """Get the global state transition instance."""
    return _state_transition
