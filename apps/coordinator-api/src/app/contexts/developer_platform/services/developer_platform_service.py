"""
Developer Platform Service

Service for managing the developer ecosystem, bounties, certifications, and regional hubs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from fastapi import HTTPException
from sqlalchemy import desc
from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger

from ...blockchain.services.blockchain import get_balance, mint_tokens
from ..domain.developer_platform import (
    BountyStatus,
    BountySubmission,
    BountyTask,
    CertificationLevel,
    DeveloperCertification,
    DeveloperProfile,
    RegionalHub,
)
from ..schemas.developer_platform import (
    BountyCreate,
    BountySubmissionCreate,
    CertificationGrant,
    DeveloperCreate,
)

logger = get_logger(__name__)


class DeveloperPlatformService:
    def __init__(self, session: Session) -> None:
        self.session = session

    async def register_developer(self, request: DeveloperCreate) -> DeveloperProfile:
        existing = self.session.execute(
            select(DeveloperProfile).where(DeveloperProfile.wallet_address == request.wallet_address)
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Developer profile already exists for this wallet")
        profile = DeveloperProfile(
            wallet_address=request.wallet_address,
            github_handle=request.github_handle,
            email=request.email,
            skills=request.skills,
        )
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        logger.info("Registered new developer: %s", profile.wallet_address)
        return profile

    async def grant_certification(self, request: CertificationGrant) -> DeveloperCertification:
        profile = self.session.get(DeveloperProfile, request.developer_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Developer profile not found")
        cert = DeveloperCertification(
            developer_id=request.developer_id,
            certification_name=request.certification_name,
            level=request.level,
            issued_by=request.issued_by,
            ipfs_credential_cid=request.ipfs_credential_cid,
        )
        reputation_boost = {
            CertificationLevel.BEGINNER: 10.0,
            CertificationLevel.INTERMEDIATE: 25.0,
            CertificationLevel.ADVANCED: 50.0,
            CertificationLevel.EXPERT: 100.0,
        }.get(request.level, 0.0)
        profile.reputation_score += reputation_boost
        self.session.add(cert)
        self.session.commit()
        self.session.refresh(cert)
        logger.info("Granted %s certification to developer %s", request.certification_name, profile.wallet_address)
        return cert

    async def create_bounty(self, request: BountyCreate) -> BountyTask:
        bounty = BountyTask(
            title=request.title,
            description=request.description,
            required_skills=request.required_skills,
            difficulty_level=request.difficulty_level,
            reward_amount=request.reward_amount,
            creator_address=request.creator_address,
            deadline=request.deadline,
        )
        self.session.add(bounty)
        self.session.commit()
        self.session.refresh(bounty)
        logger.info("Created bounty task: %s", bounty.title)
        return bounty

    async def submit_bounty(self, bounty_id: str, request: BountySubmissionCreate) -> BountySubmission:
        bounty = self.session.get(BountyTask, bounty_id)
        if not bounty:
            raise HTTPException(status_code=404, detail="Bounty not found")
        if bounty.status != BountyStatus.OPEN and bounty.status != BountyStatus.IN_PROGRESS:
            raise HTTPException(status_code=400, detail="Bounty is not open for submissions")
        developer = self.session.get(DeveloperProfile, request.developer_id)
        if not developer:
            raise HTTPException(status_code=404, detail="Developer not found")
        has_skills = any(skill in developer.skills for skill in bounty.required_skills)
        if not has_skills and bounty.required_skills:
            logger.warning("Developer %s submitted for bounty without required skills", developer.wallet_address)
        submission = BountySubmission(
            bounty_id=bounty_id,
            developer_id=request.developer_id,
            github_pr_url=request.github_pr_url,
            submission_notes=request.submission_notes,
        )
        bounty.status = BountyStatus.IN_REVIEW
        self.session.add(submission)
        self.session.commit()
        self.session.refresh(submission)
        logger.info("Submission received for bounty %s from developer %s", bounty_id, request.developer_id)
        return submission

    async def approve_submission(self, submission_id: str, reviewer_address: str, review_notes: str) -> BountySubmission:
        """Approve a submission and trigger reward payout"""
        submission = self.session.get(BountySubmission, submission_id)
        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")
        if submission.is_approved:
            raise HTTPException(status_code=400, detail="Submission is already approved")
        bounty = submission.bounty  # type: ignore[attr-defined]
        developer = submission.developer  # type: ignore[attr-defined]
        submission.is_approved = True
        submission.review_notes = review_notes
        submission.reviewer_address = reviewer_address
        submission.reviewed_at = datetime.now(UTC)
        bounty.status = BountyStatus.COMPLETED
        bounty.assigned_developer_id = developer.id
        tx_hash = "0x" + "mock_tx_hash_" + submission_id[:10]
        submission.tx_hash_reward = tx_hash
        developer.total_earned_aitbc += bounty.reward_amount
        developer.reputation_score += 5.0
        self.session.commit()
        self.session.refresh(submission)
        logger.info("Approved submission %s, paid %s to %s", submission_id, bounty.reward_amount, developer.wallet_address)
        return submission

    async def get_developer_profile(self, wallet_address: str) -> DeveloperProfile | None:
        """Get developer profile by wallet address"""
        return self.session.execute(select(DeveloperProfile).where(DeveloperProfile.wallet_address == wallet_address)).first()  # type: ignore[return-value]

    async def update_developer_profile(self, wallet_address: str, updates: dict) -> DeveloperProfile:
        """Update developer profile"""
        profile = await self.get_developer_profile(wallet_address)
        if not profile:
            raise HTTPException(status_code=404, detail="Developer profile not found")
        for key, value in updates.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        profile.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(profile)
        return profile

    async def get_leaderboard(self, limit: int = 100, offset: int = 0) -> list[DeveloperProfile]:
        """Get developer leaderboard sorted by reputation score"""
        return cast(
            list[DeveloperProfile],
            self.session.execute(
                select(DeveloperProfile)
                .where(DeveloperProfile.is_active)
                .order_by(desc(DeveloperProfile.reputation_score))  # type: ignore[arg-type]
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all(),
        )

    async def get_developer_stats(self, wallet_address: str) -> dict:
        """Get comprehensive developer statistics"""
        profile = await self.get_developer_profile(wallet_address)
        if not profile:
            raise HTTPException(status_code=404, detail="Developer profile not found")
        completed_bounties = self.session.execute(
            select(BountySubmission).where(BountySubmission.developer_id == profile.id, BountySubmission.is_approved)
        ).all()
        certifications = self.session.execute(
            select(DeveloperCertification).where(DeveloperCertification.developer_id == profile.id)
        ).all()
        return {
            "wallet_address": profile.wallet_address,
            "reputation_score": profile.reputation_score,
            "total_earned_aitbc": profile.total_earned_aitbc,
            "completed_bounties": len(completed_bounties),
            "certifications_count": len(certifications),
            "skills": profile.skills,
            "github_handle": profile.github_handle,
            "joined_at": profile.created_at.isoformat(),
            "last_updated": profile.updated_at.isoformat(),
        }

    async def list_bounties(self, status: BountyStatus | None = None, limit: int = 100, offset: int = 0) -> list[BountyTask]:
        """List bounty tasks with optional status filter"""
        query = select(BountyTask)
        if status:
            query = query.where(BountyTask.status == status)
        return self.session.execute(query.order_by(desc(BountyTask.created_at)).offset(offset).limit(limit)).all()  # type: ignore[arg-type, return-value]

    async def get_bounty_details(self, bounty_id: str) -> BountyTask | None:
        """Get detailed bounty information"""
        bounty = self.session.get(BountyTask, bounty_id)
        if not bounty:
            raise HTTPException(status_code=404, detail="Bounty not found")
        submissions_count = self.session.execute(
            select(BountySubmission).where(BountySubmission.bounty_id == bounty_id)
        ).count()  # type: ignore[attr-defined]
        return {**bounty.__dict__, "submissions_count": submissions_count}  # type: ignore[return-value]

    async def get_my_submissions(self, developer_id: str) -> list[BountySubmission]:
        """Get all submissions by a developer"""
        return cast(
            list[BountySubmission],
            self.session.execute(
                select(BountySubmission)
                .where(BountySubmission.developer_id == developer_id)
                .order_by(desc(BountySubmission.submitted_at))  # type: ignore[arg-type]
            )
            .scalars()
            .all(),
        )

    async def create_regional_hub(self, name: str, region: str, description: str, manager_address: str) -> RegionalHub:
        """Create a regional developer hub"""
        hub = RegionalHub(name=name, region=region, description=description, manager_address=manager_address)
        self.session.add(hub)
        self.session.commit()
        self.session.refresh(hub)
        logger.info("Created regional hub: %s in %s", hub.name, hub.region)  # type: ignore[attr-defined]
        return hub

    async def get_regional_hubs(self) -> list[RegionalHub]:
        """Get all regional developer hubs"""
        return self.session.execute(select(RegionalHub).where(RegionalHub.is_active)).all()  # type: ignore[attr-defined, return-value]

    async def get_hub_developers(self, hub_id: str) -> list[DeveloperProfile]:
        """Get developers in a regional hub"""
        hub = self.session.get(RegionalHub, hub_id)
        if not hub:
            raise HTTPException(status_code=404, detail="Regional hub not found")
        return self.session.execute(select(DeveloperProfile).where(DeveloperProfile.is_active)).all()  # type: ignore[return-value]

    async def stake_on_developer(self, staker_address: str, developer_address: str, amount: float) -> dict:
        """Stake AITBC tokens on a developer"""
        balance = get_balance(staker_address)
        if balance < amount:  # type: ignore[operator]
            raise HTTPException(status_code=400, detail="Insufficient balance for staking")
        developer = await self.get_developer_profile(developer_address)
        if not developer:
            raise HTTPException(status_code=404, detail="Developer not found")
        staking_info = {
            "staker_address": staker_address,
            "developer_address": developer_address,
            "amount_staked": amount,
            "apy": 5.0 + developer.reputation_score / 100,
            "staking_id": f"stake_{staker_address[:8]}_{developer_address[:8]}",
            "created_at": datetime.now(UTC).isoformat(),
        }
        logger.info("Staked %s AITBC on developer %s by %s", amount, developer_address, staker_address)
        return staking_info

    async def get_staking_info(self, address: str) -> dict:
        """Get staking information for an address (both as staker and developer)"""
        return {
            "address": address,
            "total_staked_as_staker": 1000.0,
            "total_staked_on_me": 5000.0,
            "active_stakes": 5,
            "total_rewards_earned": 125.5,
            "apy_average": 7.5,
        }

    async def unstake_tokens(self, staking_id: str, amount: float) -> dict:
        """Unstake tokens from a developer"""
        unstake_info = {
            "staking_id": staking_id,
            "amount_unstaked": amount,
            "rewards_earned": 25.5,
            "tx_hash": "0xmock_unstake_tx_hash",
            "completed_at": datetime.now(UTC).isoformat(),
        }
        logger.info("Unstaked %s AITBC from staking position %s", amount, staking_id)
        return unstake_info

    async def get_rewards(self, address: str) -> dict:
        """Get reward information for an address"""
        return {
            "address": address,
            "pending_rewards": 45.75,
            "claimed_rewards": 250.25,
            "last_claim_time": (datetime.now(UTC) - timedelta(days=7)).isoformat(),
            "next_claim_time": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        }

    async def claim_rewards(self, address: str) -> dict:
        """Claim pending rewards"""
        rewards = await self.get_rewards(address)
        if rewards["pending_rewards"] <= 0:
            raise HTTPException(status_code=400, detail="No pending rewards to claim")
        try:
            await mint_tokens(address, rewards["pending_rewards"])
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to mint rewards: {str(e)}") from e
        claim_info = {
            "address": address,
            "amount_claimed": rewards["pending_rewards"],
            "tx_hash": "0xmock_claim_tx_hash",
            "claimed_at": datetime.now(UTC).isoformat(),
        }
        logger.info("Claimed %s AITBC rewards for %s", rewards["pending_rewards"], address)
        return claim_info

    async def get_bounty_statistics(self) -> dict:
        """Get comprehensive bounty statistics"""
        total_bounties = self.session.execute(select(BountyTask)).count()  # type: ignore[attr-defined]
        open_bounties = self.session.execute(select(BountyTask).where(BountyTask.status == BountyStatus.OPEN)).count()  # type: ignore[attr-defined]
        completed_bounties = self.session.execute(
            select(BountyTask).where(BountyTask.status == BountyStatus.COMPLETED)
        ).count()  # type: ignore[attr-defined]
        total_rewards = self.session.execute(select(BountyTask).where(BountyTask.status == BountyStatus.COMPLETED)).all()
        total_reward_amount = sum(bounty.reward_amount for bounty in total_rewards)
        return {
            "total_bounties": total_bounties,
            "open_bounties": open_bounties,
            "completed_bounties": completed_bounties,
            "total_rewards_distributed": total_reward_amount,
            "average_reward_per_bounty": total_reward_amount / max(completed_bounties, 1),
            "completion_rate": completed_bounties / max(total_bounties, 1) * 100,
        }
