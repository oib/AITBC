"""PostgreSQL database module for Coordinator API"""

from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Generator, Optional, Dict, Any, List
import json
import logging
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger(__name__)

from .config_pg import settings

# SQLAlchemy setup for complex queries
engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_recycle=300,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Direct PostgreSQL connection for performance
def get_pg_connection():
    """Get direct PostgreSQL connection"""
    # Parse database URL from settings
    from urllib.parse import urlparse
    parsed = urlparse(settings.database_url)
    
    return psycopg2.connect(
        host=parsed.hostname or "localhost",
        database=parsed.path[1:] if parsed.path else "aitbc_coordinator",
        user=parsed.username or "aitbc_user",
        password=parsed.password or "aitbc_password",
        port=parsed.port or 5432,
        cursor_factory=RealDictCursor
    )

def get_db() -> Generator[Session, None, None]:
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class PostgreSQLAdapter:
    """PostgreSQL adapter for high-performance operations"""
    
    def __init__(self):
        self.connection = get_pg_connection()
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """Execute a query and return results"""
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()
    
    def execute_update(self, query: str, params: tuple = None) -> int:
        """Execute an update/insert/delete query"""
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            self.connection.commit()
            return cursor.rowcount
    
    def execute_batch(self, query: str, params_list: List[tuple]) -> int:
        """Execute batch insert/update"""
        with self.connection.cursor() as cursor:
            cursor.executemany(query, params_list)
            self.connection.commit()
            return cursor.rowcount
    
    def get_job_by_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job by ID"""
        query = "SELECT * FROM job WHERE id = %s"
        results = self.execute_query(query, (job_id,))
        return results[0] if results else None
    
    def get_available_miners(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get available miners"""
        if region:
            query = """
                SELECT * FROM miner 
                WHERE status = 'active' 
                AND inflight < concurrency
                AND (region = %s OR region IS NULL)
                ORDER BY last_heartbeat DESC
            """
            return self.execute_query(query, (region,))
        else:
            query = """
                SELECT * FROM miner 
                WHERE status = 'active' 
                AND inflight < concurrency
                ORDER BY last_heartbeat DESC
            """
            return self.execute_query(query)
    
    def get_pending_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get pending jobs"""
        query = """
            SELECT * FROM job 
            WHERE state = 'pending' 
            AND expires_at > NOW()
            ORDER BY requested_at ASC
            LIMIT %s
        """
        return self.execute_query(query, (limit,))
    
    def update_job_state(self, job_id: str, state: str, **kwargs) -> bool:
        """Update job state"""
        set_clauses = ["state = %s"]
        params = [state, job_id]
        
        for key, value in kwargs.items():
            set_clauses.append(f"{key} = %s")
            params.insert(-1, value)
        
        query = f"""
            UPDATE job 
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE id = %s
        """
        
        return self.execute_update(query, params) > 0
    
    def get_marketplace_offers(self, status: str = "active") -> List[Dict[str, Any]]:
        """Get marketplace offers"""
        query = """
            SELECT * FROM marketplaceoffer 
            WHERE status = %s
            ORDER BY price ASC, created_at DESC
        """
        return self.execute_query(query, (status,))
    
    def get_user_wallets(self, user_id: str) -> List[Dict[str, Any]]:
        """Get user wallets"""
        query = """
            SELECT * FROM wallet 
            WHERE user_id = %s
            ORDER BY created_at DESC
        """
        return self.execute_query(query, (user_id,))
    
    def create_job(self, job_data: Dict[str, Any]) -> str:
        """Create a new job"""
        query = """
            INSERT INTO job (id, client_id, state, payload, constraints, 
                           ttl_seconds, requested_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        result = self.execute_query(query, (
            job_data['id'],
            job_data['client_id'],
            job_data['state'],
            json.dumps(job_data['payload']),
            json.dumps(job_data.get('constraints', {})),
            job_data['ttl_seconds'],
            job_data['requested_at'],
            job_data['expires_at']
        ))
        return result[0]['id']
    
    def cleanup_expired_jobs(self) -> int:
        """Clean up expired jobs"""
        query = """
            UPDATE job 
            SET state = 'expired', updated_at = NOW()
            WHERE state = 'pending' 
            AND expires_at < NOW()
        """
        return self.execute_update(query)
    
    def get_miner_stats(self, miner_id: str) -> Optional[Dict[str, Any]]:
        """Get miner statistics"""
        query = """
            SELECT 
                COUNT(*) as total_jobs,
                COUNT(CASE WHEN state = 'completed' THEN 1 END) as completed_jobs,
                COUNT(CASE WHEN state = 'failed' THEN 1 END) as failed_jobs,
                AVG(CASE WHEN state = 'completed' THEN EXTRACT(EPOCH FROM (updated_at - requested_at)) END) as avg_duration_seconds
            FROM job 
            WHERE assigned_miner_id = %s
        """
        results = self.execute_query(query, (miner_id,))
        return results[0] if results else None
    
    def close(self):
        """Close the connection"""
        if self.connection:
            self.connection.close()

# Global adapter instance (lazy initialization)
db_adapter: Optional[PostgreSQLAdapter] = None


def get_db_adapter() -> PostgreSQLAdapter:
    """Get or create database adapter instance"""
    global db_adapter
    if db_adapter is None:
        db_adapter = PostgreSQLAdapter()
    return db_adapter

# Database initialization
def init_db():
    """Initialize database tables"""
    # Import models here to avoid circular imports
    from .models import Base
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    logger.info("PostgreSQL database initialized successfully")

# Health check
def check_db_health() -> Dict[str, Any]:
    """Check database health"""
    try:
        adapter = get_db_adapter()
        result = adapter.execute_query("SELECT 1 as health_check")
        return {
            "status": "healthy",
            "database": "postgresql",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
