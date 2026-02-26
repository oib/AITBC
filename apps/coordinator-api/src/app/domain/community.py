"""
Community and Developer Ecosystem Models
Database models for OpenClaw agent community, third-party solutions, and innovation labs
"""

from typing import Optional, List, Dict, Any
from sqlmodel import Field, SQLModel, Column, JSON, Relationship
from datetime import datetime
from enum import Enum
import uuid

class DeveloperTier(str, Enum):
    NOVICE = "novice"
    BUILDER = "builder"
    EXPERT = "expert"
    MASTER = "master"
    PARTNER = "partner"

class SolutionStatus(str, Enum):
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    REJECTED = "rejected"

class LabStatus(str, Enum):
    PROPOSED = "proposed"
    FUNDING = "funding"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"

class HackathonStatus(str, Enum):
    ANNOUNCED = "announced"
    REGISTRATION = "registration"
    ONGOING = "ongoing"
    JUDGING = "judging"
    COMPLETED = "completed"

class DeveloperProfile(SQLModel, table=True):
    """Profile for a developer in the OpenClaw community"""
    __tablename__ = "developer_profiles"

    developer_id: str = Field(primary_key=True, default_factory=lambda: f"dev_{uuid.uuid4().hex[:8]}")
    user_id: str = Field(index=True)
    username: str = Field(unique=True)
    bio: Optional[str] = None
    
    tier: DeveloperTier = Field(default=DeveloperTier.NOVICE)
    reputation_score: float = Field(default=0.0)
    total_earnings: float = Field(default=0.0)
    
    skills: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    github_handle: Optional[str] = None
    website: Optional[str] = None
    
    joined_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)

class AgentSolution(SQLModel, table=True):
    """A third-party agent solution available in the developer marketplace"""
    __tablename__ = "agent_solutions"

    solution_id: str = Field(primary_key=True, default_factory=lambda: f"sol_{uuid.uuid4().hex[:8]}")
    developer_id: str = Field(foreign_key="developer_profiles.developer_id")
    
    title: str
    description: str
    version: str = Field(default="1.0.0")
    
    capabilities: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    frameworks: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    
    price_model: str = Field(default="free") # free, one_time, subscription, usage_based
    price_amount: float = Field(default=0.0)
    currency: str = Field(default="AITBC")
    
    status: SolutionStatus = Field(default=SolutionStatus.DRAFT)
    downloads: int = Field(default=0)
    average_rating: float = Field(default=0.0)
    review_count: int = Field(default=0)
    
    solution_metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    published_at: Optional[datetime] = None

class InnovationLab(SQLModel, table=True):
    """Research program or innovation lab for agent development"""
    __tablename__ = "innovation_labs"

    lab_id: str = Field(primary_key=True, default_factory=lambda: f"lab_{uuid.uuid4().hex[:8]}")
    title: str
    description: str
    research_area: str
    
    lead_researcher_id: str = Field(foreign_key="developer_profiles.developer_id")
    members: List[str] = Field(default_factory=list, sa_column=Column(JSON)) # List of developer_ids
    
    status: LabStatus = Field(default=LabStatus.PROPOSED)
    funding_goal: float = Field(default=0.0)
    current_funding: float = Field(default=0.0)
    
    milestones: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    publications: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    target_completion: Optional[datetime] = None

class CommunityPost(SQLModel, table=True):
    """A post in the community support/collaboration platform"""
    __tablename__ = "community_posts"

    post_id: str = Field(primary_key=True, default_factory=lambda: f"post_{uuid.uuid4().hex[:8]}")
    author_id: str = Field(foreign_key="developer_profiles.developer_id")
    
    title: str
    content: str
    category: str = Field(default="discussion") # discussion, question, showcase, tutorial
    tags: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    
    upvotes: int = Field(default=0)
    views: int = Field(default=0)
    is_resolved: bool = Field(default=False)
    
    parent_post_id: Optional[str] = Field(default=None, foreign_key="community_posts.post_id")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Hackathon(SQLModel, table=True):
    """Innovation challenge or hackathon"""
    __tablename__ = "hackathons"

    hackathon_id: str = Field(primary_key=True, default_factory=lambda: f"hack_{uuid.uuid4().hex[:8]}")
    title: str
    description: str
    theme: str
    
    sponsor: str = Field(default="AITBC Foundation")
    prize_pool: float = Field(default=0.0)
    prize_currency: str = Field(default="AITBC")
    
    status: HackathonStatus = Field(default=HackathonStatus.ANNOUNCED)
    participants: List[str] = Field(default_factory=list, sa_column=Column(JSON)) # List of developer_ids
    submissions: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    
    registration_start: datetime
    registration_end: datetime
    event_start: datetime
    event_end: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)
