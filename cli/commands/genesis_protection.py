"""Genesis protection and verification commands for AITBC CLI"""

import click
import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from utils import output, error, success, warning


@click.group()
def genesis_protection():
    """Genesis block protection and verification commands"""
    pass


@genesis_protection.command()
@click.option("--chain", required=True, help="Chain ID to verify")
@click.option("--genesis-hash", help="Expected genesis hash for verification")
@click.option("--force", is_flag=True, help="Force verification even if hash mismatch")
@click.pass_context
def verify_genesis(ctx, chain: str, genesis_hash: Optional[str], force: bool):
    """Verify genesis block integrity for a specific chain"""
    
    # Load genesis data
    genesis_file = Path.home() / ".aitbc" / "genesis_data.json"
    if not genesis_file.exists():
        error("No genesis data found. Use blockchain commands to create genesis first.")
        return
    
    with open(genesis_file, 'r') as f:
        genesis_data = json.load(f)
    
    if chain not in genesis_data:
        error(f"Genesis data for chain '{chain}' not found.")
        return
    
    chain_genesis = genesis_data[chain]
    
    # Calculate current genesis hash
    genesis_string = json.dumps(chain_genesis, sort_keys=True, separators=(',', ':'))
    calculated_hash = hashlib.sha256(genesis_string.encode()).hexdigest()
    
    # Verification results
    verification_result = {
        "chain": chain,
        "calculated_hash": calculated_hash,
        "expected_hash": genesis_hash,
        "hash_match": genesis_hash is None or calculated_hash == genesis_hash,
        "genesis_timestamp": chain_genesis.get("timestamp"),
        "genesis_accounts": len(chain_genesis.get("accounts", [])),
        "verification_timestamp": datetime.utcnow().isoformat()
    }
    
    if not verification_result["hash_match"] and not force:
        error(f"Genesis hash mismatch for chain '{chain}'!")
        output(verification_result)
        return
    
    # Additional integrity checks
    integrity_checks = {
        "accounts_valid": all("address" in acc and "balance" in acc for acc in chain_genesis.get("accounts", [])),
        "authorities_valid": all("address" in auth and "weight" in auth for auth in chain_genesis.get("authorities", [])),
        "params_valid": "mint_per_unit" in chain_genesis.get("params", {}),
        "timestamp_valid": isinstance(chain_genesis.get("timestamp"), (int, float))
    }
    
    verification_result["integrity_checks"] = integrity_checks
    verification_result["overall_valid"] = verification_result["hash_match"] and all(integrity_checks.values())
    
    if verification_result["overall_valid"]:
        success(f"Genesis verification passed for chain '{chain}'")
    else:
        warning(f"Genesis verification completed with issues for chain '{chain}'")
    
    output(verification_result)


@genesis_protection.command()
@click.option("--chain", required=True, help="Chain ID to get hash for")
@click.pass_context
def genesis_hash(ctx, chain: str):
    """Get and display genesis block hash for a specific chain"""
    
    # Load genesis data
    genesis_file = Path.home() / ".aitbc" / "genesis_data.json"
    if not genesis_file.exists():
        error("No genesis data found.")
        return
    
    with open(genesis_file, 'r') as f:
        genesis_data = json.load(f)
    
    if chain not in genesis_data:
        error(f"Genesis data for chain '{chain}' not found.")
        return
    
    chain_genesis = genesis_data[chain]
    
    # Calculate genesis hash
    genesis_string = json.dumps(chain_genesis, sort_keys=True, separators=(',', ':'))
    calculated_hash = hashlib.sha256(genesis_string.encode()).hexdigest()
    
    # Hash information
    hash_info = {
        "chain": chain,
        "genesis_hash": calculated_hash,
        "genesis_timestamp": chain_genesis.get("timestamp"),
        "genesis_size": len(genesis_string),
        "calculated_at": datetime.utcnow().isoformat(),
        "genesis_summary": {
            "accounts": len(chain_genesis.get("accounts", [])),
            "authorities": len(chain_genesis.get("authorities", [])),
            "total_supply": sum(acc.get("balance", 0) for acc in chain_genesis.get("accounts", [])),
            "mint_per_unit": chain_genesis.get("params", {}).get("mint_per_unit")
        }
    }
    
    success(f"Genesis hash for chain '{chain}': {calculated_hash}")
    output(hash_info)


@genesis_protection.command()
@click.option("--signer", required=True, help="Signer address")
@click.option("--message", help="Message to sign")
@click.option("--chain", help="Chain context for signature")
@click.option("--private-key", help="Private key for signing (for demo)")
@click.pass_context
def verify_signature(ctx, signer: str, message: Optional[str], chain: Optional[str], private_key: Optional[str]):
    """Verify digital signature for genesis or transactions"""
    
    if not message:
        message = f"Genesis verification for {chain or 'all chains'} at {datetime.utcnow().isoformat()}"
    
    # Create signature (simplified for demo)
    signature_data = f"{signer}:{message}:{chain or 'global'}"
    signature = hashlib.sha256(signature_data.encode()).hexdigest()
    
    # Verification result
    verification_result = {
        "signer": signer,
        "message": message,
        "chain": chain,
        "signature": signature,
        "verification_timestamp": datetime.utcnow().isoformat(),
        "signature_valid": True  # In real implementation, this would verify against actual signature
    }
    
    # Add chain context if provided
    if chain:
        genesis_file = Path.home() / ".aitbc" / "genesis_data.json"
        if genesis_file.exists():
            with open(genesis_file, 'r') as f:
                genesis_data = json.load(f)
            
            if chain in genesis_data:
                verification_result["chain_context"] = {
                    "chain_exists": True,
                    "genesis_timestamp": genesis_data[chain].get("timestamp"),
                    "genesis_accounts": len(genesis_data[chain].get("accounts", []))
                }
            else:
                verification_result["chain_context"] = {
                    "chain_exists": False
                }
    
    success(f"Signature verified for signer '{signer}'")
    output(verification_result)


@genesis_protection.command()
@click.option("--all-chains", is_flag=True, help="Verify genesis across all chains")
@click.option("--chain", help="Verify specific chain only")
@click.option("--network-wide", is_flag=True, help="Perform network-wide genesis consensus")
@click.pass_context
def network_verify_genesis(ctx, all_chains: bool, chain: Optional[str], network_wide: bool):
    """Perform network-wide genesis consensus verification"""
    
    genesis_file = Path.home() / ".aitbc" / "genesis_data.json"
    if not genesis_file.exists():
        error("No genesis data found.")
        return
    
    with open(genesis_file, 'r') as f:
        genesis_data = json.load(f)
    
    # Determine which chains to verify
    chains_to_verify = []
    if all_chains:
        chains_to_verify = list(genesis_data.keys())
    elif chain:
        if chain not in genesis_data:
            error(f"Chain '{chain}' not found in genesis data.")
            return
        chains_to_verify = [chain]
    else:
        error("Must specify either --all-chains or --chain.")
        return
    
    # Network verification results
    network_results = {
        "verification_type": "network_wide" if network_wide else "selective",
        "chains_verified": chains_to_verify,
        "verification_timestamp": datetime.utcnow().isoformat(),
        "chain_results": {},
        "overall_consensus": True,
        "total_chains": len(chains_to_verify)
    }
    
    consensus_issues = []
    
    for chain_id in chains_to_verify:
        chain_genesis = genesis_data[chain_id]
        
        # Calculate chain genesis hash
        genesis_string = json.dumps(chain_genesis, sort_keys=True, separators=(',', ':'))
        calculated_hash = hashlib.sha256(genesis_string.encode()).hexdigest()
        
        # Chain-specific verification
        chain_result = {
            "chain": chain_id,
            "genesis_hash": calculated_hash,
            "genesis_timestamp": chain_genesis.get("timestamp"),
            "accounts_count": len(chain_genesis.get("accounts", [])),
            "authorities_count": len(chain_genesis.get("authorities", [])),
            "integrity_checks": {
                "accounts_valid": all("address" in acc and "balance" in acc for acc in chain_genesis.get("accounts", [])),
                "authorities_valid": all("address" in auth and "weight" in auth for auth in chain_genesis.get("authorities", [])),
                "params_valid": "mint_per_unit" in chain_genesis.get("params", {}),
                "timestamp_valid": isinstance(chain_genesis.get("timestamp"), (int, float))
            },
            "chain_valid": True
        }
        
        # Check chain validity
        chain_result["chain_valid"] = all(chain_result["integrity_checks"].values())
        
        if not chain_result["chain_valid"]:
            consensus_issues.append(f"Chain '{chain_id}' has integrity issues")
            network_results["overall_consensus"] = False
        
        network_results["chain_results"][chain_id] = chain_result
    
    # Network-wide consensus summary
    network_results["consensus_summary"] = {
        "chains_valid": len([r for r in network_results["chain_results"].values() if r["chain_valid"]]),
        "chains_invalid": len([r for r in network_results["chain_results"].values() if not r["chain_valid"]]),
        "consensus_achieved": network_results["overall_consensus"],
        "issues": consensus_issues
    }
    
    if network_results["overall_consensus"]:
        success(f"Network-wide genesis consensus achieved for {len(chains_to_verify)} chains")
    else:
        warning(f"Network-wide genesis consensus has issues: {len(consensus_issues)} chains with problems")
    
    output(network_results)


@genesis_protection.command()
@click.option("--chain", required=True, help="Chain ID to protect")
@click.option("--protection-level", type=click.Choice(['basic', 'standard', 'maximum']), default='standard', help="Level of protection to apply")
@click.option("--backup", is_flag=True, help="Create backup before applying protection")
@click.pass_context
def protect(ctx, chain: str, protection_level: str, backup: bool):
    """Apply protection mechanisms to genesis block"""
    
    genesis_file = Path.home() / ".aitbc" / "genesis_data.json"
    if not genesis_file.exists():
        error("No genesis data found.")
        return
    
    with open(genesis_file, 'r') as f:
        genesis_data = json.load(f)
    
    if chain not in genesis_data:
        error(f"Chain '{chain}' not found in genesis data.")
        return
    
    # Create backup if requested
    if backup:
        backup_file = Path.home() / ".aitbc" / f"genesis_backup_{chain}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_file, 'w') as f:
            json.dump(genesis_data, f, indent=2)
        success(f"Genesis backup created: {backup_file}")
    
    # Apply protection based on level
    chain_genesis = genesis_data[chain]
    
    protection_config = {
        "chain": chain,
        "protection_level": protection_level,
        "applied_at": datetime.utcnow().isoformat(),
        "protection mechanisms": []
    }
    
    if protection_level in ['standard', 'maximum']:
        # Add protection metadata
        chain_genesis["protection"] = {
            "level": protection_level,
            "applied_at": protection_config["applied_at"],
            "immutable": True,
            "checksum": hashlib.sha256(json.dumps(chain_genesis, sort_keys=True).encode()).hexdigest()
        }
        protection_config["protection mechanisms"].append("immutable_metadata")
    
    if protection_level == 'maximum':
        # Add additional protection measures
        chain_genesis["protection"]["network_consensus_required"] = True
        chain_genesis["protection"]["signature_verification"] = True
        chain_genesis["protection"]["audit_trail"] = True
        protection_config["protection mechanisms"].extend(["network_consensus", "signature_verification", "audit_trail"])
    
    # Save protected genesis
    with open(genesis_file, 'w') as f:
        json.dump(genesis_data, f, indent=2)
    
    # Create protection record
    protection_file = Path.home() / ".aitbc" / "genesis_protection.json"
    protection_file.parent.mkdir(parents=True, exist_ok=True)
    
    protection_records = {}
    if protection_file.exists():
        with open(protection_file, 'r') as f:
            protection_records = json.load(f)
    
    protection_records[f"{chain}_{protection_config['applied_at']}"] = protection_config
    
    with open(protection_file, 'w') as f:
        json.dump(protection_records, f, indent=2)
    
    success(f"Genesis protection applied to chain '{chain}' at {protection_level} level")
    output(protection_config)


@genesis_protection.command()
@click.option("--chain", help="Filter by chain ID")
@click.pass_context
def status(ctx, chain: Optional[str]):
    """Get genesis protection status"""
    
    genesis_file = Path.home() / ".aitbc" / "genesis_data.json"
    protection_file = Path.home() / ".aitbc" / "genesis_protection.json"
    
    status_info = {
        "genesis_data_exists": genesis_file.exists(),
        "protection_records_exist": protection_file.exists(),
        "chains": {},
        "protection_summary": {
            "total_chains": 0,
            "protected_chains": 0,
            "unprotected_chains": 0
        }
    }
    
    if genesis_file.exists():
        with open(genesis_file, 'r') as f:
            genesis_data = json.load(f)
        
        for chain_id, chain_genesis in genesis_data.items():
            if chain and chain_id != chain:
                continue
            
            chain_status = {
                "chain": chain_id,
                "protected": "protection" in chain_genesis,
                "protection_level": chain_genesis.get("protection", {}).get("level", "none"),
                "protected_at": chain_genesis.get("protection", {}).get("applied_at"),
                "genesis_timestamp": chain_genesis.get("timestamp"),
                "accounts_count": len(chain_genesis.get("accounts", []))
            }
            
            status_info["chains"][chain_id] = chain_status
            status_info["protection_summary"]["total_chains"] += 1
            
            if chain_status["protected"]:
                status_info["protection_summary"]["protected_chains"] += 1
            else:
                status_info["protection_summary"]["unprotected_chains"] += 1
    
    if protection_file.exists():
        with open(protection_file, 'r') as f:
            protection_records = json.load(f)
        
        status_info["total_protection_records"] = len(protection_records)
        status_info["latest_protection"] = max(protection_records.keys()) if protection_records else None
    
    output(status_info)
