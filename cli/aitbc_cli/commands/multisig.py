"""Multi-signature wallet commands for AITBC CLI"""

import click
import json
import hashlib
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from ..utils import output, error, success, warning


@click.group()
def multisig():
    """Multi-signature wallet management commands"""
    pass


@multisig.command()
@click.option("--threshold", type=int, required=True, help="Number of signatures required")
@click.option("--owners", required=True, help="Comma-separated list of owner addresses")
@click.option("--name", help="Wallet name for identification")
@click.option("--description", help="Wallet description")
@click.pass_context
def create(ctx, threshold: int, owners: str, name: Optional[str], description: Optional[str]):
    """Create a multi-signature wallet"""
    
    # Parse owners list
    owner_list = [owner.strip() for owner in owners.split(',')]
    
    if threshold < 1 or threshold > len(owner_list):
        error(f"Threshold must be between 1 and {len(owner_list)}")
        return
    
    # Generate unique wallet ID
    wallet_id = f"multisig_{str(uuid.uuid4())[:8]}"
    
    # Create multisig wallet configuration
    wallet_config = {
        "wallet_id": wallet_id,
        "name": name or f"Multi-sig Wallet {wallet_id}",
        "threshold": threshold,
        "owners": owner_list,
        "status": "active",
        "created_at": datetime.utcnow().isoformat(),
        "description": description or f"Multi-signature wallet with {threshold}/{len(owner_list)} threshold",
        "transactions": [],
        "proposals": [],
        "balance": 0.0
    }
    
    # Store wallet configuration
    multisig_file = Path.home() / ".aitbc" / "multisig_wallets.json"
    multisig_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Load existing wallets
    wallets = {}
    if multisig_file.exists():
        with open(multisig_file, 'r') as f:
            wallets = json.load(f)
    
    # Add new wallet
    wallets[wallet_id] = wallet_config
    
    # Save wallets
    with open(multisig_file, 'w') as f:
        json.dump(wallets, f, indent=2)
    
    success(f"Multi-signature wallet created: {wallet_id}")
    output({
        "wallet_id": wallet_id,
        "name": wallet_config["name"],
        "threshold": threshold,
        "owners": owner_list,
        "status": "created",
        "created_at": wallet_config["created_at"]
    })


@multisig.command()
@click.option("--wallet-id", required=True, help="Multi-signature wallet ID")
@click.option("--recipient", required=True, help="Recipient address")
@click.option("--amount", type=float, required=True, help="Amount to send")
@click.option("--description", help="Transaction description")
@click.pass_context
def propose(ctx, wallet_id: str, recipient: str, amount: float, description: Optional[str]):
    """Propose a transaction for multi-signature approval"""
    
    # Load wallets
    multisig_file = Path.home() / ".aitbc" / "multisig_wallets.json"
    if not multisig_file.exists():
        error("No multi-signature wallets found.")
        return
    
    with open(multisig_file, 'r') as f:
        wallets = json.load(f)
    
    if wallet_id not in wallets:
        error(f"Multi-signature wallet '{wallet_id}' not found.")
        return
    
    wallet = wallets[wallet_id]
    
    # Generate proposal ID
    proposal_id = f"prop_{str(uuid.uuid4())[:8]}"
    
    # Create transaction proposal
    proposal = {
        "proposal_id": proposal_id,
        "wallet_id": wallet_id,
        "recipient": recipient,
        "amount": amount,
        "description": description or f"Send {amount} to {recipient}",
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "signatures": [],
        "threshold": wallet["threshold"],
        "owners": wallet["owners"]
    }
    
    # Add proposal to wallet
    wallet["proposals"].append(proposal)
    
    # Save wallets
    with open(multisig_file, 'w') as f:
        json.dump(wallets, f, indent=2)
    
    success(f"Transaction proposal created: {proposal_id}")
    output({
        "proposal_id": proposal_id,
        "wallet_id": wallet_id,
        "recipient": recipient,
        "amount": amount,
        "threshold": wallet["threshold"],
        "status": "pending",
        "created_at": proposal["created_at"]
    })


@multisig.command()
@click.option("--proposal-id", required=True, help="Proposal ID to sign")
@click.option("--signer", required=True, help="Signer address")
@click.option("--private-key", help="Private key for signing (for demo)")
@click.pass_context
def sign(ctx, proposal_id: str, signer: str, private_key: Optional[str]):
    """Sign a transaction proposal"""
    
    # Load wallets
    multisig_file = Path.home() / ".aitbc" / "multisig_wallets.json"
    if not multisig_file.exists():
        error("No multi-signature wallets found.")
        return
    
    with open(multisig_file, 'r') as f:
        wallets = json.load(f)
    
    # Find the proposal
    target_wallet = None
    target_proposal = None
    
    for wallet_id, wallet in wallets.items():
        for proposal in wallet.get("proposals", []):
            if proposal["proposal_id"] == proposal_id:
                target_wallet = wallet
                target_proposal = proposal
                break
        if target_proposal:
            break
    
    if not target_proposal:
        error(f"Proposal '{proposal_id}' not found.")
        return
    
    # Check if signer is an owner
    if signer not in target_proposal["owners"]:
        error(f"Signer '{signer}' is not an owner of this wallet.")
        return
    
    # Check if already signed
    for sig in target_proposal["signatures"]:
        if sig["signer"] == signer:
            warning(f"Signer '{signer}' has already signed this proposal.")
            return
    
    # Create signature (simplified for demo)
    signature_data = f"{proposal_id}:{signer}:{target_proposal['amount']}"
    signature = hashlib.sha256(signature_data.encode()).hexdigest()
    
    # Add signature
    signature_obj = {
        "signer": signer,
        "signature": signature,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    target_proposal["signatures"].append(signature_obj)
    
    # Check if threshold reached
    if len(target_proposal["signatures"]) >= target_proposal["threshold"]:
        target_proposal["status"] = "approved"
        target_proposal["approved_at"] = datetime.utcnow().isoformat()
        
        # Add to transactions
        transaction = {
            "tx_id": f"tx_{str(uuid.uuid4())[:8]}",
            "proposal_id": proposal_id,
            "recipient": target_proposal["recipient"],
            "amount": target_proposal["amount"],
            "description": target_proposal["description"],
            "executed_at": target_proposal["approved_at"],
            "signatures": target_proposal["signatures"]
        }
        target_wallet["transactions"].append(transaction)
        
        success(f"Transaction approved and executed! Transaction ID: {transaction['tx_id']}")
    else:
        success(f"Signature added. {len(target_proposal['signatures'])}/{target_proposal['threshold']} signatures collected.")
    
    # Save wallets
    with open(multisig_file, 'w') as f:
        json.dump(wallets, f, indent=2)
    
    output({
        "proposal_id": proposal_id,
        "signer": signer,
        "signatures_collected": len(target_proposal["signatures"]),
        "threshold": target_proposal["threshold"],
        "status": target_proposal["status"]
    })


@multisig.command()
@click.option("--wallet-id", help="Filter by wallet ID")
@click.option("--status", help="Filter by status (pending, approved, rejected)")
@click.pass_context
def list(ctx, wallet_id: Optional[str], status: Optional[str]):
    """List multi-signature wallets and proposals"""
    
    # Load wallets
    multisig_file = Path.home() / ".aitbc" / "multisig_wallets.json"
    if not multisig_file.exists():
        warning("No multi-signature wallets found.")
        return
    
    with open(multisig_file, 'r') as f:
        wallets = json.load(f)
    
    # Filter wallets
    wallet_list = []
    for wid, wallet in wallets.items():
        if wallet_id and wid != wallet_id:
            continue
        
        wallet_info = {
            "wallet_id": wid,
            "name": wallet["name"],
            "threshold": wallet["threshold"],
            "owners": wallet["owners"],
            "status": wallet["status"],
            "created_at": wallet["created_at"],
            "balance": wallet.get("balance", 0.0),
            "total_proposals": len(wallet.get("proposals", [])),
            "total_transactions": len(wallet.get("transactions", []))
        }
        
        # Filter proposals by status if specified
        if status:
            filtered_proposals = [p for p in wallet.get("proposals", []) if p.get("status") == status]
            wallet_info["filtered_proposals"] = len(filtered_proposals)
        
        wallet_list.append(wallet_info)
    
    if not wallet_list:
        error("No multi-signature wallets found matching the criteria.")
        return
    
    output({
        "multisig_wallets": wallet_list,
        "total_wallets": len(wallet_list),
        "filter_criteria": {
            "wallet_id": wallet_id or "all",
            "status": status or "all"
        }
    })


@multisig.command()
@click.argument("wallet_id")
@click.pass_context
def status(ctx, wallet_id: str):
    """Get detailed status of a multi-signature wallet"""
    
    # Load wallets
    multisig_file = Path.home() / ".aitbc" / "multisig_wallets.json"
    if not multisig_file.exists():
        error("No multi-signature wallets found.")
        return
    
    with open(multisig_file, 'r') as f:
        wallets = json.load(f)
    
    if wallet_id not in wallets:
        error(f"Multi-signature wallet '{wallet_id}' not found.")
        return
    
    wallet = wallets[wallet_id]
    
    output({
        "wallet_id": wallet_id,
        "name": wallet["name"],
        "threshold": wallet["threshold"],
        "owners": wallet["owners"],
        "status": wallet["status"],
        "balance": wallet.get("balance", 0.0),
        "created_at": wallet["created_at"],
        "description": wallet.get("description"),
        "proposals": wallet.get("proposals", []),
        "transactions": wallet.get("transactions", [])
    })


@multisig.command()
@click.option("--proposal-id", help="Filter by proposal ID")
@click.option("--wallet-id", help="Filter by wallet ID")
@click.pass_context
def proposals(ctx, proposal_id: Optional[str], wallet_id: Optional[str]):
    """List transaction proposals"""
    
    # Load wallets
    multisig_file = Path.home() / ".aitbc" / "multisig_wallets.json"
    if not multisig_file.exists():
        warning("No multi-signature wallets found.")
        return
    
    with open(multisig_file, 'r') as f:
        wallets = json.load(f)
    
    # Collect proposals
    all_proposals = []
    
    for wid, wallet in wallets.items():
        if wallet_id and wid != wallet_id:
            continue
            
        for proposal in wallet.get("proposals", []):
            if proposal_id and proposal["proposal_id"] != proposal_id:
                continue
            
            proposal_info = {
                "proposal_id": proposal["proposal_id"],
                "wallet_id": wid,
                "wallet_name": wallet["name"],
                "recipient": proposal["recipient"],
                "amount": proposal["amount"],
                "description": proposal["description"],
                "status": proposal["status"],
                "threshold": proposal["threshold"],
                "signatures": proposal["signatures"],
                "created_at": proposal["created_at"]
            }
            
            if proposal.get("approved_at"):
                proposal_info["approved_at"] = proposal["approved_at"]
            
            all_proposals.append(proposal_info)
    
    if not all_proposals:
        error("No proposals found matching the criteria.")
        return
    
    output({
        "proposals": all_proposals,
        "total_proposals": len(all_proposals),
        "filter_criteria": {
            "proposal_id": proposal_id or "all",
            "wallet_id": wallet_id or "all"
        }
    })


@multisig.command()
@click.argument("proposal_id")
@click.pass_context
def challenge(ctx, proposal_id: str):
    """Create a challenge-response for proposal verification"""
    
    # Load wallets
    multisig_file = Path.home() / ".aitbc" / "multisig_wallets.json"
    if not multisig_file.exists():
        error("No multi-signature wallets found.")
        return
    
    with open(multisig_file, 'r') as f:
        wallets = json.load(f)
    
    # Find the proposal
    target_proposal = None
    for wallet in wallets.values():
        for proposal in wallet.get("proposals", []):
            if proposal["proposal_id"] == proposal_id:
                target_proposal = proposal
                break
        if target_proposal:
            break
    
    if not target_proposal:
        error(f"Proposal '{proposal_id}' not found.")
        return
    
    # Create challenge
    challenge_data = {
        "challenge_id": f"challenge_{str(uuid.uuid4())[:8]}",
        "proposal_id": proposal_id,
        "challenge": hashlib.sha256(f"{proposal_id}:{datetime.utcnow().isoformat()}".encode()).hexdigest(),
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat()
    }
    
    # Store challenge (in a real implementation, this would be more secure)
    challenges_file = Path.home() / ".aitbc" / "multisig_challenges.json"
    challenges_file.parent.mkdir(parents=True, exist_ok=True)
    
    challenges = {}
    if challenges_file.exists():
        with open(challenges_file, 'r') as f:
            challenges = json.load(f)
    
    challenges[challenge_data["challenge_id"]] = challenge_data
    
    with open(challenges_file, 'w') as f:
        json.dump(challenges, f, indent=2)
    
    success(f"Challenge created: {challenge_data['challenge_id']}")
    output({
        "challenge_id": challenge_data["challenge_id"],
        "proposal_id": proposal_id,
        "challenge": challenge_data["challenge"],
        "expires_at": challenge_data["expires_at"]
    })
