"""
Community and Developer Ecosystem Services
Services for managing OpenClaw developer tools, SDKs, and third-party solutions
"""

from datetime import datetime, UTC
from typing import Any

from aitbc import get_logger
from sqlmodel import Session, select

logger = get_logger(__name__)
from uuid import uuid4

from ..domain.community import (
    AgentSolution,
    CommunityPost,
    DeveloperProfile,
    DeveloperTier,
    Hackathon,
    InnovationLab,
    LabStatus,
    SolutionStatus,
)


class DeveloperEcosystemService:
    """Service for managing the developer ecosystem and SDKs"""

    def __init__(self, session: Session):
        self.session = session

    async def create_developer_profile(
        self, user_id: str, username: str, bio: str = None, skills: list[str] = None
    ) -> DeveloperProfile:
        """Create a new developer profile"""
        profile = DeveloperProfile(user_id=user_id, username=username, bio=bio, skills=skills or [])
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        return profile

    async def get_developer_profile(self, developer_id: str) -> DeveloperProfile | None:
        """Get developer profile by ID"""
        return self.session.execute(select(DeveloperProfile).where(DeveloperProfile.developer_id == developer_id)).first()

    async def get_sdk_release_info(self) -> dict[str, Any]:
        """Get latest SDK information for developers"""
        # Mocking SDK release data
        return {
            "latest_version": "v1.2.0",
            "release_date": datetime.now(datetime.UTC).isoformat(),
            "supported_languages": ["python", "typescript", "rust"],
            "download_urls": {"python": "pip install aitbc-agent-sdk", "typescript": "npm install @aitbc/agent-sdk"},
            "features": [
                "Advanced Meta-Learning Integration",
                "Cross-Domain Capability Synthesizer",
                "Distributed Task Processing Client",
                "Decentralized Governance Modules",
            ],
        }

    async def update_developer_reputation(self, developer_id: str, score_delta: float) -> DeveloperProfile:
        """Update a developer's reputation score and potentially tier"""
        profile = await self.get_developer_profile(developer_id)
        if not profile:
            raise ValueError(f"Developer {developer_id} not found")

        profile.reputation_score += score_delta

        # Automatic tier progression based on reputation
        if profile.reputation_score >= 1000:
            profile.tier = DeveloperTier.MASTER
        elif profile.reputation_score >= 500:
            profile.tier = DeveloperTier.EXPERT
        elif profile.reputation_score >= 100:
            profile.tier = DeveloperTier.BUILDER

        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        return profile


class ThirdPartySolutionService:
    """Service for managing the third-party agent solutions marketplace"""

    def __init__(self, session: Session):
        self.session = session

    async def publish_solution(self, developer_id: str, data: dict[str, Any]) -> AgentSolution:
        """Publish a new third-party agent solution"""
        solution = AgentSolution(
            developer_id=developer_id,
            title=data.get("title"),
            description=data.get("description"),
            version=data.get("version", "1.0.0"),
            capabilities=data.get("capabilities", []),
            frameworks=data.get("frameworks", []),
            price_model=data.get("price_model", "free"),
            price_amount=data.get("price_amount", 0.0),
            solution_metadata=data.get("metadata", {}),
            status=SolutionStatus.REVIEW,
        )

        # Auto-publish if free, otherwise manual review required
        if solution.price_model == "free":
            solution.status = SolutionStatus.PUBLISHED
            solution.published_at = datetime.now(datetime.UTC)

        self.session.add(solution)
        self.session.commit()
        self.session.refresh(solution)
        return solution

    async def list_published_solutions(self, category: str = None, limit: int = 50) -> list[AgentSolution]:
        """List published solutions, optionally filtered by capability/category"""
        query = select(AgentSolution).where(AgentSolution.status == SolutionStatus.PUBLISHED)

        # Filtering by JSON column capability (simplified)
        # In a real app, we might use PostgreSQL specific operators
        solutions = self.session.execute(query.limit(limit)).all()

        if category:
            solutions = [s for s in solutions if category in s.capabilities]

        return solutions

    async def purchase_solution(self, buyer_id: str, solution_id: str) -> dict[str, Any]:
        """Purchase or download a third-party solution"""
        solution = self.session.execute(select(AgentSolution).where(AgentSolution.solution_id == solution_id)).first()

        if not solution or solution.status != SolutionStatus.PUBLISHED:
            raise ValueError("Solution not found or not available")

        # Update download count
        solution.downloads += 1
        self.session.add(solution)

        # Update developer earnings if paid
        if solution.price_amount > 0:
            dev = self.session.execute(
                select(DeveloperProfile).where(DeveloperProfile.developer_id == solution.developer_id)
            ).first()
            if dev:
                dev.total_earnings += solution.price_amount
                self.session.add(dev)

        self.session.commit()

        # Return installation instructions / access token
        return {
            "success": True,
            "solution_id": solution_id,
            "access_token": f"acc_{uuid4().hex}",
            "installation_cmd": f"aitbc install {solution_id} --token acc_{uuid4().hex}",
        }


class InnovationLabService:
    """Service for managing agent innovation labs and research programs"""

    def __init__(self, session: Session):
        self.session = session

    async def propose_lab(self, researcher_id: str, data: dict[str, Any]) -> InnovationLab:
        """Propose a new innovation lab/research program"""
        lab = InnovationLab(
            title=data.get("title"),
            description=data.get("description"),
            research_area=data.get("research_area"),
            lead_researcher_id=researcher_id,
            funding_goal=data.get("funding_goal", 0.0),
            milestones=data.get("milestones", []),
        )

        self.session.add(lab)
        self.session.commit()
        self.session.refresh(lab)
        return lab

    async def join_lab(self, lab_id: str, developer_id: str) -> InnovationLab:
        """Join an active innovation lab"""
        lab = self.session.execute(select(InnovationLab).where(InnovationLab.lab_id == lab_id)).first()

        if not lab:
            raise ValueError("Lab not found")

        if developer_id not in lab.members:
            lab.members.append(developer_id)
            self.session.add(lab)
            self.session.commit()
            self.session.refresh(lab)

        return lab

    async def fund_lab(self, lab_id: str, amount: float) -> InnovationLab:
        """Provide funding to an innovation lab"""
        lab = self.session.execute(select(InnovationLab).where(InnovationLab.lab_id == lab_id)).first()

        if not lab:
            raise ValueError("Lab not found")

        lab.current_funding += amount
        if lab.status == LabStatus.FUNDING and lab.current_funding >= lab.funding_goal:
            lab.status = LabStatus.ACTIVE

        self.session.add(lab)
        self.session.commit()
        self.session.refresh(lab)
        return lab


class CommunityPlatformService:
    """Service for managing the community support and collaboration platform"""

    def __init__(self, session: Session):
        self.session = session

    async def create_post(self, author_id: str, data: dict[str, Any]) -> CommunityPost:
        """Create a new community post (question, tutorial, etc)"""
        post = CommunityPost(
            author_id=author_id,
            title=data.get("title", ""),
            content=data.get("content", ""),
            category=data.get("category", "discussion"),
            tags=data.get("tags", []),
            parent_post_id=data.get("parent_post_id"),
        )

        self.session.add(post)

        # Reward developer for participating
        if not post.parent_post_id:  # New thread
            dev_service = DeveloperEcosystemService(self.session)
            await dev_service.update_developer_reputation(author_id, 2.0)

        self.session.commit()
        self.session.refresh(post)
        return post

    async def get_feed(self, category: str = None, limit: int = 20) -> list[CommunityPost]:
        """Get the community feed"""
        query = select(CommunityPost).where(CommunityPost.parent_post_id is None)
        if category:
            query = query.where(CommunityPost.category == category)

        query = query.order_by(CommunityPost.created_at.desc()).limit(limit)
        return self.session.execute(query).all()

    async def upvote_post(self, post_id: str) -> CommunityPost:
        """Upvote a post and reward the author"""
        post = self.session.execute(select(CommunityPost).where(CommunityPost.post_id == post_id)).first()
        if not post:
            raise ValueError("Post not found")

        post.upvotes += 1
        self.session.add(post)

        # Reward author
        dev_service = DeveloperEcosystemService(self.session)
        await dev_service.update_developer_reputation(post.author_id, 1.0)

        self.session.commit()
        self.session.refresh(post)
        return post

    async def create_hackathon(self, organizer_id: str, data: dict[str, Any]) -> Hackathon:
        """Create a new agent innovation hackathon"""
        # Verify organizer is an expert or partner
        dev = self.session.execute(select(DeveloperProfile).where(DeveloperProfile.developer_id == organizer_id)).first()
        if not dev or dev.tier not in [DeveloperTier.EXPERT, DeveloperTier.MASTER, DeveloperTier.PARTNER]:
            raise ValueError("Only high-tier developers can organize hackathons")

        hackathon = Hackathon(
            title=data.get("title", ""),
            description=data.get("description", ""),
            theme=data.get("theme", ""),
            sponsor=data.get("sponsor", "AITBC Foundation"),
            prize_pool=data.get("prize_pool", 0.0),
            registration_start=datetime.fromisoformat(data.get("registration_start", datetime.now(datetime.UTC).isoformat())),
            registration_end=datetime.fromisoformat(data.get("registration_end")),
            event_start=datetime.fromisoformat(data.get("event_start")),
            event_end=datetime.fromisoformat(data.get("event_end")),
        )

        self.session.add(hackathon)
        self.session.commit()
        self.session.refresh(hackathon)
        return hackathon

    async def register_for_hackathon(self, hackathon_id: str, developer_id: str) -> Hackathon:
        """Register a developer for a hackathon"""
        hackathon = self.session.execute(select(Hackathon).where(Hackathon.hackathon_id == hackathon_id)).first()

        if not hackathon:
            raise ValueError("Hackathon not found")

        if hackathon.status not in [HackathonStatus.ANNOUNCED, HackathonStatus.REGISTRATION]:
            raise ValueError("Registration is not open for this hackathon")

        if developer_id not in hackathon.participants:
            hackathon.participants.append(developer_id)
            self.session.add(hackathon)
            self.session.commit()
            self.session.refresh(hackathon)

        return hackathon
