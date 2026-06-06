from datetime import datetime

from pydantic import BaseModel

from ..domain.developer_platform import CertificationLevel


class DeveloperCreate(BaseModel):
    wallet_address: str
    github_handle: str | None = None
    email: str | None = None
    skills: list[str] = []


class BountyCreate(BaseModel):
    title: str
    description: str
    required_skills: list[str] = []
    difficulty_level: CertificationLevel = CertificationLevel.INTERMEDIATE
    reward_amount: float
    creator_address: str
    deadline: datetime | None = None


class BountySubmissionCreate(BaseModel):
    developer_id: str
    github_pr_url: str | None = None
    submission_notes: str = ""


class CertificationGrant(BaseModel):
    developer_id: str
    certification_name: str
    level: CertificationLevel
    issued_by: str
    ipfs_credential_cid: str | None = None
