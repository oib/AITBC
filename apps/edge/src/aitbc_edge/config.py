"""Configuration for Edge API Service"""

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Edge API settings"""

    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8111
    api_prefix: str = "/v1"

    # Database settings
    database_url: str = "postgresql+asyncpg://aitbc_edge:password@localhost:5432/aitbc_edge"

    # Blockchain node RPC settings
    blockchain_rpc_host: str = "localhost"
    blockchain_rpc_port: int = 8202

    # GPU service settings
    gpu_service_host: str = "localhost"
    gpu_service_port: int = 8101

    # JWT settings
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24

    # CORS settings
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
