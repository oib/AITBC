import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timedelta

from sqlmodel import Session, create_engine, SQLModel
from sqlmodel.pool import StaticPool
from fastapi import HTTPException

from app.services.developer_platform_service import DeveloperPlatformService
from app.domain.developer_platform import BountyStatus, CertificationLevel
from app.schemas.developer_platform import (
    DeveloperCreate, BountyCreate, BountySubmissionCreate, CertificationGrant
)

@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()

@pytest.fixture
def mock_contract_service():
    return AsyncMock()

@pytest.fixture
def dev_service(test_db, mock_contract_service):
    return DeveloperPlatformService(
        session=test_db, 
        contract_service=mock_contract_service
    )

@pytest.mark.asyncio
async def test_register_developer(dev_service):
    req = DeveloperCreate(
        wallet_address="0xDev1",
        github_handle="dev_one",
        skills=["python", "solidity"]
    )
    
    dev = await dev_service.register_developer(req)
    
    assert dev.wallet_address == "0xDev1"
    assert dev.reputation_score == 0.0
    assert "solidity" in dev.skills

@pytest.mark.asyncio
async def test_grant_certification(dev_service):
    dev = await dev_service.register_developer(DeveloperCreate(wallet_address="0xDev1"))
    
    req = CertificationGrant(
        developer_id=dev.id,
        certification_name="ZK-Circuit Architect",
        level=CertificationLevel.ADVANCED,
        issued_by="0xDAOAdmin"
    )
    
    cert = await dev_service.grant_certification(req)
    
    assert cert.developer_id == dev.id
    assert cert.level == CertificationLevel.ADVANCED
    
    # Check reputation boost (ADVANCED = +50.0)
    dev_service.session.refresh(dev)
    assert dev.reputation_score == 50.0

@pytest.mark.asyncio
async def test_bounty_lifecycle(dev_service):
    # 1. Register Developer
    dev = await dev_service.register_developer(DeveloperCreate(wallet_address="0xDev1"))
    
    # 2. Create Bounty
    bounty_req = BountyCreate(
        title="Implement Atomic Swap",
        description="Write a secure HTLC contract",
        reward_amount=1000.0,
        creator_address="0xCreator"
    )
    bounty = await dev_service.create_bounty(bounty_req)
    assert bounty.status == BountyStatus.OPEN
    
    # 3. Submit Work
    sub_req = BountySubmissionCreate(
        developer_id=dev.id,
        github_pr_url="https://github.com/aitbc/pr/1"
    )
    sub = await dev_service.submit_bounty(bounty.id, sub_req)
    assert sub.bounty_id == bounty.id
    
    dev_service.session.refresh(bounty)
    assert bounty.status == BountyStatus.IN_REVIEW
    
    # 4. Approve Submission
    appr_sub = await dev_service.approve_submission(sub.id, reviewer_address="0xReviewer", review_notes="Looks great!")
    
    assert appr_sub.is_approved is True
    assert appr_sub.tx_hash_reward is not None
    
    dev_service.session.refresh(bounty)
    dev_service.session.refresh(dev)
    
    assert bounty.status == BountyStatus.COMPLETED
    assert bounty.assigned_developer_id == dev.id
    assert dev.total_earned_aitbc == 1000.0
    assert dev.reputation_score == 5.0 # Base bump for finishing a bounty
