"""
Database models for confidential transactions
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import Column, String, DateTime, Boolean, Text, JSON, Integer, LargeBinary
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from ..database import Base


class ConfidentialTransactionDB(Base):
    """Database model for confidential transactions"""
    __tablename__ = "confidential_transactions"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Public fields (always visible)
    transaction_id = Column(String(255), unique=True, nullable=False, index=True)
    job_id = Column(String(255), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status = Column(String(50), nullable=False, default="created")
    
    # Encryption metadata
    confidential = Column(Boolean, nullable=False, default=False)
    algorithm = Column(String(50), nullable=True)
    
    # Encrypted data (stored as binary)
    encrypted_data = Column(LargeBinary, nullable=True)
    encrypted_nonce = Column(LargeBinary, nullable=True)
    encrypted_tag = Column(LargeBinary, nullable=True)
    
    # Encrypted keys for participants (JSON encoded)
    encrypted_keys = Column(JSON, nullable=True)
    participants = Column(JSON, nullable=True)
    
    # Access policies
    access_policies = Column(JSON, nullable=True)
    
    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(String(255), nullable=True)
    
    # Indexes for performance
    __table_args__ = (
        {'schema': 'aitbc'}
    )


class ParticipantKeyDB(Base):
    """Database model for participant encryption keys"""
    __tablename__ = "participant_keys"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    participant_id = Column(String(255), unique=True, nullable=False, index=True)
    
    # Key data (encrypted at rest)
    encrypted_private_key = Column(LargeBinary, nullable=False)
    public_key = Column(LargeBinary, nullable=False)
    
    # Key metadata
    algorithm = Column(String(50), nullable=False, default="X25519")
    version = Column(Integer, nullable=False, default=1)
    
    # Status
    active = Column(Boolean, nullable=False, default=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoke_reason = Column(String(255), nullable=True)
    
    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    rotated_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        {'schema': 'aitbc'}
    )


class ConfidentialAccessLogDB(Base):
    """Database model for confidential data access logs"""
    __tablename__ = "confidential_access_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Access details
    transaction_id = Column(String(255), nullable=True, index=True)
    participant_id = Column(String(255), nullable=False, index=True)
    purpose = Column(String(100), nullable=False)
    
    # Request details
    action = Column(String(100), nullable=False)
    resource = Column(String(100), nullable=False)
    outcome = Column(String(50), nullable=False)
    
    # Additional data
    details = Column(JSON, nullable=True)
    data_accessed = Column(JSON, nullable=True)
    
    # Metadata
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    authorization_id = Column(String(255), nullable=True)
    
    # Integrity
    signature = Column(String(128), nullable=True)  # SHA-512 hash
    
    # Timestamps
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    __table_args__ = (
        {'schema': 'aitbc'}
    )


class KeyRotationLogDB(Base):
    """Database model for key rotation logs"""
    __tablename__ = "key_rotation_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    participant_id = Column(String(255), nullable=False, index=True)
    old_version = Column(Integer, nullable=False)
    new_version = Column(Integer, nullable=False)
    
    # Rotation details
    rotated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reason = Column(String(255), nullable=False)
    
    # Who performed the rotation
    rotated_by = Column(String(255), nullable=True)
    
    __table_args__ = (
        {'schema': 'aitbc'}
    )


class AuditAuthorizationDB(Base):
    """Database model for audit authorizations"""
    __tablename__ = "audit_authorizations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Authorization details
    issuer = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    purpose = Column(String(100), nullable=False)
    
    # Validity period
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Authorization data
    signature = Column(String(512), nullable=False)
    metadata = Column(JSON, nullable=True)
    
    # Status
    active = Column(Boolean, nullable=False, default=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        {'schema': 'aitbc'}
    )
