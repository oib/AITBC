"""
Developer Platform Service

Service for managing the developer ecosystem, bounties, certifications, and regional hubs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlmodel import Session, select
from fastapi import HTTPException

from ..domain.developer_platform import (
    DeveloperProfile, DeveloperCertification, RegionalHub, 
    BountyTask, BountySubmission, BountyStatus, CertificationLevel
)
from ..schemas.developer_platform import (
    DeveloperCreate, BountyCreate, BountySubmissionCreate, CertificationGrant
)
from ..services.blockchain import mint_tokens, get_balance

logger = logging.getLogger(__name__)

class DeveloperPlatformService:
    def __init__(
        self,
        session: Session
    ):
        self.session = session

    async def register_developer(self, request: DeveloperCreate) -> DeveloperProfile:
        existing = self.session.exec(
            select(DeveloperProfile).where(DeveloperProfile.wallet_address == request.wallet_address)
        ).first()
        
        if existing:
            raise HTTPException(status_code=400, detail="Developer profile already exists for this wallet")
            
        profile = DeveloperProfile(
            wallet_address=request.wallet_address,
            github_handle=request.github_handle,
            email=request.email,
            skills=request.skills
        )
        
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        
        logger.info(f"Registered new developer: {profile.wallet_address}")
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
            ipfs_credential_cid=request.ipfs_credential_cid
        )
        
        # Boost reputation based on certification level
        reputation_boost = {
            CertificationLevel.BEGINNER: 10.0,
            CertificationLevel.INTERMEDIATE: 25.0,
            CertificationLevel.ADVANCED: 50.0,
            CertificationLevel.EXPERT: 100.0
        }.get(request.level, 0.0)
        
        profile.reputation_score += reputation_boost
        
        self.session.add(cert)
        self.session.commit()
        self.session.refresh(cert)
        
        logger.info(f"Granted {request.certification_name} certification to developer {profile.wallet_address}")
        return cert

    async def create_bounty(self, request: BountyCreate) -> BountyTask:
        bounty = BountyTask(
            title=request.title,
            description=request.description,
            required_skills=request.required_skills,
            difficulty_level=request.difficulty_level,
            reward_amount=request.reward_amount,
            creator_address=request.creator_address,
            deadline=request.deadline
        )
        
        self.session.add(bounty)
        self.session.commit()
        self.session.refresh(bounty)
        
        # In a real system, this would interact with a smart contract to lock the reward funds
        logger.info(f"Created bounty task: {bounty.title}")
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

        # Basic skill check (optional enforcement)
        has_skills = any(skill in developer.skills for skill in bounty.required_skills)
        if not has_skills and bounty.required_skills:
            logger.warning(f"Developer {developer.wallet_address} submitted for bounty without required skills")

        submission = BountySubmission(
            bounty_id=bounty_id,
            developer_id=request.developer_id,
            github_pr_url=request.github_pr_url,
            submission_notes=request.submission_notes
        )
        
        bounty.status = BountyStatus.IN_REVIEW
        
        self.session.add(submission)
        self.session.commit()
        self.session.refresh(submission)
        
        logger.info(f"Submission received for bounty {bounty_id} from developer {request.developer_id}")
        return submission

    async def approve_submission(self, submission_id: str, reviewer_address: str, review_notes: str) -> BountySubmission:
        """Approve a submission and trigger reward payout"""
        submission = self.session.get(BountySubmission, submission_id)
        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")
            
        if submission.is_approved:
            raise HTTPException(status_code=400, detail="Submission is already approved")
            
        bounty = submission.bounty
        developer = submission.developer
        
        submission.is_approved = True
        submission.review_notes = review_notes
        submission.reviewer_address = reviewer_address
        submission.reviewed_at = datetime.utcnow()
        
        bounty.status = BountyStatus.COMPLETED
        bounty.assigned_developer_id = developer.id
        
        # Trigger reward payout
        # This would interface with the Multi-chain reward distribution protocol
        # tx_hash = await self.contract_service.distribute_bounty_reward(...)
        tx_hash = "0x" + "mock_tx_hash_" + submission_id[:10]
        submission.tx_hash_reward = tx_hash
        
        # Update developer stats
        developer.total_earned_aitbc += bounty.reward_amount
        developer.reputation_score += 5.0 # Base reputation bump for completing a bounty
        
        self.session.commit()
        self.session.refresh(submission)
        
        logger.info(f"Approved submission {submission_id}, paid {bounty.reward_amount} to {developer.wallet_address}")
        return submission

    async def get_developer_profile(self, wallet_address: str) -> Optional[DeveloperProfile]:
        """Get developer profile by wallet address"""
        return self.session.exec(
            select(DeveloperProfile).where(DeveloperProfile.wallet_address == wallet_address)
        ).first()

    async def update_developer_profile(self, wallet_address: str, updates: dict) -> DeveloperProfile:
        """Update developer profile"""
        profile = await self.get_developer_profile(wallet_address)
        if not profile:
            raise HTTPException(status_code=404, detail="Developer profile not found")
        
        for key, value in updates.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        
        profile.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(profile)
        
        return profile

    async def get_leaderboard(self, limit: int = 100, offset: int = 0) -> List[DeveloperProfile]:
        """Get developer leaderboard sorted by reputation score"""
        return self.session.exec(
            select(DeveloperProfile)
            .where(DeveloperProfile.is_active == True)
            .order_by(DeveloperProfile.reputation_score.desc())
            .offset(offset)
            .limit(limit)
        ).all()

    async def get_developer_stats(self, wallet_address: str) -> dict:
        """Get comprehensive developer statistics"""
        profile = await self.get_developer_profile(wallet_address)
        if not profile:
            raise HTTPException(status_code=404, detail="Developer profile not found")
        
        # Get bounty statistics
        completed_bounties = self.session.exec(
            select(BountySubmission).where(
                BountySubmission.developer_id == profile.id,
                BountySubmission.is_approved == True
            )
        ).all()
        
        # Get certification statistics
        certifications = self.session.exec(
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
            "last_updated": profile.updated_at.isoformat()
        }

    async def list_bounties(self, status: Optional[BountyStatus] = None, limit: int = 100, offset: int = 0) -> List[BountyTask]:
        """List bounty tasks with optional status filter"""
        query = select(BountyTask)
        if status:
            query = query.where(BountyTask.status == status)
        
        return self.session.exec(
            query.order_by(BountyTask.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()

    async def get_bounty_details(self, bounty_id: str) -> Optional[BountyTask]:
        """Get detailed bounty information"""
        bounty = self.session.get(BountyTask, bounty_id)
        if not bounty:
            raise HTTPException(status_code=404, detail="Bounty not found")
        
        # Get submissions count
        submissions_count = self.session.exec(
            select(BountySubmission).where(BountySubmission.bounty_id == bounty_id)
        ).count()
        
        return {
            **bounty.__dict__,
            "submissions_count": submissions_count
        }

    async def get_my_submissions(self, developer_id: str) -> List[BountySubmission]:
        """Get all submissions by a developer"""
        return self.session.exec(
            select(BountySubmission)
            .where(BountySubmission.developer_id == developer_id)
            .order_by(BountySubmission.submitted_at.desc())
        ).all()

    async def create_regional_hub(self, name: str, region: str, description: str, manager_address: str) -> RegionalHub:
        """Create a regional developer hub"""
        hub = RegionalHub(
            name=name,
            region=region,
            description=description,
            manager_address=manager_address
        )
        
        self.session.add(hub)
        self.session.commit()
        self.session.refresh(hub)
        
        logger.info(f"Created regional hub: {hub.name} in {hub.region}")
        return hub

    async def get_regional_hubs(self) -> List[RegionalHub]:
        """Get all regional developer hubs"""
        return self.session.exec(
            select(RegionalHub).where(RegionalHub.is_active == True)
        ).all()

    async def get_hub_developers(self, hub_id: str) -> List[DeveloperProfile]:
        """Get developers in a regional hub"""
        # This would require a junction table in a real implementation
        # For now, return developers from the same region
        hub = self.session.get(RegionalHub, hub_id)
        if not hub:
            raise HTTPException(status_code=404, detail="Regional hub not found")
        
        # Mock implementation - in reality would use hub membership table
        return self.session.exec(
            select(DeveloperProfile).where(DeveloperProfile.is_active == True)
        ).all()

    async def stake_on_developer(self, staker_address: str, developer_address: str, amount: float) -> dict:
        """Stake AITBC tokens on a developer"""
        # Check staker balance
        balance = get_balance(staker_address)
        if balance < amount:
            raise HTTPException(status_code=400, detail="Insufficient balance for staking")
        
        # Get developer profile
        developer = await self.get_developer_profile(developer_address)
        if not developer:
            raise HTTPException(status_code=404, detail="Developer not found")
        
        # In a real implementation, this would interact with staking smart contract
        # For now, return mock staking info
        staking_info = {
            "staker_address": staker_address,
            "developer_address": developer_address,
            "amount_staked": amount,
            "apy": 5.0 + (developer.reputation_score / 100), # Base APY + reputation bonus
            "staking_id": f"stake_{staker_address[:8]}_{developer_address[:8]}",
            "created_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Staked {amount} AITBC on developer {developer_address} by {staker_address}")
        return staking_info

    async def get_staking_info(self, address: str) -> dict:
        """Get staking information for an address (both as staker and developer)"""
        # Mock implementation - would query staking contracts/database
        return {
            "address": address,
            "total_staked_as_staker": 1000.0,
            "total_staked_on_me": 5000.0,
            "active_stakes": 5,
            "total_rewards_earned": 125.5,
            "apy_average": 7.5
        }

    async def unstake_tokens(self, staking_id: str, amount: float) -> dict:
        """Unstake tokens from a developer"""
        # Mock implementation - would interact with staking contract
        unstake_info = {
            "staking_id": staking_id,
            "amount_unstaked": amount,
            "rewards_earned": 25.5,
            "tx_hash": "0xmock_unstake_tx_hash",
            "completed_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Unstaked {amount} AITBC from staking position {staking_id}")
        return unstake_info

    async def get_rewards(self, address: str) -> dict:
        """Get reward information for an address"""
        # Mock implementation - would query reward contracts
        return {
            "address": address,
            "pending_rewards": 45.75,
            "claimed_rewards": 250.25,
            "last_claim_time": (datetime.utcnow() - timedelta(days=7)).isoformat(),
            "next_claim_time": (datetime.utcnow() + timedelta(days=1)).isoformat()
        }

    async def claim_rewards(self, address: str) -> dict:
        """Claim pending rewards"""
        # Mock implementation - would interact with reward contract
        rewards = await self.get_rewards(address)
        
        if rewards["pending_rewards"] <= 0:
            raise HTTPException(status_code=400, detail="No pending rewards to claim")
        
        # Mint rewards to address
        try:
            await mint_tokens(address, rewards["pending_rewards"])
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to mint rewards: {str(e)}")
        
        claim_info = {
            "address": address,
            "amount_claimed": rewards["pending_rewards"],
            "tx_hash": "0xmock_claim_tx_hash",
            "claimed_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Claimed {rewards['pending_rewards']} AITBC rewards for {address}")
        return claim_info

    async def get_bounty_statistics(self) -> dict:
        """Get comprehensive bounty statistics"""
        total_bounties = self.session.exec(select(BountyTask)).count()
        open_bounties = self.session.exec(
            select(BountyTask).where(BountyTask.status == BountyStatus.OPEN)
        ).count()
        completed_bounties = self.session.exec(
            select(BountyTask).where(BountyTask.status == BountyStatus.COMPLETED)
        ).count()
        
        total_rewards = self.session.exec(
            select(BountyTask).where(BountyTask.status == BountyStatus.COMPLETED)
        ).all()
        total_reward_amount = sum(bounty.reward_amount for bounty in total_rewards)
        
        return {
            "total_bounties": total_bounties,
            "open_bounties": open_bounties,
            "completed_bounties": completed_bounties,
            "total_rewards_distributed": total_reward_amount,
            "average_reward_per_bounty": total_reward_amount / max(completed_bounties, 1),
            "completion_rate": (completed_bounties / max(total_bounties, 1)) * 100
        }
