"""
Developer Platform API Router
REST API endpoints for the developer ecosystem including bounties, certifications, and regional hubs
"""

from datetime import datetime, UTC
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, func, select

from ..domain.developer_platform import (
    BountyStatus,
    CertificationLevel,
    DeveloperCertification,
    DeveloperProfile,
    RegionalHub,
)
from ..schemas.developer_platform import BountyCreate, BountySubmissionCreate, CertificationGrant, DeveloperCreate
from ..services.developer_platform_service import DeveloperPlatformService
from ..services.governance_service import GovernanceService
from ..storage.db import get_session

router = APIRouter(prefix="/developer-platform", tags=["Developer Platform"])


# Dependency injection
def get_developer_platform_service(session: Session = Depends(get_session)) -> DeveloperPlatformService:
    return DeveloperPlatformService(session)


def get_governance_service(session: Session = Depends(get_session)) -> GovernanceService:
    return GovernanceService(session)


# Developer Management Endpoints
@router.post("/register", response_model=dict[str, Any])
async def register_developer(
    request: DeveloperCreate,
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> dict[str, Any]:
    """Register a new developer profile"""

    try:
        profile = await dev_service.register_developer(request)

        return {
            "success": True,
            "profile_id": profile.id,
            "wallet_address": profile.wallet_address,
            "reputation_score": profile.reputation_score,
            "created_at": profile.created_at.isoformat(),
            "message": "Developer profile registered successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error registering developer")


@router.get("/profile/{wallet_address}", response_model=dict[str, Any])
async def get_developer_profile(
    wallet_address: str,
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> dict[str, Any]:
    """Get developer profile by wallet address"""

    try:
        profile = await dev_service.get_developer_profile(wallet_address)
        if not profile:
            raise HTTPException(status_code=404, detail="Developer profile not found")

        return {
            "id": profile.id,
            "wallet_address": profile.wallet_address,
            "github_handle": profile.github_handle,
            "email": profile.email,
            "reputation_score": profile.reputation_score,
            "total_earned_aitbc": profile.total_earned_aitbc,
            "skills": profile.skills,
            "is_active": profile.is_active,
            "created_at": profile.created_at.isoformat(),
            "updated_at": profile.updated_at.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting developer profile")


@router.put("/profile/{wallet_address}", response_model=dict[str, Any])
async def update_developer_profile(
    wallet_address: str,
    updates: dict[str, Any],
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> dict[str, Any]:
    """Update developer profile"""

    try:
        profile = await dev_service.update_developer_profile(wallet_address, updates)

        return {
            "success": True,
            "profile_id": profile.id,
            "wallet_address": profile.wallet_address,
            "updated_at": profile.updated_at.isoformat(),
            "message": "Developer profile updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error updating developer profile")


@router.get("/leaderboard", response_model=list[dict[str, Any]])
async def get_leaderboard(
    limit: int = Query(100, ge=1, le=500, description="Maximum number of developers"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> list[dict[str, Any]]:
    """Get developer leaderboard sorted by reputation score"""

    try:
        developers = await dev_service.get_leaderboard(limit, offset)

        return [
            {
                "rank": offset + i + 1,
                "id": dev.id,
                "wallet_address": dev.wallet_address,
                "github_handle": dev.github_handle,
                "reputation_score": dev.reputation_score,
                "total_earned_aitbc": dev.total_earned_aitbc,
                "skills_count": len(dev.skills),
                "created_at": dev.created_at.isoformat(),
            }
            for i, dev in enumerate(developers)
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting leaderboard")


@router.get("/stats/{wallet_address}", response_model=dict[str, Any])
async def get_developer_stats(
    wallet_address: str,
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> dict[str, Any]:
    """Get comprehensive developer statistics"""

    try:
        stats = await dev_service.get_developer_stats(wallet_address)
        return stats

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting developer stats")


# Bounty Management Endpoints
@router.post("/bounties", response_model=dict[str, Any])
async def create_bounty(
    request: BountyCreate,
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> dict[str, Any]:
    """Create a new bounty task"""

    try:
        bounty = await dev_service.create_bounty(request)

        return {
            "success": True,
            "bounty_id": bounty.id,
            "title": bounty.title,
            "reward_amount": bounty.reward_amount,
            "difficulty_level": bounty.difficulty_level.value,
            "status": bounty.status.value,
            "created_at": bounty.created_at.isoformat(),
            "deadline": bounty.deadline.isoformat() if bounty.deadline else None,
            "message": "Bounty created successfully",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error creating bounty")


@router.get("/bounties", response_model=list[dict[str, Any]])
async def list_bounties(
    status: BountyStatus | None = Query(None, description="Filter by bounty status"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of bounties"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> list[dict[str, Any]]:
    """List bounty tasks with optional status filter"""

    try:
        bounties = await dev_service.list_bounties(status, limit, offset)

        return [
            {
                "id": bounty.id,
                "title": bounty.title,
                "description": bounty.description[:200] + "..." if len(bounty.description) > 200 else bounty.description,
                "reward_amount": bounty.reward_amount,
                "difficulty_level": bounty.difficulty_level.value,
                "required_skills": bounty.required_skills,
                "status": bounty.status.value,
                "creator_address": bounty.creator_address,
                "created_at": bounty.created_at.isoformat(),
                "deadline": bounty.deadline.isoformat() if bounty.deadline else None,
            }
            for bounty in bounties
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error listing bounties")


@router.get("/bounties/{bounty_id}", response_model=dict[str, Any])
async def get_bounty_details(
    bounty_id: str,
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> dict[str, Any]:
    """Get detailed bounty information"""

    try:
        bounty_details = await dev_service.get_bounty_details(bounty_id)
        return bounty_details

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting bounty details")


@router.post("/bounties/{bounty_id}/submit", response_model=dict[str, Any])
async def submit_bounty_solution(
    bounty_id: str,
    request: BountySubmissionCreate,
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> dict[str, Any]:
    """Submit a solution for a bounty"""

    try:
        submission = await dev_service.submit_bounty(bounty_id, request)

        return {
            "success": True,
            "submission_id": submission.id,
            "bounty_id": bounty_id,
            "developer_id": request.developer_id,
            "github_pr_url": submission.github_pr_url,
            "submitted_at": submission.submitted_at.isoformat(),
            "status": "submitted",
            "message": "Bounty solution submitted successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error submitting bounty solution")


@router.get("/bounties/my-submissions", response_model=list[dict[str, Any]])
async def get_my_submissions(
    developer_id: str,
    limit: int = Query(100, ge=1, le=500, description="Maximum number of submissions"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> list[dict[str, Any]]:
    """Get all submissions by a developer"""

    try:
        submissions = await dev_service.get_my_submissions(developer_id)

        return [
            {
                "id": sub.id,
                "bounty_id": sub.bounty_id,
                "bounty_title": sub.bounty.title,
                "reward_amount": sub.bounty.reward_amount,
                "github_pr_url": sub.github_pr_url,
                "submission_notes": sub.submission_notes,
                "is_approved": sub.is_approved,
                "review_notes": sub.review_notes,
                "submitted_at": sub.submitted_at.isoformat(),
                "reviewed_at": sub.reviewed_at.isoformat() if sub.reviewed_at else None,
            }
            for sub in submissions[offset : offset + limit]
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting submissions")


@router.post("/bounties/{bounty_id}/review", response_model=dict[str, Any])
async def review_bounty_submission(
    submission_id: str,
    reviewer_address: str,
    review_notes: str,
    approved: bool = Query(True, description="Whether to approve the submission"),
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> dict[str, Any]:
    """Review and approve/reject a bounty submission"""

    try:
        if approved:
            submission = await dev_service.approve_submission(submission_id, reviewer_address, review_notes)
        else:
            # In a real implementation, would have a reject method
            raise HTTPException(status_code=400, detail="Rejection not implemented in this demo")

        return {
            "success": True,
            "submission_id": submission.id,
            "bounty_id": submission.bounty_id,
            "developer_address": submission.developer.wallet_address,
            "reward_amount": submission.bounty.reward_amount,
            "is_approved": submission.is_approved,
            "tx_hash_reward": submission.tx_hash_reward,
            "reviewed_at": submission.reviewed_at.isoformat(),
            "message": "Submission approved and reward distributed",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error reviewing submission")


@router.get("/bounties/stats", response_model=dict[str, Any])
async def get_bounty_statistics(
    session: Session = Depends(get_session), dev_service: DeveloperPlatformService = Depends(get_developer_platform_service)
) -> dict[str, Any]:
    """Get comprehensive bounty statistics"""

    try:
        stats = await dev_service.get_bounty_statistics()
        return stats

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting bounty statistics")


# Certification Management Endpoints
@router.post("/certifications", response_model=dict[str, Any])
async def grant_certification(
    request: CertificationGrant,
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> dict[str, Any]:
    """Grant a certification to a developer"""

    try:
        certification = await dev_service.grant_certification(request)

        return {
            "success": True,
            "certification_id": certification.id,
            "developer_id": request.developer_id,
            "certification_name": request.certification_name,
            "level": request.level.value,
            "issued_by": request.issued_by,
            "ipfs_credential_cid": request.ipfs_credential_cid,
            "granted_at": certification.granted_at.isoformat(),
            "message": "Certification granted successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error granting certification")


@router.get("/certifications/{wallet_address}", response_model=list[dict[str, Any]])
async def get_developer_certifications(
    wallet_address: str,
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> list[dict[str, Any]]:
    """Get certifications for a developer"""

    try:
        profile = await dev_service.get_developer_profile(wallet_address)
        if not profile:
            raise HTTPException(status_code=404, detail="Developer profile not found")

        certifications = session.execute(
            select(DeveloperCertification).where(DeveloperCertification.developer_id == profile.id)
        ).all()

        return [
            {
                "id": cert.id,
                "certification_name": cert.certification_name,
                "level": cert.level.value,
                "issued_by": cert.issued_by,
                "ipfs_credential_cid": cert.ipfs_credential_cid,
                "granted_at": cert.granted_at.isoformat(),
                "is_verified": True,
            }
            for cert in certifications
        ]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting certifications")


@router.get("/certifications/verify/{certification_id}", response_model=dict[str, Any])
async def verify_certification(certification_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Verify a certification by ID"""

    try:
        certification = session.get(DeveloperCertification, certification_id)
        if not certification:
            raise HTTPException(status_code=404, detail="Certification not found")

        return {
            "certification_id": certification_id,
            "certification_name": certification.certification_name,
            "level": certification.level.value,
            "developer_id": certification.developer_id,
            "issued_by": certification.issued_by,
            "granted_at": certification.granted_at.isoformat(),
            "is_valid": True,
            "verification_timestamp": datetime.now(datetime.UTC).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error verifying certification")


@router.get("/certifications/types", response_model=list[dict[str, Any]])
async def get_certification_types() -> list[dict[str, Any]]:
    """Get available certification types"""

    try:
        certification_types = [
            {
                "name": "Blockchain Development",
                "levels": [level.value for level in CertificationLevel],
                "description": "Blockchain and smart contract development skills",
                "skills_required": ["solidity", "web3", "defi"],
            },
            {
                "name": "AI/ML Development",
                "levels": [level.value for level in CertificationLevel],
                "description": "Artificial Intelligence and Machine Learning development",
                "skills_required": ["python", "tensorflow", "pytorch"],
            },
            {
                "name": "Full-Stack Development",
                "levels": [level.value for level in CertificationLevel],
                "description": "Complete web application development",
                "skills_required": ["javascript", "react", "nodejs"],
            },
            {
                "name": "DevOps Engineering",
                "levels": [level.value for level in CertificationLevel],
                "description": "Development operations and infrastructure",
                "skills_required": ["docker", "kubernetes", "ci-cd"],
            },
        ]

        return certification_types

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting certification types")


# Regional Hub Management Endpoints
@router.post("/hubs", response_model=dict[str, Any])
async def create_regional_hub(
    name: str,
    region: str,
    description: str,
    manager_address: str,
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> dict[str, Any]:
    """Create a regional developer hub"""

    try:
        hub = await dev_service.create_regional_hub(name, region, description, manager_address)

        return {
            "success": True,
            "hub_id": hub.id,
            "name": hub.name,
            "region": hub.region,
            "description": hub.description,
            "manager_address": hub.manager_address,
            "is_active": hub.is_active,
            "created_at": hub.created_at.isoformat(),
            "message": "Regional hub created successfully",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error creating regional hub")


@router.get("/hubs", response_model=list[dict[str, Any]])
async def get_regional_hubs(
    session: Session = Depends(get_session), dev_service: DeveloperPlatformService = Depends(get_developer_platform_service)
) -> list[dict[str, Any]]:
    """Get all regional developer hubs"""

    try:
        hubs = await dev_service.get_regional_hubs()

        return [
            {
                "id": hub.id,
                "name": hub.name,
                "region": hub.region,
                "description": hub.description,
                "manager_address": hub.manager_address,
                "developer_count": 0,  # Would be calculated from hub membership
                "is_active": hub.is_active,
                "created_at": hub.created_at.isoformat(),
            }
            for hub in hubs
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting regional hubs")


@router.get("/hubs/{hub_id}/developers", response_model=list[dict[str, Any]])
async def get_hub_developers(
    hub_id: str,
    limit: int = Query(100, ge=1, le=500, description="Maximum number of developers"),
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> list[dict[str, Any]]:
    """Get developers in a regional hub"""

    try:
        developers = await dev_service.get_hub_developers(hub_id)

        return [
            {
                "id": dev.id,
                "wallet_address": dev.wallet_address,
                "github_handle": dev.github_handle,
                "reputation_score": dev.reputation_score,
                "skills": dev.skills,
                "joined_at": dev.created_at.isoformat(),
            }
            for dev in developers[:limit]
        ]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting hub developers")


# Staking & Rewards Endpoints
@router.post("/stake", response_model=dict[str, Any])
async def stake_on_developer(
    staker_address: str,
    developer_address: str,
    amount: float,
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> dict[str, Any]:
    """Stake AITBC tokens on a developer"""

    # Validate addresses to prevent SSRF
    import re
    ADDRESS_PATTERN = re.compile(r'^[a-zA-Z0-9]{20,50}$')
    
    def validate_address(addr: str) -> bool:
        if not addr:
            return False
        if any(char in addr for char in ['/', '\\', '..', '\n', '\r', '\t']):
            return False
        if addr.startswith(('http://', 'https://', 'ftp://')):
            return False
        return bool(ADDRESS_PATTERN.match(addr))
    
    if not validate_address(staker_address) or not validate_address(developer_address):
        raise HTTPException(status_code=400, detail="Invalid address format")

    try:
        staking_info = await dev_service.stake_on_developer(staker_address, developer_address, amount)

        return staking_info

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error staking on developer")


@router.get("/staking/{address}", response_model=dict[str, Any])
async def get_staking_info(
    address: str,
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> dict[str, Any]:
    """Get staking information for an address"""

    try:
        staking_info = await dev_service.get_staking_info(address)
        return staking_info

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting staking info")


@router.post("/unstake", response_model=dict[str, Any])
async def unstake_tokens(
    staking_id: str,
    amount: float,
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> dict[str, Any]:
    """Unstake tokens from a developer"""

    try:
        unstake_info = await dev_service.unstake_tokens(staking_id, amount)
        return unstake_info

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error unstaking tokens")


@router.get("/rewards/{address}", response_model=dict[str, Any])
async def get_rewards(
    address: str,
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> dict[str, Any]:
    """Get reward information for an address"""

    try:
        rewards = await dev_service.get_rewards(address)
        return rewards

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting rewards")


@router.post("/claim-rewards", response_model=dict[str, Any])
async def claim_rewards(
    address: str,
    session: Session = Depends(get_session),
    dev_service: DeveloperPlatformService = Depends(get_developer_platform_service),
) -> dict[str, Any]:
    """Claim pending rewards"""

    try:
        claim_info = await dev_service.claim_rewards(address)
        return claim_info

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error claiming rewards")


@router.get("/staking-stats", response_model=dict[str, Any])
async def get_staking_statistics(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Get comprehensive staking statistics"""

    try:
        # Mock implementation - would query real staking data
        stats = {
            "total_staked_amount": 1000000.0,
            "active_stakers": 500,
            "active_developers_staked": 150,
            "average_apy": 7.5,
            "total_rewards_distributed": 50000.0,
            "staking_utilization": 65.0,
            "top_staked_developers": [
                {"address": "0x123...", "staked_amount": 50000.0, "apy": 12.5},
                {"address": "0x456...", "staked_amount": 35000.0, "apy": 10.0},
                {"address": "0x789...", "staked_amount": 25000.0, "apy": 8.5},
            ],
        }

        return stats

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting staking statistics")


# Platform Analytics Endpoints
@router.get("/analytics/overview", response_model=dict[str, Any])
async def get_platform_overview(
    session: Session = Depends(get_session), dev_service: DeveloperPlatformService = Depends(get_developer_platform_service)
) -> dict[str, Any]:
    """Get platform overview analytics"""

    try:
        # Get bounty statistics
        bounty_stats = await dev_service.get_bounty_statistics()

        # Get developer statistics
        total_developers = session.execute(select(DeveloperProfile)).count()
        active_developers = session.execute(select(DeveloperProfile).where(DeveloperProfile.is_active)).count()

        # Get certification statistics
        total_certifications = session.execute(select(DeveloperCertification)).count()

        # Get regional hub statistics
        total_hubs = session.execute(select(RegionalHub)).count()

        return {
            "developers": {
                "total": total_developers,
                "active": active_developers,
                "new_this_month": 25,  # Mock data
                "average_reputation": 45.5,
            },
            "bounties": bounty_stats,
            "certifications": {
                "total_granted": total_certifications,
                "new_this_month": 15,  # Mock data
                "most_common_level": "intermediate",
            },
            "regional_hubs": {
                "total": total_hubs,
                "active": total_hubs,  # Mock: all hubs are active
                "regions_covered": 12,  # Mock data
            },
            "staking": {"total_staked": 1000000.0, "active_stakers": 500, "average_apy": 7.5},  # Mock data
            "generated_at": datetime.now(datetime.UTC).isoformat(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting platform overview")


@router.get("/health", response_model=dict[str, Any])
async def get_platform_health(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Get developer platform health status"""

    try:
        # Check database connectivity
        try:
            developer_count = session.execute(select(func.count(DeveloperProfile.id))).scalar()
            database_status = "healthy"
        except Exception:
            database_status = "unhealthy"
            developer_count = 0

        # Mock service health checks
        services_status = {
            "database": database_status,
            "blockchain": "healthy",  # Would check actual blockchain connectivity
            "ipfs": "healthy",  # Would check IPFS connectivity
            "smart_contracts": "healthy",  # Would check smart contract deployment
        }

        overall_status = "healthy" if all(status == "healthy" for status in services_status.values()) else "degraded"

        return {
            "status": overall_status,
            "services": services_status,
            "metrics": {
                "total_developers": developer_count,
                "active_bounties": 25,  # Mock data
                "pending_submissions": 8,  # Mock data
                "system_uptime": "99.9%",
            },
            "last_updated": datetime.now(datetime.UTC).isoformat(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting platform health")
