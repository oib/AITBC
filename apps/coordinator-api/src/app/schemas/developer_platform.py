from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from .developer_platform import BountyStatus, CertificationLevel

class DeveloperCreate(BaseModel):
    wallet_address: str
    github_handle: Optional[str] = None
    email: Optional[str] = None
    skills: List[str] = []

class BountyCreate(BaseModel):
    title: str
    description: str
    required_skills: List[str] = []
    difficulty_level: CertificationLevel = CertificationLevel.INTERMEDIATE
    reward_amount: float
    creator_address: str
    deadline: Optional[datetime] = None

class BountySubmissionCreate(BaseModel):
    developer_id: str
    github_pr_url: Optional[str] = None
    submission_notes: str = ""

class CertificationGrant(BaseModel):
    developer_id: str
    certification_name: str
    level: CertificationLevel
    issued_by: str
    ipfs_credential_cid: Optional[str] = None
