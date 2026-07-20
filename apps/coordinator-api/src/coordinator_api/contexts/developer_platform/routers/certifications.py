"""Certification management endpoints for the Developer Platform."""

from datetime import UTC, datetime
from typing import Annotated, Any

from aitbc.rate_limiting import rate_limit
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from ....storage.db import get_session
from ..domain.developer_platform import CertificationLevel, DeveloperCertification
from ..schemas.developer_platform import CertificationGrant
from ..services.developer_platform_service import DeveloperPlatformService
from .common import get_developer_platform_service

router = APIRouter(tags=["Developer Platform"])


@router.post("/certifications", response_model=dict[str, Any])
@rate_limit(rate=20, per=60)
async def grant_certification(
    request: CertificationGrant,
    request_http: Request,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> dict[str, Any]:
    """Grant a certification to a developer."""

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
            "granted_at": certification.issued_at.isoformat(),
            "message": "Certification granted successfully",
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error granting certification") from None


@router.get("/certifications/types", response_model=list[dict[str, Any]])
@rate_limit(rate=500, per=60)
async def get_certification_types(request: Request) -> list[dict[str, Any]]:
    """Get available certification types."""

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
                "skills_required": ["kubernetes", "ci-cd"],
            },
        ]

        return certification_types

    except Exception:
        raise HTTPException(status_code=500, detail="Error getting certification types") from None


@router.get("/certifications/{wallet_address}", response_model=list[dict[str, Any]])
@rate_limit(rate=200, per=60)
async def get_developer_certifications(
    wallet_address: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    dev_service: Annotated[DeveloperPlatformService, Depends(get_developer_platform_service)],
) -> list[dict[str, Any]]:
    """Get certifications for a developer."""

    try:
        profile = await dev_service.get_developer_profile(wallet_address)
        if not profile:
            raise HTTPException(status_code=404, detail="Developer profile not found")

        certifications = (
            session.execute(select(DeveloperCertification).where(DeveloperCertification.developer_id == profile.id))
            .scalars()
            .all()
        )

        return [
            {
                "id": cert.id,
                "certification_name": cert.certification_name,
                "level": cert.level.value,
                "issued_by": cert.issued_by,
                "ipfs_credential_cid": cert.ipfs_credential_cid,
                "granted_at": cert.issued_at.isoformat(),
                "is_verified": True,
            }
            for cert in certifications
        ]

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error getting certifications") from None


@router.get("/certifications/verify/{certification_id}", response_model=dict[str, Any])
@rate_limit(rate=200, per=60)
async def verify_certification(
    request: Request, certification_id: str, session: Annotated[Session, Depends(get_session)]
) -> dict[str, Any]:
    """Verify a certification by ID."""

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
            "granted_at": certification.issued_at.isoformat(),
            "is_valid": True,
            "verification_timestamp": datetime.now(UTC).isoformat(),
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error verifying certification") from None
