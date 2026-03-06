"""
Repository layer for confidential transactions
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
import json
from base64 import b64encode, b64decode

from sqlalchemy import select, update, delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.confidential import (
    ConfidentialTransactionDB,
    ParticipantKeyDB,
    ConfidentialAccessLogDB,
    KeyRotationLogDB,
    AuditAuthorizationDB
)
from ..schemas import (
    ConfidentialTransaction,
    KeyPair,
    ConfidentialAccessLog,
    KeyRotationLog,
    AuditAuthorization
)
from sqlmodel import SQLModel as BaseAsyncSession


class ConfidentialTransactionRepository:
    """Repository for confidential transaction operations"""
    
    async def create(
        self,
        session: AsyncSession,
        transaction: ConfidentialTransaction
    ) -> ConfidentialTransactionDB:
        """Create a new confidential transaction"""
        db_transaction = ConfidentialTransactionDB(
            transaction_id=transaction.transaction_id,
            job_id=transaction.job_id,
            status=transaction.status,
            confidential=transaction.confidential,
            algorithm=transaction.algorithm,
            encrypted_data=b64decode(transaction.encrypted_data) if transaction.encrypted_data else None,
            encrypted_keys=transaction.encrypted_keys,
            participants=transaction.participants,
            access_policies=transaction.access_policies,
            created_by=transaction.participants[0] if transaction.participants else None
        )
        
        session.add(db_transaction)
        await session.commit()
        await session.refresh(db_transaction)
        
        return db_transaction
    
    async def get_by_id(
        self,
        session: AsyncSession,
        transaction_id: str
    ) -> Optional[ConfidentialTransactionDB]:
        """Get transaction by ID"""
        stmt = select(ConfidentialTransactionDB).where(
            ConfidentialTransactionDB.transaction_id == transaction_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_job_id(
        self,
        session: AsyncSession,
        job_id: str
    ) -> Optional[ConfidentialTransactionDB]:
        """Get transaction by job ID"""
        stmt = select(ConfidentialTransactionDB).where(
            ConfidentialTransactionDB.job_id == job_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_by_participant(
        self,
        session: AsyncSession,
        participant_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[ConfidentialTransactionDB]:
        """List transactions for a participant"""
        stmt = select(ConfidentialTransactionDB).where(
            ConfidentialTransactionDB.participants.contains([participant_id])
        ).offset(offset).limit(limit)
        
        result = await session.execute(stmt)
        return result.scalars().all()
    
    async def update_status(
        self,
        session: AsyncSession,
        transaction_id: str,
        status: str
    ) -> bool:
        """Update transaction status"""
        stmt = update(ConfidentialTransactionDB).where(
            ConfidentialTransactionDB.transaction_id == transaction_id
        ).values(status=status)
        
        result = await session.execute(stmt)
        await session.commit()
        
        return result.rowcount > 0
    
    async def delete(
        self,
        session: AsyncSession,
        transaction_id: str
    ) -> bool:
        """Delete a transaction"""
        stmt = delete(ConfidentialTransactionDB).where(
            ConfidentialTransactionDB.transaction_id == transaction_id
        )
        
        result = await session.execute(stmt)
        await session.commit()
        
        return result.rowcount > 0


class ParticipantKeyRepository:
    """Repository for participant key operations"""
    
    async def create(
        self,
        session: AsyncSession,
        key_pair: KeyPair
    ) -> ParticipantKeyDB:
        """Store a new key pair"""
        # In production, private_key should be encrypted with master key
        db_key = ParticipantKeyDB(
            participant_id=key_pair.participant_id,
            encrypted_private_key=key_pair.private_key,
            public_key=key_pair.public_key,
            algorithm=key_pair.algorithm,
            version=key_pair.version,
            active=True
        )
        
        session.add(db_key)
        await session.commit()
        await session.refresh(db_key)
        
        return db_key
    
    async def get_by_participant(
        self,
        session: AsyncSession,
        participant_id: str,
        active_only: bool = True
    ) -> Optional[ParticipantKeyDB]:
        """Get key pair for participant"""
        stmt = select(ParticipantKeyDB).where(
            ParticipantKeyDB.participant_id == participant_id
        )
        
        if active_only:
            stmt = stmt.where(ParticipantKeyDB.active == True)
        
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def update_active(
        self,
        session: AsyncSession,
        participant_id: str,
        active: bool,
        reason: Optional[str] = None
    ) -> bool:
        """Update key active status"""
        stmt = update(ParticipantKeyDB).where(
            ParticipantKeyDB.participant_id == participant_id
        ).values(
            active=active,
            revoked_at=datetime.utcnow() if not active else None,
            revoke_reason=reason
        )
        
        result = await session.execute(stmt)
        await session.commit()
        
        return result.rowcount > 0
    
    async def rotate(
        self,
        session: AsyncSession,
        participant_id: str,
        new_key_pair: KeyPair
    ) -> ParticipantKeyDB:
        """Rotate to new key pair"""
        # Deactivate old key
        await self.update_active(session, participant_id, False, "rotation")
        
        # Store new key
        return await self.create(session, new_key_pair)
    
    async def list_active(
        self,
        session: AsyncSession,
        limit: int = 100,
        offset: int = 0
    ) -> List[ParticipantKeyDB]:
        """List active keys"""
        stmt = select(ParticipantKeyDB).where(
            ParticipantKeyDB.active == True
        ).offset(offset).limit(limit)
        
        result = await session.execute(stmt)
        return result.scalars().all()


class AccessLogRepository:
    """Repository for access log operations"""
    
    async def create(
        self,
        session: AsyncSession,
        log: ConfidentialAccessLog
    ) -> ConfidentialAccessLogDB:
        """Create access log entry"""
        db_log = ConfidentialAccessLogDB(
            transaction_id=log.transaction_id,
            participant_id=log.participant_id,
            purpose=log.purpose,
            action=log.action,
            resource=log.resource,
            outcome=log.outcome,
            details=log.details,
            data_accessed=log.data_accessed,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            authorization_id=log.authorized_by,
            signature=log.signature
        )
        
        session.add(db_log)
        await session.commit()
        await session.refresh(db_log)
        
        return db_log
    
    async def query(
        self,
        session: AsyncSession,
        transaction_id: Optional[str] = None,
        participant_id: Optional[str] = None,
        purpose: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[ConfidentialAccessLogDB]:
        """Query access logs"""
        stmt = select(ConfidentialAccessLogDB)
        
        # Build filters
        filters = []
        if transaction_id:
            filters.append(ConfidentialAccessLogDB.transaction_id == transaction_id)
        if participant_id:
            filters.append(ConfidentialAccessLogDB.participant_id == participant_id)
        if purpose:
            filters.append(ConfidentialAccessLogDB.purpose == purpose)
        if start_time:
            filters.append(ConfidentialAccessLogDB.timestamp >= start_time)
        if end_time:
            filters.append(ConfidentialAccessLogDB.timestamp <= end_time)
        
        if filters:
            stmt = stmt.where(and_(*filters))
        
        # Order by timestamp descending
        stmt = stmt.order_by(ConfidentialAccessLogDB.timestamp.desc())
        stmt = stmt.offset(offset).limit(limit)
        
        result = await session.execute(stmt)
        return result.scalars().all()
    
    async def count(
        self,
        session: AsyncSession,
        transaction_id: Optional[str] = None,
        participant_id: Optional[str] = None,
        purpose: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> int:
        """Count access logs matching criteria"""
        stmt = select(ConfidentialAccessLogDB)
        
        # Build filters
        filters = []
        if transaction_id:
            filters.append(ConfidentialAccessLogDB.transaction_id == transaction_id)
        if participant_id:
            filters.append(ConfidentialAccessLogDB.participant_id == participant_id)
        if purpose:
            filters.append(ConfidentialAccessLogDB.purpose == purpose)
        if start_time:
            filters.append(ConfidentialAccessLogDB.timestamp >= start_time)
        if end_time:
            filters.append(ConfidentialAccessLogDB.timestamp <= end_time)
        
        if filters:
            stmt = stmt.where(and_(*filters))
        
        result = await session.execute(stmt)
        return len(result.all())


class KeyRotationRepository:
    """Repository for key rotation logs"""
    
    async def create(
        self,
        session: AsyncSession,
        log: KeyRotationLog
    ) -> KeyRotationLogDB:
        """Create key rotation log"""
        db_log = KeyRotationLogDB(
            participant_id=log.participant_id,
            old_version=log.old_version,
            new_version=log.new_version,
            rotated_at=log.rotated_at,
            reason=log.reason
        )
        
        session.add(db_log)
        await session.commit()
        await session.refresh(db_log)
        
        return db_log
    
    async def list_by_participant(
        self,
        session: AsyncSession,
        participant_id: str,
        limit: int = 50
    ) -> List[KeyRotationLogDB]:
        """List rotation logs for participant"""
        stmt = select(KeyRotationLogDB).where(
            KeyRotationLogDB.participant_id == participant_id
        ).order_by(KeyRotationLogDB.rotated_at.desc()).limit(limit)
        
        result = await session.execute(stmt)
        return result.scalars().all()


class AuditAuthorizationRepository:
    """Repository for audit authorizations"""
    
    async def create(
        self,
        session: AsyncSession,
        auth: AuditAuthorization
    ) -> AuditAuthorizationDB:
        """Create audit authorization"""
        db_auth = AuditAuthorizationDB(
            issuer=auth.issuer,
            subject=auth.subject,
            purpose=auth.purpose,
            created_at=auth.created_at,
            expires_at=auth.expires_at,
            signature=auth.signature,
            metadata=auth.__dict__
        )
        
        session.add(db_auth)
        await session.commit()
        await session.refresh(db_auth)
        
        return db_auth
    
    async def get_valid(
        self,
        session: AsyncSession,
        authorization_id: str
    ) -> Optional[AuditAuthorizationDB]:
        """Get valid authorization"""
        stmt = select(AuditAuthorizationDB).where(
            and_(
                AuditAuthorizationDB.id == authorization_id,
                AuditAuthorizationDB.active == True,
                AuditAuthorizationDB.expires_at > datetime.utcnow()
            )
        )
        
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def revoke(
        self,
        session: AsyncSession,
        authorization_id: str
    ) -> bool:
        """Revoke authorization"""
        stmt = update(AuditAuthorizationDB).where(
            AuditAuthorizationDB.id == authorization_id
        ).values(active=False, revoked_at=datetime.utcnow())
        
        result = await session.execute(stmt)
        await session.commit()
        
        return result.rowcount > 0
    
    async def cleanup_expired(
        self,
        session: AsyncSession
    ) -> int:
        """Clean up expired authorizations"""
        stmt = update(AuditAuthorizationDB).where(
            AuditAuthorizationDB.expires_at < datetime.utcnow()
        ).values(active=False)
        
        result = await session.execute(stmt)
        await session.commit()
        
        return result.rowcount
