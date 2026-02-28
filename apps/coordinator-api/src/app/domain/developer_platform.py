"""
Developer Platform Domain Models

Domain models for managing the developer ecosystem, bounties, certifications, and regional hubs.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel, Relationship

class BountyStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class CertificationLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"

class DeveloperProfile(SQLModel, table=True):
    """Profile for a developer in the AITBC ecosystem"""
    __tablename__ = "developer_profile"
    
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    wallet_address: str = Field(index=True, unique=True)
    github_handle: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    
    reputation_score: float = Field(default=0.0)
    total_earned_aitbc: float = Field(default=0.0)
    
    skills: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    certifications: List["DeveloperCertification"] = Relationship(back_populates="developer")
    bounty_submissions: List["BountySubmission"] = Relationship(back_populates="developer")

class DeveloperCertification(SQLModel, table=True):
    """Certifications earned by developers"""
    __tablename__ = "developer_certification"
    
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    developer_id: str = Field(foreign_key="developer_profile.id", index=True)
    
    certification_name: str = Field(index=True)
    level: CertificationLevel = Field(default=CertificationLevel.BEGINNER)
    
    issued_by: str = Field() # Could be an agent or a DAO entity
    issued_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(default=None)
    
    ipfs_credential_cid: Optional[str] = Field(default=None) # Proof of certification

    # Relationships
    developer: DeveloperProfile = Relationship(back_populates="certifications")

class RegionalHub(SQLModel, table=True):
    """Regional developer hubs for local coordination"""
    __tablename__ = "regional_hub"
    
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    region_code: str = Field(index=True, unique=True) # e.g. "US-EAST", "EU-CENTRAL"
    name: str = Field()
    description: Optional[str] = Field(default=None)
    
    lead_wallet_address: str = Field() # Hub lead
    member_count: int = Field(default=0)
    
    budget_allocation: float = Field(default=0.0)
    spent_budget: float = Field(default=0.0)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)

class BountyTask(SQLModel, table=True):
    """Automated bounty board tasks"""
    __tablename__ = "bounty_task"
    
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    title: str = Field()
    description: str = Field()
    
    required_skills: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    difficulty_level: CertificationLevel = Field(default=CertificationLevel.INTERMEDIATE)
    
    reward_amount: float = Field()
    reward_token: str = Field(default="AITBC")
    
    status: BountyStatus = Field(default=BountyStatus.OPEN, index=True)
    
    creator_address: str = Field(index=True)
    assigned_developer_id: Optional[str] = Field(foreign_key="developer_profile.id", default=None)
    
    deadline: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    submissions: List["BountySubmission"] = Relationship(back_populates="bounty")

class BountySubmission(SQLModel, table=True):
    """Submissions for bounty tasks"""
    __tablename__ = "bounty_submission"
    
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    bounty_id: str = Field(foreign_key="bounty_task.id", index=True)
    developer_id: str = Field(foreign_key="developer_profile.id", index=True)
    
    github_pr_url: Optional[str] = Field(default=None)
    submission_notes: str = Field(default="")
    
    is_approved: bool = Field(default=False)
    review_notes: Optional[str] = Field(default=None)
    reviewer_address: Optional[str] = Field(default=None)
    
    tx_hash_reward: Optional[str] = Field(default=None) # Hash of the reward payout transaction
    
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_at: Optional[datetime] = Field(default=None)

    # Relationships
    bounty: BountyTask = Relationship(back_populates="submissions")
    developer: DeveloperProfile = Relationship(back_populates="bounty_submissions")
