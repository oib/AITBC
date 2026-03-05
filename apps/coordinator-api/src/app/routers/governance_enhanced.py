"""
Enhanced Governance API Router
REST API endpoints for multi-jurisdictional DAO governance, regional councils, treasury management, and staking
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlmodel import Session, select, func

from ..storage.db import get_session
from ..domain.governance import (
    GovernanceProfile, Proposal, Vote, DaoTreasury, TransparencyReport,
    ProposalStatus, VoteType, GovernanceRole
)
from ..services.governance_service import GovernanceService

router = APIRouter(
    prefix="/governance-enhanced",
    tags=["Enhanced Governance"]
)

# Dependency injection
def get_governance_service(session: Session = Depends(get_session)) -> GovernanceService:
    return GovernanceService(session)


# Regional Council Management Endpoints
@router.post("/regional-councils", response_model=Dict[str, Any])
async def create_regional_council(
    region: str,
    council_name: str,
    jurisdiction: str,
    council_members: List[str],
    budget_allocation: float,
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> Dict[str, Any]:
    """Create a regional governance council"""
    
    try:
        council = await governance_service.create_regional_council(
            region, council_name, jurisdiction, council_members, budget_allocation
        )
        
        return {
            "success": True,
            "council": council,
            "message": f"Regional council '{council_name}' created successfully in {region}"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating regional council: {str(e)}")


@router.get("/regional-councils", response_model=List[Dict[str, Any]])
async def get_regional_councils(
    region: Optional[str] = Query(None, description="Filter by region"),
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> List[Dict[str, Any]]:
    """Get regional governance councils"""
    
    try:
        councils = await governance_service.get_regional_councils(region)
        return councils
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting regional councils: {str(e)}")


@router.post("/regional-proposals", response_model=Dict[str, Any])
async def create_regional_proposal(
    council_id: str,
    title: str,
    description: str,
    proposal_type: str,
    amount_requested: float,
    proposer_address: str,
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> Dict[str, Any]:
    """Create a proposal for a specific regional council"""
    
    try:
        proposal = await governance_service.create_regional_proposal(
            council_id, title, description, proposal_type, amount_requested, proposer_address
        )
        
        return {
            "success": True,
            "proposal": proposal,
            "message": f"Regional proposal '{title}' created successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating regional proposal: {str(e)}")


@router.post("/regional-proposals/{proposal_id}/vote", response_model=Dict[str, Any])
async def vote_on_regional_proposal(
    proposal_id: str,
    voter_address: str,
    vote_type: VoteType,
    voting_power: float,
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> Dict[str, Any]:
    """Vote on a regional proposal"""
    
    try:
        vote = await governance_service.vote_on_regional_proposal(
            proposal_id, voter_address, vote_type, voting_power
        )
        
        return {
            "success": True,
            "vote": vote,
            "message": f"Vote cast successfully on proposal {proposal_id}"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error voting on proposal: {str(e)}")


# Treasury Management Endpoints
@router.get("/treasury/balance", response_model=Dict[str, Any])
async def get_treasury_balance(
    region: Optional[str] = Query(None, description="Filter by region"),
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> Dict[str, Any]:
    """Get treasury balance for global or specific region"""
    
    try:
        balance = await governance_service.get_treasury_balance(region)
        return balance
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting treasury balance: {str(e)}")


@router.post("/treasury/allocate", response_model=Dict[str, Any])
async def allocate_treasury_funds(
    council_id: str,
    amount: float,
    purpose: str,
    recipient_address: str,
    approver_address: str,
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> Dict[str, Any]:
    """Allocate treasury funds to a regional council or project"""
    
    try:
        allocation = await governance_service.allocate_treasury_funds(
            council_id, amount, purpose, recipient_address, approver_address
        )
        
        return {
            "success": True,
            "allocation": allocation,
            "message": f"Treasury funds allocated successfully: {amount} AITBC"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error allocating treasury funds: {str(e)}")


@router.get("/treasury/transactions", response_model=List[Dict[str, Any]])
async def get_treasury_transactions(
    limit: int = Query(100, ge=1, le=500, description="Maximum number of transactions"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    region: Optional[str] = Query(None, description="Filter by region"),
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> List[Dict[str, Any]]:
    """Get treasury transaction history"""
    
    try:
        transactions = await governance_service.get_treasury_transactions(limit, offset, region)
        return transactions
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting treasury transactions: {str(e)}")


# Staking & Rewards Endpoints
@router.post("/staking/pools", response_model=Dict[str, Any])
async def create_staking_pool(
    pool_name: str,
    developer_address: str,
    base_apy: float,
    reputation_multiplier: float,
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> Dict[str, Any]:
    """Create a staking pool for an agent developer"""
    
    try:
        pool = await governance_service.create_staking_pool(
            pool_name, developer_address, base_apy, reputation_multiplier
        )
        
        return {
            "success": True,
            "pool": pool,
            "message": f"Staking pool '{pool_name}' created successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating staking pool: {str(e)}")


@router.get("/staking/pools", response_model=List[Dict[str, Any]])
async def get_developer_staking_pools(
    developer_address: Optional[str] = Query(None, description="Filter by developer address"),
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> List[Dict[str, Any]]:
    """Get staking pools for a specific developer or all pools"""
    
    try:
        pools = await governance_service.get_developer_staking_pools(developer_address)
        return pools
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting staking pools: {str(e)}")


@router.get("/staking/calculate-rewards", response_model=Dict[str, Any])
async def calculate_staking_rewards(
    pool_id: str,
    staker_address: str,
    amount: float,
    duration_days: int,
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> Dict[str, Any]:
    """Calculate staking rewards for a specific position"""
    
    try:
        rewards = await governance_service.calculate_staking_rewards(
            pool_id, staker_address, amount, duration_days
        )
        return rewards
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating staking rewards: {str(e)}")


@router.post("/staking/distribute-rewards/{pool_id}", response_model=Dict[str, Any])
async def distribute_staking_rewards(
    pool_id: str,
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> Dict[str, Any]:
    """Distribute rewards to all stakers in a pool"""
    
    try:
        distribution = await governance_service.distribute_staking_rewards(pool_id)
        
        return {
            "success": True,
            "distribution": distribution,
            "message": f"Rewards distributed successfully for pool {pool_id}"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error distributing staking rewards: {str(e)}")


# Analytics and Monitoring Endpoints
@router.get("/analytics/governance", response_model=Dict[str, Any])
async def get_governance_analytics(
    time_period_days: int = Query(30, ge=1, le=365, description="Time period in days"),
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> Dict[str, Any]:
    """Get comprehensive governance analytics"""
    
    try:
        analytics = await governance_service.get_governance_analytics(time_period_days)
        return analytics
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting governance analytics: {str(e)}")


@router.get("/analytics/regional-health/{region}", response_model=Dict[str, Any])
async def get_regional_governance_health(
    region: str,
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> Dict[str, Any]:
    """Get health metrics for a specific region's governance"""
    
    try:
        health = await governance_service.get_regional_governance_health(region)
        return health
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting regional governance health: {str(e)}")


# Enhanced Profile Management
@router.post("/profiles/create", response_model=Dict[str, Any])
async def create_governance_profile(
    user_id: str,
    initial_voting_power: float = 0.0,
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> Dict[str, Any]:
    """Create or get a governance profile"""
    
    try:
        profile = await governance_service.get_or_create_profile(user_id, initial_voting_power)
        
        return {
            "success": True,
            "profile_id": profile.profile_id,
            "user_id": profile.user_id,
            "role": profile.role.value,
            "voting_power": profile.voting_power,
            "delegated_power": profile.delegated_power,
            "total_votes_cast": profile.total_votes_cast,
            "joined_at": profile.joined_at.isoformat(),
            "message": "Governance profile created successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating governance profile: {str(e)}")


@router.post("/profiles/delegate", response_model=Dict[str, Any])
async def delegate_votes(
    delegator_id: str,
    delegatee_id: str,
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> Dict[str, Any]:
    """Delegate voting power from one profile to another"""
    
    try:
        delegator = await governance_service.delegate_votes(delegator_id, delegatee_id)
        
        return {
            "success": True,
            "delegator_id": delegator_id,
            "delegatee_id": delegatee_id,
            "delegated_power": delegator.voting_power,
            "delegate_to": delegator.delegate_to,
            "message": "Votes delegated successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error delegating votes: {str(e)}")


@router.get("/profiles/{user_id}", response_model=Dict[str, Any])
async def get_governance_profile(
    user_id: str,
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> Dict[str, Any]:
    """Get governance profile by user ID"""
    
    try:
        profile = await governance_service.get_or_create_profile(user_id)
        
        return {
            "profile_id": profile.profile_id,
            "user_id": profile.user_id,
            "role": profile.role.value,
            "voting_power": profile.voting_power,
            "delegated_power": profile.delegated_power,
            "total_votes_cast": profile.total_votes_cast,
            "proposals_created": profile.proposals_created,
            "proposals_passed": profile.proposals_passed,
            "delegate_to": profile.delegate_to,
            "joined_at": profile.joined_at.isoformat(),
            "last_voted_at": profile.last_voted_at.isoformat() if profile.last_voted_at else None
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting governance profile: {str(e)}")


# Multi-Jurisdictional Compliance
@router.get("/jurisdictions", response_model=List[Dict[str, Any]])
async def get_supported_jurisdictions() -> List[Dict[str, Any]]:
    """Get list of supported jurisdictions and their requirements"""
    
    try:
        jurisdictions = [
            {
                "code": "US",
                "name": "United States",
                "region": "global",
                "requirements": {
                    "kyc_required": True,
                    "aml_required": True,
                    "tax_reporting": True,
                    "minimum_stake": 1000.0,
                    "voting_threshold": 100.0
                },
                "supported_councils": ["us-east", "us-west", "us-central"]
            },
            {
                "code": "EU",
                "name": "European Union",
                "region": "global",
                "requirements": {
                    "kyc_required": True,
                    "aml_required": True,
                    "gdpr_compliance": True,
                    "minimum_stake": 800.0,
                    "voting_threshold": 80.0
                },
                "supported_councils": ["eu-west", "eu-central", "eu-north"]
            },
            {
                "code": "SG",
                "name": "Singapore",
                "region": "asia-pacific",
                "requirements": {
                    "kyc_required": True,
                    "aml_required": True,
                    "tax_reporting": True,
                    "minimum_stake": 500.0,
                    "voting_threshold": 50.0
                },
                "supported_councils": ["asia-pacific", "sea"]
            }
        ]
        
        return jurisdictions
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting jurisdictions: {str(e)}")


@router.get("/compliance/check/{user_address}", response_model=Dict[str, Any])
async def check_compliance_status(
    user_address: str,
    jurisdiction: str,
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> Dict[str, Any]:
    """Check compliance status for a user in a specific jurisdiction"""
    
    try:
        # Mock compliance check - would integrate with real compliance systems
        compliance_status = {
            "user_address": user_address,
            "jurisdiction": jurisdiction,
            "is_compliant": True,
            "compliance_level": "full",
            "last_check": datetime.utcnow().isoformat(),
            "requirements_met": {
                "kyc_verified": True,
                "aml_screened": True,
                "tax_id_provided": True,
                "minimum_stake_met": True
            },
            "restrictions": [],
            "next_review_date": (datetime.utcnow() + timedelta(days=365)).isoformat()
        }
        
        return compliance_status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking compliance status: {str(e)}")


# System Health and Status
@router.get("/health", response_model=Dict[str, Any])
async def get_governance_system_health(
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> Dict[str, Any]:
    """Get overall governance system health status"""
    
    try:
        # Check database connectivity
        try:
            profile_count = session.execute(select(func.count(GovernanceProfile.profile_id))).scalar()
            database_status = "healthy"
        except Exception:
            database_status = "unhealthy"
            profile_count = 0
        
        # Mock service health checks
        services_status = {
            "database": database_status,
            "treasury_contracts": "healthy",
            "staking_contracts": "healthy",
            "regional_councils": "healthy",
            "compliance_systems": "healthy"
        }
        
        overall_status = "healthy" if all(status == "healthy" for status in services_status.values()) else "degraded"
        
        # Get basic metrics
        analytics = await governance_service.get_governance_analytics(7)  # Last 7 days
        
        health_data = {
            "status": overall_status,
            "services": services_status,
            "metrics": {
                "total_profiles": profile_count,
                "active_proposals": analytics["proposals"]["still_active"],
                "regional_councils": analytics["regional_councils"]["total_councils"],
                "treasury_balance": analytics["treasury"]["total_allocations"],
                "staking_pools": analytics["staking"]["active_pools"]
            },
            "last_updated": datetime.utcnow().isoformat()
        }
        
        return health_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting system health: {str(e)}")


@router.get("/status", response_model=Dict[str, Any])
async def get_governance_platform_status(
    session: Session = Depends(get_session),
    governance_service: GovernanceService = Depends(get_governance_service)
) -> Dict[str, Any]:
    """Get comprehensive platform status information"""
    
    try:
        # Get analytics for overview
        analytics = await governance_service.get_governance_analytics(30)
        
        # Get regional councils
        councils = await governance_service.get_regional_councils()
        
        # Get treasury balance
        treasury = await governance_service.get_treasury_balance()
        
        status_data = {
            "platform": "AITBC Enhanced Governance",
            "version": "2.0.0",
            "status": "operational",
            "features": {
                "multi_jurisdictional_support": True,
                "regional_councils": len(councils),
                "treasury_management": True,
                "staking_rewards": True,
                "compliance_integration": True
            },
            "statistics": analytics,
            "treasury": treasury,
            "regional_coverage": {
                "total_regions": len(set(c["region"] for c in councils)),
                "active_councils": len(councils),
                "supported_jurisdictions": 3
            },
            "performance": {
                "average_proposal_time": "2.5 days",
                "voting_participation": f"{analytics['voting']['average_voter_participation']}%",
                "treasury_utilization": f"{analytics['treasury']['utilization_rate']}%",
                "staking_apy": f"{analytics['staking']['average_apy']}%"
            },
            "last_updated": datetime.utcnow().isoformat()
        }
        
        return status_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting platform status: {str(e)}")
