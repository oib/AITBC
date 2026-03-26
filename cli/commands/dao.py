#!/usr/bin/env python3
"""
OpenClaw DAO CLI Commands
Provides command-line interface for DAO governance operations
"""

import click
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any
from web3 import Web3
from utils.blockchain import get_web3_connection, get_contract
from utils.config import load_config

@click.group()
def dao():
    """OpenClaw DAO governance commands"""
    pass

@dao.command()
@click.option('--token-address', required=True, help='Governance token contract address')
@click.option('--timelock-address', required=True, help='Timelock controller address')
@click.option('--network', default='mainnet', help='Blockchain network')
def deploy(token_address: str, timelock_address: str, network: str):
    """Deploy OpenClaw DAO contract"""
    try:
        w3 = get_web3_connection(network)
        config = load_config()
        
        # Account for deployment
        account = w3.eth.account.from_key(config['private_key'])
        
        # Contract ABI (simplified)
        abi = [
            {
                "inputs": [
                    {"internalType": "address", "name": "_governanceToken", "type": "address"},
                    {"internalType": "contract TimelockController", "name": "_timelock", "type": "address"}
                ],
                "stateMutability": "nonpayable",
                "type": "constructor"
            }
        ]
        
        # Deploy contract
        contract = w3.eth.contract(abi=abi, bytecode="0x...")  # Actual bytecode needed
        
        # Build transaction
        tx = contract.constructor(token_address, timelock_address).build_transaction({
            'from': account.address,
            'gas': 2000000,
            'gasPrice': w3.eth.gas_price,
            'nonce': w3.eth.get_transaction_count(account.address)
        })
        
        # Sign and send
        signed_tx = w3.eth.account.sign_transaction(tx, config['private_key'])
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        # Wait for confirmation
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        click.echo(f"✅ OpenClaw DAO deployed at: {receipt.contractAddress}")
        click.echo(f"📦 Transaction hash: {tx_hash.hex()}")
        
    except Exception as e:
        click.echo(f"❌ Deployment failed: {str(e)}", err=True)

@dao.command()
@click.option('--dao-address', required=True, help='DAO contract address')
@click.option('--targets', required=True, help='Comma-separated target addresses')
@click.option('--values', required=True, help='Comma-separated ETH values')
@click.option('--calldatas', required=True, help='Comma-separated hex calldatas')
@click.option('--description', required=True, help='Proposal description')
@click.option('--type', 'proposal_type', type=click.Choice(['0', '1', '2', '3']), 
              default='0', help='Proposal type (0=parameter, 1=upgrade, 2=treasury, 3=emergency)')
def propose(dao_address: str, targets: str, values: str, calldatas: str, 
           description: str, proposal_type: str):
    """Create a new governance proposal"""
    try:
        w3 = get_web3_connection()
        config = load_config()
        
        # Parse inputs
        target_addresses = targets.split(',')
        value_list = [int(v) for v in values.split(',')]
        calldata_list = calldatas.split(',')
        
        # Get contract
        dao_contract = get_contract(dao_address, "OpenClawDAO")
        
        # Build transaction
        tx = dao_contract.functions.propose(
            target_addresses,
            value_list,
            calldata_list,
            description,
            int(proposal_type)
        ).build_transaction({
            'from': config['address'],
            'gas': 500000,
            'gasPrice': w3.eth.gas_price,
            'nonce': w3.eth.get_transaction_count(config['address'])
        })
        
        # Sign and send
        signed_tx = w3.eth.account.sign_transaction(tx, config['private_key'])
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        # Get proposal ID
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        # Parse proposal ID from events
        proposal_id = None
        for log in receipt.logs:
            try:
                event = dao_contract.events.ProposalCreated().process_log(log)
                proposal_id = event.args.proposalId
                break
            except:
                continue
        
        click.echo(f"✅ Proposal created!")
        click.echo(f"📋 Proposal ID: {proposal_id}")
        click.echo(f"📦 Transaction hash: {tx_hash.hex()}")
        
    except Exception as e:
        click.echo(f"❌ Proposal creation failed: {str(e)}", err=True)

@dao.command()
@click.option('--dao-address', required=True, help='DAO contract address')
@click.option('--proposal-id', required=True, type=int, help='Proposal ID')
def vote(dao_address: str, proposal_id: int):
    """Cast a vote on a proposal"""
    try:
        w3 = get_web3_connection()
        config = load_config()
        
        # Get contract
        dao_contract = get_contract(dao_address, "OpenClawDAO")
        
        # Check proposal state
        state = dao_contract.functions.state(proposal_id).call()
        if state != 1:  # Active
            click.echo("❌ Proposal is not active for voting")
            return
        
        # Get voting power
        token_address = dao_contract.functions.governanceToken().call()
        token_contract = get_contract(token_address, "ERC20")
        voting_power = token_contract.functions.balanceOf(config['address']).call()
        
        if voting_power == 0:
            click.echo("❌ No voting power (no governance tokens)")
            return
        
        click.echo(f"🗳️ Your voting power: {voting_power}")
        
        # Get vote choice
        support = click.prompt(
            "Vote (0=Against, 1=For, 2=Abstain)",
            type=click.Choice(['0', '1', '2'])
        )
        
        reason = click.prompt("Reason (optional)", default="", show_default=False)
        
        # Build transaction
        tx = dao_contract.functions.castVoteWithReason(
            proposal_id,
            int(support),
            reason
        ).build_transaction({
            'from': config['address'],
            'gas': 100000,
            'gasPrice': w3.eth.gas_price,
            'nonce': w3.eth.get_transaction_count(config['address'])
        })
        
        # Sign and send
        signed_tx = w3.eth.account.sign_transaction(tx, config['private_key'])
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        click.echo(f"✅ Vote cast!")
        click.echo(f"📦 Transaction hash: {tx_hash.hex()}")
        
    except Exception as e:
        click.echo(f"❌ Voting failed: {str(e)}", err=True)

@dao.command()
@click.option('--dao-address', required=True, help='DAO contract address')
@click.option('--proposal-id', required=True, type=int, help='Proposal ID')
def execute(dao_address: str, proposal_id: int):
    """Execute a successful proposal"""
    try:
        w3 = get_web3_connection()
        config = load_config()
        
        # Get contract
        dao_contract = get_contract(dao_address, "OpenClawDAO")
        
        # Check proposal state
        state = dao_contract.functions.state(proposal_id).call()
        if state != 7:  # Succeeded
            click.echo("❌ Proposal has not succeeded")
            return
        
        # Build transaction
        tx = dao_contract.functions.execute(proposal_id).build_transaction({
            'from': config['address'],
            'gas': 300000,
            'gasPrice': w3.eth.gas_price,
            'nonce': w3.eth.get_transaction_count(config['address'])
        })
        
        # Sign and send
        signed_tx = w3.eth.account.sign_transaction(tx, config['private_key'])
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        click.echo(f"✅ Proposal executed!")
        click.echo(f"📦 Transaction hash: {tx_hash.hex()}")
        
    except Exception as e:
        click.echo(f"❌ Execution failed: {str(e)}", err=True)

@dao.command()
@click.option('--dao-address', required=True, help='DAO contract address')
def list_proposals(dao_address: str):
    """List all proposals"""
    try:
        w3 = get_web3_connection()
        dao_contract = get_contract(dao_address, "OpenClawDAO")
        
        # Get proposal count
        proposal_count = dao_contract.functions.proposalCount().call()
        
        click.echo(f"📋 Found {proposal_count} proposals:\n")
        
        for i in range(1, proposal_count + 1):
            try:
                proposal = dao_contract.functions.getProposal(i).call()
                state = dao_contract.functions.state(i).call()
                
                state_names = {
                    0: "Pending",
                    1: "Active", 
                    2: "Canceled",
                    3: "Defeated",
                    4: "Succeeded",
                    5: "Queued",
                    6: "Expired",
                    7: "Executed"
                }
                
                type_names = {
                    0: "Parameter Change",
                    1: "Protocol Upgrade", 
                    2: "Treasury Allocation",
                    3: "Emergency Action"
                }
                
                click.echo(f"🔹 Proposal #{i}")
                click.echo(f"   Type: {type_names.get(proposal[3], 'Unknown')}")
                click.echo(f"   State: {state_names.get(state, 'Unknown')}")
                click.echo(f"   Description: {proposal[4]}")
                click.echo(f"   For: {proposal[6]}, Against: {proposal[7]}, Abstain: {proposal[8]}")
                click.echo()
                
            except Exception as e:
                continue
                
    except Exception as e:
        click.echo(f"❌ Failed to list proposals: {str(e)}", err=True)

@dao.command()
@click.option('--dao-address', required=True, help='DAO contract address')
def status(dao_address: str):
    """Show DAO status and statistics"""
    try:
        w3 = get_web3_connection()
        dao_contract = get_contract(dao_address, "OpenClawDAO")
        
        # Get DAO info
        token_address = dao_contract.functions.governanceToken().call()
        token_contract = get_contract(token_address, "ERC20")
        
        total_supply = token_contract.functions.totalSupply().call()
        proposal_count = dao_contract.functions.proposalCount().call()
        
        # Get active proposals
        active_proposals = dao_contract.functions.getActiveProposals().call()
        
        click.echo("🏛️ OpenClaw DAO Status")
        click.echo("=" * 40)
        click.echo(f"📊 Total Supply: {total_supply / 1e18:.2f} tokens")
        click.echo(f"📋 Total Proposals: {proposal_count}")
        click.echo(f"🗳️ Active Proposals: {len(active_proposals)}")
        click.echo(f"🪙 Governance Token: {token_address}")
        click.echo(f"🏛️ DAO Address: {dao_address}")
        
        # Voting parameters
        voting_delay = dao_contract.functions.votingDelay().call()
        voting_period = dao_contract.functions.votingPeriod().call()
        quorum = dao_contract.functions.quorum(w3.eth.block_number).call()
        threshold = dao_contract.functions.proposalThreshold().call()
        
        click.echo(f"\n⚙️ Voting Parameters:")
        click.echo(f"   Delay: {voting_delay // 86400} days")
        click.echo(f"   Period: {voting_period // 86400} days")
        click.echo(f"   Quorum: {quorum / 1e18:.2f} tokens ({(quorum * 100 / total_supply):.2f}%)")
        click.echo(f"   Threshold: {threshold / 1e18:.2f} tokens")
        
    except Exception as e:
        click.echo(f"❌ Failed to get status: {str(e)}", err=True)

if __name__ == '__main__':
    dao()
