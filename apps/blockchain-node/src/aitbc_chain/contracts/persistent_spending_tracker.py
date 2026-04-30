"""
Persistent Spending Tracker - Database-Backed Security
Fixes the critical vulnerability where spending limits were lost on restart
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, UTC, timedelta
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from eth_utils import to_checksum_address
import json

Base = declarative_base()


class SpendingRecord(Base):
    """Database model for spending tracking"""
    __tablename__ = "spending_records"
    
    id = Column(String, primary_key=True)
    agent_address = Column(String, index=True)
    period_type = Column(String, index=True)  # hour, day, week
    period_key = Column(String, index=True)
    amount = Column(Float)
    transaction_hash = Column(String)
    timestamp = Column(DateTime, default=datetime.now(datetime.UTC))
    
    # Composite indexes for performance
    __table_args__ = (
        Index('idx_agent_period', 'agent_address', 'period_type', 'period_key'),
        Index('idx_timestamp', 'timestamp'),
    )


class SpendingLimit(Base):
    """Database model for spending limits"""
    __tablename__ = "spending_limits"
    
    agent_address = Column(String, primary_key=True)
    per_transaction = Column(Float)
    per_hour = Column(Float)
    per_day = Column(Float)
    per_week = Column(Float)
    time_lock_threshold = Column(Float)
    time_lock_delay_hours = Column(Integer)
    updated_at = Column(DateTime, default=datetime.now(datetime.UTC))
    updated_by = Column(String)  # Guardian who updated


class GuardianAuthorization(Base):
    """Database model for guardian authorizations"""
    __tablename__ = "guardian_authorizations"
    
    id = Column(String, primary_key=True)
    agent_address = Column(String, index=True)
    guardian_address = Column(String, index=True)
    is_active = Column(Boolean, default=True)
    added_at = Column(DateTime, default=datetime.now(datetime.UTC))
    added_by = Column(String)


@dataclass
class SpendingCheckResult:
    """Result of spending limit check"""
    allowed: bool
    reason: str
    current_spent: Dict[str, float]
    remaining: Dict[str, float]
    requires_time_lock: bool
    time_lock_until: Optional[datetime] = None


class PersistentSpendingTracker:
    """
    Database-backed spending tracker that survives restarts
    """
    
    def __init__(self, database_url: str = "sqlite:///spending_tracker.db"):
        self.engine = create_engine(database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def get_session(self) -> Session:
        """Get database session"""
        return self.SessionLocal()
    
    def _get_period_key(self, timestamp: datetime, period: str) -> str:
        """Generate period key for spending tracking"""
        if period == "hour":
            return timestamp.strftime("%Y-%m-%d-%H")
        elif period == "day":
            return timestamp.strftime("%Y-%m-%d")
        elif period == "week":
            # Get week number (Monday as first day)
            week_num = timestamp.isocalendar()[1]
            return f"{timestamp.year}-W{week_num:02d}"
        else:
            raise ValueError(f"Invalid period: {period}")
    
    def get_spent_in_period(self, agent_address: str, period: str, timestamp: datetime = None) -> float:
        """
        Get total spent in given period from database
        
        Args:
            agent_address: Agent wallet address
            period: Period type (hour, day, week)
            timestamp: Timestamp to check (default: now)
            
        Returns:
            Total amount spent in period
        """
        if timestamp is None:
            timestamp = datetime.now(datetime.UTC)
        
        period_key = self._get_period_key(timestamp, period)
        agent_address = to_checksum_address(agent_address)
        
        with self.get_session() as session:
            total = session.query(SpendingRecord).filter(
                SpendingRecord.agent_address == agent_address,
                SpendingRecord.period_type == period,
                SpendingRecord.period_key == period_key
            ).with_entities(SpendingRecord.amount).all()
            
            return sum(record.amount for record in total)
    
    def record_spending(self, agent_address: str, amount: float, transaction_hash: str, timestamp: datetime = None) -> bool:
        """
        Record a spending transaction in the database
        
        Args:
            agent_address: Agent wallet address
            amount: Amount spent
            transaction_hash: Transaction hash
            timestamp: Transaction timestamp (default: now)
            
        Returns:
            True if recorded successfully
        """
        if timestamp is None:
            timestamp = datetime.now(datetime.UTC)
        
        agent_address = to_checksum_address(agent_address)
        
        try:
            with self.get_session() as session:
                # Record for all periods
                periods = ["hour", "day", "week"]
                
                for period in periods:
                    period_key = self._get_period_key(timestamp, period)
                    
                    record = SpendingRecord(
                        id=f"{transaction_hash}_{period}",
                        agent_address=agent_address,
                        period_type=period,
                        period_key=period_key,
                        amount=amount,
                        transaction_hash=transaction_hash,
                        timestamp=timestamp
                    )
                    
                    session.add(record)
                
                session.commit()
                return True
                
        except Exception as e:
            print(f"Failed to record spending: {e}")
            return False
    
    def check_spending_limits(self, agent_address: str, amount: float, timestamp: datetime = None) -> SpendingCheckResult:
        """
        Check if amount exceeds spending limits using persistent data
        
        Args:
            agent_address: Agent wallet address
            amount: Amount to check
            timestamp: Timestamp for check (default: now)
            
        Returns:
            Spending check result
        """
        if timestamp is None:
            timestamp = datetime.now(datetime.UTC)
        
        agent_address = to_checksum_address(agent_address)
        
        # Get spending limits from database
        with self.get_session() as session:
            limits = session.query(SpendingLimit).filter(
                SpendingLimit.agent_address == agent_address
            ).first()
            
            if not limits:
                # Default limits if not set
                limits = SpendingLimit(
                    agent_address=agent_address,
                    per_transaction=1000.0,
                    per_hour=5000.0,
                    per_day=20000.0,
                    per_week=100000.0,
                    time_lock_threshold=5000.0,
                    time_lock_delay_hours=24
                )
                session.add(limits)
                session.commit()
        
        # Check each limit
        current_spent = {}
        remaining = {}
        
        # Per-transaction limit
        if amount > limits.per_transaction:
            return SpendingCheckResult(
                allowed=False,
                reason=f"Amount {amount} exceeds per-transaction limit {limits.per_transaction}",
                current_spent=current_spent,
                remaining=remaining,
                requires_time_lock=False
            )
        
        # Per-hour limit
        spent_hour = self.get_spent_in_period(agent_address, "hour", timestamp)
        current_spent["hour"] = spent_hour
        remaining["hour"] = limits.per_hour - spent_hour
        
        if spent_hour + amount > limits.per_hour:
            return SpendingCheckResult(
                allowed=False,
                reason=f"Hourly spending {spent_hour + amount} would exceed limit {limits.per_hour}",
                current_spent=current_spent,
                remaining=remaining,
                requires_time_lock=False
            )
        
        # Per-day limit
        spent_day = self.get_spent_in_period(agent_address, "day", timestamp)
        current_spent["day"] = spent_day
        remaining["day"] = limits.per_day - spent_day
        
        if spent_day + amount > limits.per_day:
            return SpendingCheckResult(
                allowed=False,
                reason=f"Daily spending {spent_day + amount} would exceed limit {limits.per_day}",
                current_spent=current_spent,
                remaining=remaining,
                requires_time_lock=False
            )
        
        # Per-week limit
        spent_week = self.get_spent_in_period(agent_address, "week", timestamp)
        current_spent["week"] = spent_week
        remaining["week"] = limits.per_week - spent_week
        
        if spent_week + amount > limits.per_week:
            return SpendingCheckResult(
                allowed=False,
                reason=f"Weekly spending {spent_week + amount} would exceed limit {limits.per_week}",
                current_spent=current_spent,
                remaining=remaining,
                requires_time_lock=False
            )
        
        # Check time lock requirement
        requires_time_lock = amount >= limits.time_lock_threshold
        time_lock_until = None
        
        if requires_time_lock:
            time_lock_until = timestamp + timedelta(hours=limits.time_lock_delay_hours)
        
        return SpendingCheckResult(
            allowed=True,
            reason="Spending limits check passed",
            current_spent=current_spent,
            remaining=remaining,
            requires_time_lock=requires_time_lock,
            time_lock_until=time_lock_until
        )
    
    def update_spending_limits(self, agent_address: str, new_limits: Dict, guardian_address: str) -> bool:
        """
        Update spending limits for an agent
        
        Args:
            agent_address: Agent wallet address
            new_limits: New spending limits
            guardian_address: Guardian making the change
            
        Returns:
            True if updated successfully
        """
        agent_address = to_checksum_address(agent_address)
        guardian_address = to_checksum_address(guardian_address)
        
        # Verify guardian authorization
        if not self.is_guardian_authorized(agent_address, guardian_address):
            return False
        
        try:
            with self.get_session() as session:
                limits = session.query(SpendingLimit).filter(
                    SpendingLimit.agent_address == agent_address
                ).first()
                
                if limits:
                    limits.per_transaction = new_limits.get("per_transaction", limits.per_transaction)
                    limits.per_hour = new_limits.get("per_hour", limits.per_hour)
                    limits.per_day = new_limits.get("per_day", limits.per_day)
                    limits.per_week = new_limits.get("per_week", limits.per_week)
                    limits.time_lock_threshold = new_limits.get("time_lock_threshold", limits.time_lock_threshold)
                    limits.time_lock_delay_hours = new_limits.get("time_lock_delay_hours", limits.time_lock_delay_hours)
                    limits.updated_at = datetime.now(datetime.UTC)
                    limits.updated_by = guardian_address
                else:
                    limits = SpendingLimit(
                        agent_address=agent_address,
                        per_transaction=new_limits.get("per_transaction", 1000.0),
                        per_hour=new_limits.get("per_hour", 5000.0),
                        per_day=new_limits.get("per_day", 20000.0),
                        per_week=new_limits.get("per_week", 100000.0),
                        time_lock_threshold=new_limits.get("time_lock_threshold", 5000.0),
                        time_lock_delay_hours=new_limits.get("time_lock_delay_hours", 24),
                        updated_at=datetime.now(datetime.UTC),
                        updated_by=guardian_address
                    )
                    session.add(limits)
                
                session.commit()
                return True
                
        except Exception as e:
            print(f"Failed to update spending limits: {e}")
            return False
    
    def add_guardian(self, agent_address: str, guardian_address: str, added_by: str) -> bool:
        """
        Add a guardian for an agent
        
        Args:
            agent_address: Agent wallet address
            guardian_address: Guardian address
            added_by: Who added this guardian
            
        Returns:
            True if added successfully
        """
        agent_address = to_checksum_address(agent_address)
        guardian_address = to_checksum_address(guardian_address)
        added_by = to_checksum_address(added_by)
        
        try:
            with self.get_session() as session:
                # Check if already exists
                existing = session.query(GuardianAuthorization).filter(
                    GuardianAuthorization.agent_address == agent_address,
                    GuardianAuthorization.guardian_address == guardian_address
                ).first()
                
                if existing:
                    existing.is_active = True
                    existing.added_at = datetime.now(datetime.UTC)
                    existing.added_by = added_by
                else:
                    auth = GuardianAuthorization(
                        id=f"{agent_address}_{guardian_address}",
                        agent_address=agent_address,
                        guardian_address=guardian_address,
                        is_active=True,
                        added_at=datetime.now(datetime.UTC),
                        added_by=added_by
                    )
                    session.add(auth)
                
                session.commit()
                return True
                
        except Exception as e:
            print(f"Failed to add guardian: {e}")
            return False
    
    def is_guardian_authorized(self, agent_address: str, guardian_address: str) -> bool:
        """
        Check if a guardian is authorized for an agent
        
        Args:
            agent_address: Agent wallet address
            guardian_address: Guardian address
            
        Returns:
            True if authorized
        """
        agent_address = to_checksum_address(agent_address)
        guardian_address = to_checksum_address(guardian_address)
        
        with self.get_session() as session:
            auth = session.query(GuardianAuthorization).filter(
                GuardianAuthorization.agent_address == agent_address,
                GuardianAuthorization.guardian_address == guardian_address,
                GuardianAuthorization.is_active == True
            ).first()
            
            return auth is not None
    
    def get_spending_summary(self, agent_address: str) -> Dict:
        """
        Get comprehensive spending summary for an agent
        
        Args:
            agent_address: Agent wallet address
            
        Returns:
            Spending summary
        """
        agent_address = to_checksum_address(agent_address)
        now = datetime.now(datetime.UTC)
        
        # Get current spending
        current_spent = {
            "hour": self.get_spent_in_period(agent_address, "hour", now),
            "day": self.get_spent_in_period(agent_address, "day", now),
            "week": self.get_spent_in_period(agent_address, "week", now)
        }
        
        # Get limits
        with self.get_session() as session:
            limits = session.query(SpendingLimit).filter(
                SpendingLimit.agent_address == agent_address
            ).first()
            
            if not limits:
                return {"error": "No spending limits set"}
        
        # Calculate remaining
        remaining = {
            "hour": limits.per_hour - current_spent["hour"],
            "day": limits.per_day - current_spent["day"],
            "week": limits.per_week - current_spent["week"]
        }
        
        # Get authorized guardians
        with self.get_session() as session:
            guardians = session.query(GuardianAuthorization).filter(
                GuardianAuthorization.agent_address == agent_address,
                GuardianAuthorization.is_active == True
            ).all()
        
        return {
            "agent_address": agent_address,
            "current_spending": current_spent,
            "remaining_spending": remaining,
            "limits": {
                "per_transaction": limits.per_transaction,
                "per_hour": limits.per_hour,
                "per_day": limits.per_day,
                "per_week": limits.per_week
            },
            "time_lock": {
                "threshold": limits.time_lock_threshold,
                "delay_hours": limits.time_lock_delay_hours
            },
            "authorized_guardians": [g.guardian_address for g in guardians],
            "last_updated": limits.updated_at.isoformat() if limits.updated_at else None
        }


# Global persistent tracker instance
persistent_tracker = PersistentSpendingTracker()
