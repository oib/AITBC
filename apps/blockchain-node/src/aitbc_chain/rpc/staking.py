"""
Staking-related RPC endpoints.
"""
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request
from sqlmodel import select

from aitbc.rate_limiting import rate_limit

from ..database import session_scope
from ..logger import get_logger
from ..models import Account, AgentIdentity, GovernanceProposal, GovernanceVote, Stake
from .utils import get_chain_id

_logger = get_logger(__name__)

@rate_limit(rate=20, per=60)
async def stake_tokens(request: Request, stake_data: dict[str, Any]) -> dict[str, Any]:
    """
    Stake tokens for consensus participation.
    
    Locks tokens for a specified period. Staked tokens earn rewards
    and provide voting power in consensus.
    """
    chain_id = get_chain_id(stake_data.get('chain_id'))
    address = stake_data.get('address')
    amount = stake_data.get('amount', 0)
    lock_days = stake_data.get('lock_days', 30)
    if not address:
        raise HTTPException(status_code=400, detail='address is required')
    if amount <= 0:
        raise HTTPException(status_code=400, detail='amount must be positive')
    address = address.lower().strip()
    if not address.startswith('0x'):
        address = '0x' + address
    with session_scope() as session:
        account = session.get(Account, (chain_id, address))
        if not account:
            raise HTTPException(status_code=404, detail=f'Account {address} not found')
        if account.balance < amount:
            raise HTTPException(status_code=400, detail=f'Insufficient balance: {account.balance} < {amount}')
        account.balance -= amount
        session.add(account)
        locked_until = datetime.now(UTC)
        locked_until = locked_until.replace(day=locked_until.day + lock_days)
        stake = Stake(chain_id=chain_id, address=address, amount=amount, locked_until=locked_until, status='active')
        session.add(stake)
        session.commit()
        _logger.info('Tokens staked: %s staked %s on %s', address, amount, chain_id)
        return {'success': True, 'stake_id': stake.id, 'address': address, 'amount': amount, 'chain_id': chain_id, 'locked_until': locked_until.isoformat(), 'status': 'active', 'remaining_balance': account.balance}

@rate_limit(rate=10, per=60)
async def unstake_tokens(request: Request, unstake_data: dict[str, Any]) -> dict[str, Any]:
    """
    Unstake tokens after lock period expires.
    
    Returns staked tokens to account balance.
    """
    chain_id = get_chain_id(unstake_data.get('chain_id'))
    address = unstake_data.get('address')
    stake_id = unstake_data.get('stake_id')
    if not address or not stake_id:
        raise HTTPException(status_code=400, detail='address and stake_id are required')
    address = address.lower().strip()
    if not address.startswith('0x'):
        address = '0x' + address
    with session_scope() as session:
        stake = session.get(Stake, stake_id)
        if not stake:
            raise HTTPException(status_code=404, detail=f'Stake {stake_id} not found')
        if stake.address != address:
            raise HTTPException(status_code=403, detail='Not authorized to unstake')
        if stake.status != 'active':
            raise HTTPException(status_code=400, detail=f'Stake is not active: {stake.status}')
        now = datetime.now(UTC)
        if stake.locked_until and now < stake.locked_until:
            raise HTTPException(status_code=400, detail=f'Lock period not expired. Locked until: {stake.locked_until.isoformat()}')
        account = session.get(Account, (chain_id, address))
        if not account:
            account = Account(chain_id=chain_id, address=address, balance=0, nonce=0)
            session.add(account)
        account.balance += stake.amount
        session.add(account)
        stake.status = 'withdrawn'
        session.add(stake)
        session.commit()
        _logger.info('Tokens unstaked: %s recovered %s from stake %s', address, stake.amount, stake_id)
        return {'success': True, 'stake_id': stake_id, 'address': address, 'amount': stake.amount, 'chain_id': chain_id, 'new_balance': account.balance, 'status': 'withdrawn'}

@rate_limit(rate=100, per=60)
async def get_staking_info(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get staking information for an address"""
    chain_id = get_chain_id(chain_id)
    address = address.lower().strip()
    with session_scope() as session:
        statement = select(Stake).where(Stake.chain_id == chain_id, Stake.address == address)
        stakes = session.exec(statement).all()
        total_staked = sum(s.amount for s in stakes if s.status == 'active')
        active_stakes = [{'stake_id': s.id, 'amount': s.amount, 'locked_until': s.locked_until.isoformat() if s.locked_until else None, 'status': s.status, 'created_at': s.created_at.isoformat() if s.created_at else None} for s in stakes if s.status == 'active']
        return {'success': True, 'address': address, 'chain_id': chain_id, 'total_staked': total_staked, 'active_stake_count': len(active_stakes), 'active_stakes': active_stakes}

@rate_limit(rate=20, per=60)
async def register_agent_identity(request: Request, identity_data: dict[str, Any]) -> dict[str, Any]:
    """
    Register an agent identity on the blockchain.
    
    Records agent metadata and verification status on-chain for cross-node verification.
    """
    chain_id = get_chain_id(identity_data.get('chain_id'))
    agent_id = identity_data.get('agent_id')
    agent_address = identity_data.get('agent_address')
    display_name = identity_data.get('display_name')
    agent_type = identity_data.get('agent_type', 'general')
    capabilities = identity_data.get('capabilities', {})
    if not agent_id or not agent_address:
        raise HTTPException(status_code=400, detail='agent_id and agent_address are required')
    agent_address = agent_address.lower().strip()
    if not agent_address.startswith('0x'):
        agent_address = '0x' + agent_address
    with session_scope() as session:
        existing = session.exec(select(AgentIdentity).where(AgentIdentity.chain_id == chain_id, AgentIdentity.agent_id == agent_id)).first()
        if existing:
            raise HTTPException(status_code=400, detail=f'Agent identity already exists: {agent_id}')
        identity = AgentIdentity(chain_id=chain_id, agent_id=agent_id, agent_address=agent_address, display_name=display_name, agent_type=agent_type, capabilities=capabilities, status='active', is_verified=False)
        session.add(identity)
        session.commit()
        session.refresh(identity)
        _logger.info('Agent identity registered on-chain: %s -> %s', agent_id, agent_address)
        return {'success': True, 'identity_id': identity.id, 'agent_id': agent_id, 'agent_address': agent_address, 'chain_id': chain_id, 'status': identity.status, 'is_verified': identity.is_verified}

@rate_limit(rate=50, per=60)
async def get_agent_identity(request: Request, agent_id: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get agent identity from blockchain"""
    chain_id = get_chain_id(chain_id)
    with session_scope() as session:
        identity = session.exec(select(AgentIdentity).where(AgentIdentity.chain_id == chain_id, AgentIdentity.agent_id == agent_id)).first()
        if not identity:
            raise HTTPException(status_code=404, detail=f'Agent identity not found: {agent_id}')
        return {'success': True, 'identity_id': identity.id, 'agent_id': identity.agent_id, 'agent_address': identity.agent_address, 'display_name': identity.display_name, 'agent_type': identity.agent_type, 'capabilities': identity.capabilities, 'status': identity.status, 'is_verified': identity.is_verified, 'verified_at': identity.verified_at.isoformat() if identity.verified_at else None, 'created_at': identity.created_at.isoformat() if identity.created_at else None, 'chain_id': chain_id}

@rate_limit(rate=50, per=60)
async def verify_agent_identity(request: Request, verification_data: dict[str, Any]) -> dict[str, Any]:
    """
    Verify an agent identity on the blockchain.
    
    Marks an agent identity as verified after successful validation.
    """
    chain_id = get_chain_id(verification_data.get('chain_id'))
    agent_id = verification_data.get('agent_id')
    verifier_address = verification_data.get('verifier_address')
    if not agent_id or not verifier_address:
        raise HTTPException(status_code=400, detail='agent_id and verifier_address are required')
    with session_scope() as session:
        identity = session.exec(select(AgentIdentity).where(AgentIdentity.chain_id == chain_id, AgentIdentity.agent_id == agent_id)).first()
        if not identity:
            raise HTTPException(status_code=404, detail=f'Agent identity not found: {agent_id}')
        identity.is_verified = True
        identity.verified_at = datetime.now(UTC)
        identity.verified_by = verifier_address
        session.add(identity)
        session.commit()
        _logger.info('Agent identity verified: %s by %s', agent_id, verifier_address)
        return {'success': True, 'identity_id': identity.id, 'agent_id': agent_id, 'is_verified': True, 'verified_at': identity.verified_at.isoformat(), 'verified_by': verifier_address, 'chain_id': chain_id}

@rate_limit(rate=20, per=60)
async def create_governance_proposal(request: Request, proposal_data: dict[str, Any]) -> dict[str, Any]:
    """
    Create a governance proposal on the blockchain.
    
    Records governance proposals for DAO decision-making.
    """
    chain_id = get_chain_id(proposal_data.get('chain_id'))
    proposal_id = proposal_data.get('proposal_id')
    proposer_address = proposal_data.get('proposer_address')
    title = proposal_data.get('title')
    description = proposal_data.get('description')
    category = proposal_data.get('category', 'general')
    voting_starts = proposal_data.get('voting_starts')
    voting_ends = proposal_data.get('voting_ends')
    execution_payload = proposal_data.get('execution_payload', {})
    if not proposal_id or not proposer_address or (not title):
        raise HTTPException(status_code=400, detail='proposal_id, proposer_address, and title are required')
    proposer_address = proposer_address.lower().strip()
    if not proposer_address.startswith('0x'):
        proposer_address = '0x' + proposer_address
    with session_scope() as session:
        existing = session.exec(select(GovernanceProposal).where(GovernanceProposal.chain_id == chain_id, GovernanceProposal.proposal_id == proposal_id)).first()
        if existing:
            raise HTTPException(status_code=400, detail=f'Proposal already exists: {proposal_id}')
        try:
            voting_starts_dt = datetime.fromisoformat(voting_starts) if voting_starts else datetime.now(UTC)
            voting_ends_dt = datetime.fromisoformat(voting_ends) if voting_ends else voting_starts_dt + timedelta(days=7)
        except Exception:
            voting_starts_dt = datetime.now(UTC)
            voting_ends_dt = voting_starts_dt + timedelta(days=7)
        proposal = GovernanceProposal(chain_id=chain_id, proposal_id=proposal_id, proposer_address=proposer_address, title=title, description=description, category=category, status='active', execution_payload=execution_payload, voting_starts=voting_starts_dt, voting_ends=voting_ends_dt)
        session.add(proposal)
        session.commit()
        session.refresh(proposal)
        _logger.info('Governance proposal created on-chain: %s by %s', proposal_id, proposer_address)
        return {'success': True, 'proposal_id': proposal.proposal_id, 'proposer_address': proposal.proposer_address, 'title': proposal.title, 'status': proposal.status, 'voting_starts': proposal.voting_starts.isoformat(), 'voting_ends': proposal.voting_ends.isoformat(), 'chain_id': chain_id}

@rate_limit(rate=50, per=60)
async def cast_governance_vote(request: Request, vote_data: dict[str, Any]) -> dict[str, Any]:
    """
    Cast a vote on a governance proposal.
    
    Records votes on-chain for proposal decision-making.
    """
    chain_id = get_chain_id(vote_data.get('chain_id'))
    proposal_id = vote_data.get('proposal_id')
    voter_address = vote_data.get('voter_address')
    vote_type = vote_data.get('vote_type', 'for')
    voting_power = vote_data.get('voting_power', 0)
    reason = vote_data.get('reason')
    if not proposal_id or not voter_address:
        raise HTTPException(status_code=400, detail='proposal_id and voter_address are required')
    voter_address = voter_address.lower().strip()
    if not voter_address.startswith('0x'):
        voter_address = '0x' + voter_address
    with session_scope() as session:
        proposal = session.exec(select(GovernanceProposal).where(GovernanceProposal.chain_id == chain_id, GovernanceProposal.proposal_id == proposal_id)).first()
        if not proposal:
            raise HTTPException(status_code=404, detail=f'Proposal not found: {proposal_id}')
        existing_vote = session.exec(select(GovernanceVote).where(GovernanceVote.chain_id == chain_id, GovernanceVote.proposal_id == proposal_id, GovernanceVote.voter_address == voter_address)).first()
        if existing_vote:
            raise HTTPException(status_code=400, detail=f'Already voted on proposal: {proposal_id}')
        vote = GovernanceVote(chain_id=chain_id, proposal_id=proposal_id, voter_address=voter_address, vote_type=vote_type, voting_power=voting_power, reason=reason)
        session.add(vote)
        if vote_type == 'for':
            proposal.votes_for += voting_power
        elif vote_type == 'against':
            proposal.votes_against += voting_power
        else:
            proposal.votes_abstain += voting_power
        session.add(proposal)
        session.commit()
        _logger.info('Governance vote cast: %s voted %s on %s', voter_address, vote_type, proposal_id)
        return {'success': True, 'vote_id': vote.id, 'proposal_id': proposal_id, 'voter_address': voter_address, 'vote_type': vote_type, 'voting_power': voting_power, 'chain_id': chain_id}

@rate_limit(rate=50, per=60)
async def get_governance_proposal(request: Request, proposal_id: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get governance proposal from blockchain"""
    chain_id = get_chain_id(chain_id)
    with session_scope() as session:
        proposal = session.exec(select(GovernanceProposal).where(GovernanceProposal.chain_id == chain_id, GovernanceProposal.proposal_id == proposal_id)).first()
        if not proposal:
            raise HTTPException(status_code=404, detail=f'Proposal not found: {proposal_id}')
        votes = session.exec(select(GovernanceVote).where(GovernanceVote.chain_id == chain_id, GovernanceVote.proposal_id == proposal_id)).all()
        return {'success': True, 'proposal_id': proposal.proposal_id, 'proposer_address': proposal.proposer_address, 'title': proposal.title, 'description': proposal.description, 'category': proposal.category, 'status': proposal.status, 'votes_for': proposal.votes_for, 'votes_against': proposal.votes_against, 'votes_abstain': proposal.votes_abstain, 'quorum_required': proposal.quorum_required, 'passing_threshold': proposal.passing_threshold, 'voting_starts': proposal.voting_starts.isoformat(), 'voting_ends': proposal.voting_ends.isoformat(), 'executed_at': proposal.executed_at.isoformat() if proposal.executed_at else None, 'total_votes': len(votes), 'chain_id': chain_id}
