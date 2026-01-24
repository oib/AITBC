"""Coordinator API configuration with PostgreSQL support"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/v1"
    debug: bool = False
    
    # Database Configuration
    database_url: str = "postgresql://aitbc_user:aitbc_password@localhost:5432/aitbc_coordinator"
    
    # JWT Configuration
    jwt_secret: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    
    # Job Configuration
    default_job_ttl_seconds: int = 3600  # 1 hour
    max_job_ttl_seconds: int = 86400  # 24 hours
    job_cleanup_interval_seconds: int = 300  # 5 minutes
    
    # Miner Configuration
    miner_heartbeat_timeout_seconds: int = 120  # 2 minutes
    miner_max_inflight: int = 10
    
    # Marketplace Configuration
    marketplace_offer_ttl_seconds: int = 3600  # 1 hour
    
    # Wallet Configuration
    wallet_rpc_url: str = "http://localhost:9080"
    
    # CORS Configuration
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "https://aitbc.bubuit.net",
        "https://aitbc.bubuit.net:8080"
    ]
    
    # Logging Configuration
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Create global settings instance
settings = Settings()
