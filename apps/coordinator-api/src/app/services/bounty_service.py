"""
Bounty Management Service
Business logic for AI agent bounty system with ZK-proof verification
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from aitbc.aitbc_logging import get_logger

from ..contexts.bounty.domain.bounty import Bounty, BountyStats, BountyStatus, BountySubmission, BountyTier, SubmissionStatus

logger = get_logger(__name__)


class BountyService:
    """Service for managing AI agent bounties"""

    def __init__(self, session: Session | None = None) -> None:
        self.session: Session | None = session

    async def create_bounty(
        self,
        creator_id: str,
        title: str,
        description: str,
        reward_amount: float,
        tier: BountyTier,
        performance_criteria: dict[str, Any],
        min_accuracy: float,
        max_response_time: int | None,
        deadline: datetime,
        max_submissions: int,
        requires_zk_proof: bool,
        auto_verify_threshold: float,
        tags: list[str],
        category: str | None,
        difficulty: str | None,
    ) -> Bounty:
        """Create a new bounty"""
        try:
            creation_fee = reward_amount * 0.005
            success_fee = reward_amount * 0.02
            platform_fee = reward_amount * 0.01
            bounty = Bounty(
                title=title,
                description=description,
                reward_amount=reward_amount,
                creator_id=creator_id,
                tier=tier,
                performance_criteria=performance_criteria,
                min_accuracy=min_accuracy,
                max_response_time=max_response_time,
                deadline=deadline,
                max_submissions=max_submissions,
                requires_zk_proof=requires_zk_proof,
                auto_verify_threshold=auto_verify_threshold,
                tags=tags,
                category=category,
                difficulty=difficulty,
                creation_fee=creation_fee,
                success_fee=success_fee,
                platform_fee=platform_fee,
            )
            self.session.add(bounty)  # type: ignore[union-attr]
            self.session.commit()  # type: ignore[union-attr]
            self.session.refresh(bounty)  # type: ignore[union-attr]
            logger.info("Created bounty %s: %s", bounty.bounty_id, title)
            return bounty
        except Exception as e:
            logger.error("Failed to create bounty: %s", e)
            self.session.rollback()  # type: ignore[union-attr]
            raise

    async def get_bounty(self, bounty_id: str) -> Bounty | None:
        """Get bounty by ID"""
        try:
            stmt = select(Bounty).where(Bounty.bounty_id == bounty_id)  # type: ignore[arg-type]
            result = self.session.execute(stmt).scalar_one_or_none()  # type: ignore[union-attr]
            return result
        except Exception as e:
            logger.error("Failed to get bounty %s: %s", bounty_id, e)
            raise

    async def get_bounties(
        self,
        status: BountyStatus | None = None,
        tier: BountyTier | None = None,
        creator_id: str | None = None,
        category: str | None = None,
        min_reward: float | None = None,
        max_reward: float | None = None,
        deadline_before: datetime | None = None,
        deadline_after: datetime | None = None,
        tags: list[str] | None = None,
        requires_zk_proof: bool | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> list[Bounty]:
        """Get filtered list of bounties"""
        try:
            query = select(Bounty)
            if status:
                query = query.where(Bounty.status == status)  # type: ignore[arg-type]
            if tier:
                query = query.where(Bounty.tier == tier)  # type: ignore[arg-type]
            if creator_id:
                query = query.where(Bounty.creator_id == creator_id)  # type: ignore[arg-type]
            if category:
                query = query.where(Bounty.category == category)  # type: ignore[arg-type]
            if min_reward:
                query = query.where(Bounty.reward_amount >= min_reward)  # type: ignore[arg-type]
            if max_reward:
                query = query.where(Bounty.reward_amount <= max_reward)  # type: ignore[arg-type]
            if deadline_before:
                query = query.where(Bounty.deadline <= deadline_before)  # type: ignore[arg-type]
            if deadline_after:
                query = query.where(Bounty.deadline >= deadline_after)  # type: ignore[arg-type]
            if requires_zk_proof is not None:
                query = query.where(Bounty.requires_zk_proof == requires_zk_proof)  # type: ignore[arg-type]
            if tags:
                for tag in tags:
                    query = query.where(Bounty.tags.contains([tag]))  # type: ignore[attr-defined]
            query = query.order_by(Bounty.creation_time.desc())  # type: ignore[attr-defined]
            offset = (page - 1) * limit
            query = query.offset(offset).limit(limit)
            result = self.session.execute(query).scalars().all()  # type: ignore[union-attr]
            return list(result)
        except Exception as e:
            logger.error("Failed to get bounties: %s", e)
            raise

    async def create_submission(
        self,
        bounty_id: str,
        submitter_address: str,
        zk_proof: dict[str, Any] | None,
        performance_hash: str,
        accuracy: float,
        response_time: int | None,
        compute_power: float | None,
        energy_efficiency: float | None,
        submission_data: dict[str, Any],
        test_results: dict[str, Any],
    ) -> BountySubmission:
        """Create a bounty submission"""
        try:
            bounty = await self.get_bounty(bounty_id)
            if not bounty:
                raise ValueError("Bounty not found")
            if bounty.status != BountyStatus.ACTIVE:
                raise ValueError("Bounty is not active")
            if datetime.now(UTC) > bounty.deadline:
                raise ValueError("Bounty deadline has passed")
            if bounty.submission_count >= bounty.max_submissions:
                raise ValueError("Maximum submissions reached")
            existing_stmt = select(BountySubmission).where(
                and_(BountySubmission.bounty_id == bounty_id, BountySubmission.submitter_address == submitter_address)
            )  # type: ignore[arg-type]
            existing = self.session.execute(existing_stmt).scalar_one_or_none()  # type: ignore[union-attr]
            if existing:
                raise ValueError("Already submitted to this bounty")
            submission = BountySubmission(
                bounty_id=bounty_id,
                submitter_address=submitter_address,
                accuracy=accuracy,
                response_time=response_time,
                compute_power=compute_power,
                energy_efficiency=energy_efficiency,
                zk_proof=zk_proof or {},
                performance_hash=performance_hash,
                submission_data=submission_data,
                test_results=test_results,
            )
            self.session.add(submission)  # type: ignore[union-attr]
            bounty.submission_count += 1
            self.session.commit()  # type: ignore[union-attr]
            self.session.refresh(submission)  # type: ignore[union-attr]
            logger.info("Created submission %s for bounty %s", submission.submission_id, bounty_id)
            return submission
        except Exception as e:
            logger.error("Failed to create submission: %s", e)
            self.session.rollback()  # type: ignore[union-attr]
            raise

    async def get_bounty_submissions(self, bounty_id: str) -> list[BountySubmission]:
        """Get all submissions for a bounty"""
        try:
            stmt = (
                select(BountySubmission)
                .where(BountySubmission.bounty_id == bounty_id)
                .order_by(BountySubmission.submission_time.desc())
            )  # type: ignore[attr-defined, arg-type]
            result = self.session.execute(stmt).scalars().all()  # type: ignore[union-attr]
            return list(result)
        except Exception as e:
            logger.error("Failed to get bounty submissions: %s", e)
            raise

    async def verify_submission(
        self, bounty_id: str, submission_id: str, verified: bool, verifier_address: str, verification_notes: str | None = None
    ) -> BountySubmission:
        """Verify a bounty submission"""
        try:
            stmt = select(BountySubmission).where(
                and_(BountySubmission.submission_id == submission_id, BountySubmission.bounty_id == bounty_id)
            )  # type: ignore[arg-type]
            submission = self.session.execute(stmt).scalar_one_or_none()  # type: ignore[union-attr]
            if not submission:
                raise ValueError("Submission not found")
            if submission.status != SubmissionStatus.PENDING:
                raise ValueError("Submission already processed")
            submission.status = SubmissionStatus.VERIFIED if verified else SubmissionStatus.REJECTED
            submission.verification_time = datetime.now(UTC)
            submission.verifier_address = verifier_address
            if verified:
                bounty = await self.get_bounty(bounty_id)
                if submission.accuracy >= bounty.min_accuracy:  # type: ignore[union-attr]
                    bounty.status = BountyStatus.COMPLETED  # type: ignore[union-attr]
                    bounty.winning_submission_id = submission.submission_id  # type: ignore[union-attr]
                    bounty.winner_address = submission.submitter_address  # type: ignore[union-attr]
                    logger.info("Bounty %s completed by %s", bounty_id, submission.submitter_address)
            self.session.commit()  # type: ignore[union-attr]
            self.session.refresh(submission)  # type: ignore[union-attr]
            return submission
        except Exception as e:
            logger.error("Failed to verify submission: %s", e)
            self.session.rollback()  # type: ignore[union-attr]
            raise

    async def create_dispute(
        self, bounty_id: str, submission_id: str, disputer_address: str, dispute_reason: str
    ) -> BountySubmission:
        """Create a dispute for a submission"""
        try:
            stmt = select(BountySubmission).where(
                and_(BountySubmission.submission_id == submission_id, BountySubmission.bounty_id == bounty_id)
            )  # type: ignore[arg-type]
            submission = self.session.execute(stmt).scalar_one_or_none()  # type: ignore[union-attr]
            if not submission:
                raise ValueError("Submission not found")
            if submission.status != SubmissionStatus.VERIFIED:
                raise ValueError("Can only dispute verified submissions")
            if datetime.now(UTC) - submission.verification_time > timedelta(days=1):  # type: ignore[operator]
                raise ValueError("Dispute window expired")
            submission.status = SubmissionStatus.DISPUTED
            submission.dispute_reason = dispute_reason
            submission.dispute_time = datetime.now(UTC)
            bounty = await self.get_bounty(bounty_id)
            bounty.status = BountyStatus.DISPUTED  # type: ignore[union-attr]
            self.session.commit()  # type: ignore[union-attr]
            self.session.refresh(submission)  # type: ignore[union-attr]
            logger.info("Created dispute for submission %s", submission_id)
            return submission
        except Exception as e:
            logger.error("Failed to create dispute: %s", e)
            self.session.rollback()  # type: ignore[union-attr]
            raise

    async def get_user_created_bounties(
        self, user_address: str, status: BountyStatus | None = None, page: int = 1, limit: int = 20
    ) -> list[Bounty]:
        """Get bounties created by a user"""
        try:
            query = select(Bounty).where(Bounty.creator_id == user_address)  # type: ignore[arg-type]
            if status:
                query = query.where(Bounty.status == status)  # type: ignore[arg-type]
            query = query.order_by(Bounty.creation_time.desc())  # type: ignore[attr-defined]
            offset = (page - 1) * limit
            query = query.offset(offset).limit(limit)
            result = self.session.execute(query).scalars().all()  # type: ignore[union-attr]
            return list(result)
        except Exception as e:
            logger.error("Failed to get user created bounties: %s", e)
            raise

    async def get_user_submissions(
        self, user_address: str, status: SubmissionStatus | None = None, page: int = 1, limit: int = 20
    ) -> list[BountySubmission]:
        """Get submissions made by a user"""
        try:
            query = select(BountySubmission).where(BountySubmission.submitter_address == user_address)  # type: ignore[arg-type]
            if status:
                query = query.where(BountySubmission.status == status)  # type: ignore[arg-type]
            query = query.order_by(BountySubmission.submission_time.desc())  # type: ignore[attr-defined]
            offset = (page - 1) * limit
            query = query.offset(offset).limit(limit)
            result = self.session.execute(query).scalars().all()  # type: ignore[union-attr]
            return list(result)
        except Exception as e:
            logger.error("Failed to get user submissions: %s", e)
            raise

    async def get_leaderboard(self, period: str = "weekly", limit: int = 50) -> list[dict[str, Any]]:
        """Get bounty leaderboard"""
        try:
            if period == "daily":
                start_date = datetime.now(UTC) - timedelta(days=1)
            elif period == "weekly":
                start_date = datetime.now(UTC) - timedelta(weeks=1)
            elif period == "monthly":
                start_date = datetime.now(UTC) - timedelta(days=30)
            else:
                start_date = datetime.now(UTC) - timedelta(weeks=1)
            stmt = (
                select(
                    BountySubmission.submitter_address,
                    func.count(BountySubmission.submission_id).label("submissions"),
                    func.avg(BountySubmission.accuracy).label("avg_accuracy"),
                    func.sum(Bounty.reward_amount).label("total_rewards"),
                )
                .join(Bounty)
                .where(
                    and_(BountySubmission.status == SubmissionStatus.VERIFIED, BountySubmission.submission_time >= start_date)
                )
                .group_by(BountySubmission.submitter_address)
                .order_by(func.sum(Bounty.reward_amount).desc())
                .limit(limit)
            )  # type: ignore[arg-type,call-overload]
            result = self.session.execute(stmt).all()  # type: ignore[union-attr]
            leaderboard: list[dict[str, Any]] = []
            for row in result:
                leaderboard.append(
                    {
                        "address": row.submitter_address,
                        "submissions": row.submissions,
                        "avg_accuracy": float(row.avg_accuracy),
                        "total_rewards": float(row.total_rewards),
                        "rank": len(leaderboard) + 1,
                    }
                )
            return leaderboard
        except Exception as e:
            logger.error("Failed to get leaderboard: %s", e)
            raise

    async def get_bounty_stats(self, period: str = "monthly") -> BountyStats:
        """Get bounty statistics"""
        try:
            if period == "daily":
                start_date = datetime.now(UTC) - timedelta(days=1)
            elif period == "weekly":
                start_date = datetime.now(UTC) - timedelta(weeks=1)
            elif period == "monthly":
                start_date = datetime.now(UTC) - timedelta(days=30)
            else:
                start_date = datetime.now(UTC) - timedelta(days=30)
            total_stmt = select(func.count(Bounty.bounty_id)).where(Bounty.creation_time >= start_date)  # type: ignore[arg-type]
            total_bounties = self.session.execute(total_stmt).scalar() or 0  # type: ignore[union-attr]
            active_stmt = select(func.count(Bounty.bounty_id)).where(
                and_(Bounty.creation_time >= start_date, Bounty.status == BountyStatus.ACTIVE)
            )  # type: ignore[arg-type]
            active_bounties = self.session.execute(active_stmt).scalar() or 0  # type: ignore[union-attr]
            completed_stmt = select(func.count(Bounty.bounty_id)).where(
                and_(Bounty.creation_time >= start_date, Bounty.status == BountyStatus.COMPLETED)
            )  # type: ignore[arg-type]
            completed_bounties = self.session.execute(completed_stmt).scalar() or 0  # type: ignore[union-attr]
            total_locked_stmt = select(func.sum(Bounty.reward_amount)).where(Bounty.creation_time >= start_date)  # type: ignore[arg-type]
            total_value_locked = self.session.execute(total_locked_stmt).scalar() or 0.0  # type: ignore[union-attr]
            total_rewards_stmt = select(func.sum(Bounty.reward_amount)).where(
                and_(Bounty.creation_time >= start_date, Bounty.status == BountyStatus.COMPLETED)
            )  # type: ignore[arg-type]
            total_rewards_paid = self.session.execute(total_rewards_stmt).scalar() or 0.0  # type: ignore[union-attr]
            success_rate = completed_bounties / total_bounties * 100 if total_bounties > 0 else 0.0
            avg_reward = total_value_locked / total_bounties if total_bounties > 0 else 0.0
            tier_stmt = (
                select(Bounty.tier, func.count(Bounty.bounty_id).label("count"))
                .where(Bounty.creation_time >= start_date)
                .group_by(Bounty.tier)
            )  # type: ignore[arg-type, call-overload]
            tier_result = self.session.execute(tier_stmt).all()  # type: ignore[union-attr]
            tier_distribution = {row.tier.value: row.count for row in tier_result}
            expired_stmt = select(func.count(Bounty.bounty_id)).where(
                and_(Bounty.creation_time >= start_date, Bounty.status == BountyStatus.EXPIRED)
            )  # type: ignore[arg-type]
            expired_bounties = self.session.execute(expired_stmt).scalar() or 0  # type: ignore[union-attr]
            disputed_stmt = select(func.count(Bounty.bounty_id)).where(
                and_(Bounty.creation_time >= start_date, Bounty.status == BountyStatus.DISPUTED)
            )  # type: ignore[arg-type]
            disputed_bounties = self.session.execute(disputed_stmt).scalar() or 0  # type: ignore[union-attr]
            fees_stmt = select(func.sum(Bounty.platform_fee + Bounty.creation_fee)).where(Bounty.creation_time >= start_date)  # type: ignore[arg-type]
            total_fees_collected = self.session.execute(fees_stmt).scalar() or 0.0  # type: ignore[union-attr]
            stats = BountyStats(
                period_start=start_date,
                period_end=datetime.now(UTC),
                period_type=period,
                total_bounties=total_bounties,
                active_bounties=active_bounties,
                completed_bounties=completed_bounties,
                expired_bounties=expired_bounties,
                disputed_bounties=disputed_bounties,
                total_value_locked=total_value_locked,
                total_rewards_paid=total_rewards_paid,
                total_fees_collected=total_fees_collected,
                average_reward=avg_reward,
                success_rate=success_rate,
                tier_distribution=tier_distribution,
            )
            return stats
        except Exception as e:
            logger.error("Failed to get bounty stats: %s", e)
            raise

    async def get_categories(self) -> list[str]:
        """Get all bounty categories"""
        try:
            stmt = select(Bounty.category).where(and_(Bounty.category.isnot(None), Bounty.category != "")).distinct()  # type: ignore[arg-type, call-overload, union-attr]
            result = self.session.execute(stmt).scalars().all()  # type: ignore[union-attr]
            return list(result)
        except Exception as e:
            logger.error("Failed to get categories: %s", e)
            raise

    async def get_popular_tags(self, limit: int = 100) -> list[str]:
        """Get popular bounty tags"""
        try:
            stmt = select(Bounty.tags).where(func.array_length(Bounty.tags, 1) > 0).limit(limit)  # type: ignore[call-overload]
            result = self.session.execute(stmt).scalars().all()  # type: ignore[union-attr]
            all_tags = []
            for tags in result:
                all_tags.extend(tags)
            return list(set(all_tags))[:limit]
        except Exception as e:
            logger.error("Failed to get popular tags: %s", e)
            raise

    async def search_bounties(self, query: str, page: int = 1, limit: int = 20) -> list[Bounty]:
        """Search bounties by text"""
        try:
            search_pattern = f"%{query}%"
            stmt = (
                select(Bounty)
                .where(or_(Bounty.title.ilike(search_pattern), Bounty.description.ilike(search_pattern)))
                .order_by(Bounty.creation_time.desc())
            )  # type: ignore[attr-defined]
            offset = (page - 1) * limit
            stmt = stmt.offset(offset).limit(limit)
            result = self.session.execute(stmt).scalars().all()  # type: ignore[union-attr]
            return list(result)
        except Exception as e:
            logger.error("Failed to search bounties: %s", e)
            raise

    async def expire_bounty(self, bounty_id: str) -> Bounty:
        """Expire a bounty"""
        try:
            bounty = await self.get_bounty(bounty_id)
            if not bounty:
                raise ValueError("Bounty not found")
            if bounty.status != BountyStatus.ACTIVE:
                raise ValueError("Bounty is not active")
            if datetime.now(UTC) <= bounty.deadline:
                raise ValueError("Deadline has not passed")
            bounty.status = BountyStatus.EXPIRED
            self.session.commit()  # type: ignore[union-attr]
            self.session.refresh(bounty)  # type: ignore[union-attr]
            logger.info("Expired bounty %s", bounty_id)
            return bounty
        except Exception as e:
            logger.error("Failed to expire bounty: %s", e)
            self.session.rollback()  # type: ignore[union-attr]
            raise
