"""
Persistent Spending Tracker - Database-Backed Security
Fixes the critical vulnerability where spending limits were lost on restart
"""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from eth_utils import to_checksum_address  # type: ignore[attr-defined]
from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from aitbc import get_logger

logger = get_logger(__name__)
Base = declarative_base()

class SpendingRecord(Base):
    """Database model for spending tracking"""
    __tablename__ = 'spending_records'
    id = Column(String, primary_key=True)
    agent_address = Column(String, index=True)
    period_type = Column(String, index=True)
    period_key = Column(String, index=True)
    amount = Column(Float)
    transaction_hash = Column(String)
    timestamp = Column(DateTime, default=datetime.now(UTC))
    __table_args__ = (Index('idx_agent_period', 'agent_address', 'period_type', 'period_key'), Index('idx_timestamp', 'timestamp'))

class SpendingLimit(Base):
    """Database model for spending limits"""
    __tablename__ = 'spending_limits'
    agent_address = Column(String, primary_key=True)
    per_transaction = Column(Float)
    per_hour = Column(Float)
    per_day = Column(Float)
    per_week = Column(Float)
    time_lock_threshold = Column(Float)
    time_lock_delay_hours = Column(Integer)
    updated_at = Column(DateTime, default=datetime.now(UTC))
    updated_by = Column(String)

class GuardianAuthorization(Base):
    """Database model for guardian authorizations"""
    __tablename__ = 'guardian_authorizations'
    id = Column(String, primary_key=True)
    agent_address = Column(String, index=True)
    guardian_address = Column(String, index=True)
    is_active = Column(Boolean, default=True)
    added_at = Column(DateTime, default=datetime.now(UTC))
    added_by = Column(String)

@dataclass
class SpendingCheckResult:
    """Result of spending limit check"""
    allowed: bool
    reason: str
    current_spent: dict[str, float]
    remaining: dict[str, float]
    requires_time_lock: bool
    time_lock_until: datetime | None = None

class PersistentSpendingTracker:
    """
    Database-backed spending tracker that survives restarts
    """

    def __init__(self, database_url: str='sqlite:///spending_tracker.db'):
        self.engine = create_engine(database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        """Get database session"""
        return self.SessionLocal()

    def _get_period_key(self, timestamp: datetime, period: str) -> str:
        """Generate period key for spending tracking"""
        if period == 'hour':
            return timestamp.strftime('%Y-%m-%d-%H')
        elif period == 'day':
            return timestamp.strftime('%Y-%m-%d')
        elif period == 'week':
            week_num = timestamp.isocalendar()[1]
            return f'{timestamp.year}-W{week_num:02d}'
        else:
            raise ValueError(f'Invalid period: {period}')

    def get_spent_in_period(self, agent_address: str, period: str, timestamp: datetime | None = None) -> float:
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
            timestamp = datetime.now(UTC)
        period_key = self._get_period_key(timestamp, period)
        agent_address = to_checksum_address(agent_address)
        with self.get_session() as session:
            total = session.query(SpendingRecord).filter(SpendingRecord.agent_address == agent_address, SpendingRecord.period_type == period, SpendingRecord.period_key == period_key).with_entities(SpendingRecord.amount).all()
            return float(sum(record.amount for record in total if record.amount is not None))

    def record_spending(self, agent_address: str, amount: float, transaction_hash: str, timestamp: datetime | None = None) -> bool:
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
            timestamp = datetime.now(UTC)
        agent_address = to_checksum_address(agent_address)
        try:
            with self.get_session() as session:
                periods = ['hour', 'day', 'week']
                for period in periods:
                    period_key = self._get_period_key(timestamp, period)
                    record = SpendingRecord(id=f'{transaction_hash}_{period}', agent_address=agent_address, period_type=period, period_key=period_key, amount=amount, transaction_hash=transaction_hash, timestamp=timestamp)  # type: ignore[arg-type]
                    session.add(record)
                session.commit()
                return True
        except Exception as e:
            logger.error('Failed to record spending: %s', e)
            return False

    def check_spending_limits(self, agent_address: str, amount: float, timestamp: datetime | None = None) -> SpendingCheckResult:
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
            timestamp = datetime.now(UTC)
        agent_address = to_checksum_address(agent_address)
        with self.get_session() as session:
            limits = session.query(SpendingLimit).filter(SpendingLimit.agent_address == agent_address).first()
            if not limits:
                limits = SpendingLimit(agent_address=agent_address, per_transaction=1000.0, per_hour=5000.0, per_day=20000.0, per_week=100000.0, time_lock_threshold=5000.0, time_lock_delay_hours=24)  # type: ignore[arg-type]
                session.add(limits)
                session.commit()
        current_spent: dict[str, float] = {}
        remaining: dict[str, float] = {}
        per_transaction = limits.per_transaction if limits.per_transaction is not None else 0.0
        per_hour = limits.per_hour if limits.per_hour is not None else 0.0
        per_day = limits.per_day if limits.per_day is not None else 0.0
        per_week = limits.per_week if limits.per_week is not None else 0.0
        time_lock_threshold = limits.time_lock_threshold if limits.time_lock_threshold is not None else 0.0
        if amount > per_transaction:
            return SpendingCheckResult(allowed=False, reason=f'Amount {amount} exceeds per-transaction limit {per_transaction}', current_spent=current_spent, remaining=remaining, requires_time_lock=False)
        spent_hour = self.get_spent_in_period(agent_address, 'hour', timestamp)
        current_spent['hour'] = spent_hour
        remaining['hour'] = per_hour - spent_hour  # type: ignore[operator]
        if spent_hour + amount > per_hour:
            return SpendingCheckResult(allowed=False, reason=f'Hourly spending {spent_hour + amount} would exceed limit {per_hour}', current_spent=current_spent, remaining=remaining, requires_time_lock=False)
        spent_day = self.get_spent_in_period(agent_address, 'day', timestamp)
        current_spent['day'] = spent_day
        remaining['day'] = per_day - spent_day  # type: ignore[operator]
        if spent_day + amount > per_day:
            return SpendingCheckResult(allowed=False, reason=f'Daily spending {spent_day + amount} would exceed limit {per_day}', current_spent=current_spent, remaining=remaining, requires_time_lock=False)
        spent_week = self.get_spent_in_period(agent_address, 'week', timestamp)
        current_spent['week'] = spent_week
        remaining['week'] = per_week - spent_week  # type: ignore[operator]
        if spent_week + amount > per_week:
            return SpendingCheckResult(allowed=False, reason=f'Weekly spending {spent_week + amount} would exceed limit {per_week}', current_spent=current_spent, remaining=remaining, requires_time_lock=False)
        requires_time_lock = amount >= time_lock_threshold
        time_lock_until = None
        if requires_time_lock:
            time_lock_until = timestamp + timedelta(hours=float(limits.time_lock_delay_hours if limits.time_lock_delay_hours is not None else 0))
        return SpendingCheckResult(allowed=True, reason='Spending limits check passed', current_spent=current_spent, remaining=remaining, requires_time_lock=requires_time_lock, time_lock_until=time_lock_until)

    def update_spending_limits(self, agent_address: str, new_limits: dict[str, Any], guardian_address: str) -> bool:
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
        if not self.is_guardian_authorized(agent_address, guardian_address):
            return False
        try:
            with self.get_session() as session:
                limits = session.query(SpendingLimit).filter(SpendingLimit.agent_address == agent_address).first()
                if limits:
                    limits.per_transaction = new_limits.get('per_transaction', limits.per_transaction)
                    limits.per_hour = new_limits.get('per_hour', limits.per_hour)
                    limits.per_day = new_limits.get('per_day', limits.per_day)
                    limits.per_week = new_limits.get('per_week', limits.per_week)
                    limits.time_lock_threshold = new_limits.get('time_lock_threshold', limits.time_lock_threshold)
                    limits.time_lock_delay_hours = new_limits.get('time_lock_delay_hours', limits.time_lock_delay_hours)
                    limits.updated_at = datetime.now(UTC)
                    limits.updated_by = guardian_address
                else:
                    limits = SpendingLimit(agent_address=agent_address, per_transaction=new_limits.get('per_transaction', 1000.0), per_hour=new_limits.get('per_hour', 5000.0), per_day=new_limits.get('per_day', 20000.0), per_week=new_limits.get('per_week', 100000.0), time_lock_threshold=new_limits.get('time_lock_threshold', 5000.0), time_lock_delay_hours=new_limits.get('time_lock_delay_hours', 24), updated_at=datetime.now(UTC), updated_by=guardian_address)
                    session.add(limits)
                session.commit()
                return True
        except Exception as e:
            logger.error('Failed to update spending limits: %s', str(e))
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
                existing = session.query(GuardianAuthorization).filter(GuardianAuthorization.agent_address == agent_address, GuardianAuthorization.guardian_address == guardian_address).first()
                if existing:
                    existing.is_active = True
                    existing.added_at = datetime.now(UTC)
                    existing.added_by = added_by
                else:
                    auth = GuardianAuthorization(id=f'{agent_address}_{guardian_address}', agent_address=agent_address, guardian_address=guardian_address, is_active=True, added_at=datetime.now(UTC), added_by=added_by)
                    session.add(auth)
                session.commit()
                return True
        except Exception as e:
            logger.error('Failed to add guardian: %s', str(e))
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
            auth = session.query(GuardianAuthorization).filter(GuardianAuthorization.agent_address == agent_address, GuardianAuthorization.guardian_address == guardian_address, GuardianAuthorization.is_active == True).first()
            return auth is not None

    def get_spending_summary(self, agent_address: str) -> dict[str, Any]:
        """
        Get comprehensive spending summary for an agent
        
        Args:
            agent_address: Agent wallet address
            
        Returns:
            Spending summary
        """
        agent_address = to_checksum_address(agent_address)
        now = datetime.now(UTC)
        current_spent = {'hour': self.get_spent_in_period(agent_address, 'hour', now), 'day': self.get_spent_in_period(agent_address, 'day', now), 'week': self.get_spent_in_period(agent_address, 'week', now)}
        with self.get_session() as session:
            limits = session.query(SpendingLimit).filter(SpendingLimit.agent_address == agent_address).first()
            if not limits:
                return {'error': 'No spending limits set'}
        per_hour_limit = float(limits.per_hour) if limits.per_hour is not None else 0.0
        per_day_limit = float(limits.per_day) if limits.per_day is not None else 0.0
        per_week_limit = float(limits.per_week) if limits.per_week is not None else 0.0
        remaining = {'hour': per_hour_limit - current_spent['hour'], 'day': per_day_limit - current_spent['day'], 'week': per_week_limit - current_spent['week']}
        with self.get_session() as session:
            guardians = session.query(GuardianAuthorization).filter(GuardianAuthorization.agent_address == agent_address, GuardianAuthorization.is_active == True).all()
        return {'agent_address': agent_address, 'current_spending': current_spent, 'remaining_spending': remaining, 'limits': {'per_transaction': limits.per_transaction, 'per_hour': limits.per_hour, 'per_day': limits.per_day, 'per_week': limits.per_week}, 'time_lock': {'threshold': limits.time_lock_threshold, 'delay_hours': limits.time_lock_delay_hours}, 'authorized_guardians': [g.guardian_address for g in guardians], 'last_updated': limits.updated_at.isoformat() if limits.updated_at else None}
persistent_tracker = PersistentSpendingTracker()
