"""Configuration module for AITBC CLI"""

import os
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from aitbc.config import BaseAITBCConfig
from aitbc.constants import BLOCKCHAIN_RPC_PORT, BLOCKCHAIN_P2P_PORT


class CLIConfig(BaseAITBCConfig):
    """CLI-specific configuration inheriting from shared BaseAITBCConfig"""
    
    model_config = SettingsConfigDict(
        env_file=str(Path("/etc/aitbc/.env")),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # CLI-specific settings
    app_name: str = Field(default="AITBC CLI", description="CLI application name")
    app_version: str = Field(default="2.1.0", description="CLI version")
    
    # Service URLs
    coordinator_url: str = Field(default="http://localhost:8000", description="Coordinator API URL")
    wallet_daemon_url: str = Field(default="http://localhost:8003", description="Wallet daemon URL")
    wallet_url: str = Field(default="http://localhost:8003", description="Wallet daemon URL (alias for compatibility)")
    blockchain_rpc_url: str = Field(default=f"http://localhost:{BLOCKCHAIN_RPC_PORT}", description="Blockchain RPC URL")
    
    # Chain configuration
    chain_id: str = Field(default="ait-mainnet", description="Default chain ID for multichain operations")
    
    # Authentication
    api_key: Optional[str] = Field(default=None, description="API key for authentication")
    
    # Request settings
    timeout: int = Field(default=30, description="Request timeout in seconds")
    
    # Config file path (for backward compatibility)
    config_file: Optional[str] = Field(default=None, description="Path to config file")


def get_config(config_file: Optional[str] = None) -> CLIConfig:
    """Load CLI configuration from shared config system"""
    # For backward compatibility, allow config_file override
    if config_file:
        config_path = Path(config_file)
        if config_path.exists():
            import yaml
            with open(config_path) as f:
                config_data = yaml.safe_load(f) or {}
            
            # Override with config file values
            return CLIConfig(
                coordinator_url=config_data.get("coordinator_url", "http://localhost:8000"),
                wallet_daemon_url=config_data.get("wallet_url", "http://localhost:8003"),
                api_key=config_data.get("api_key"),
                timeout=config_data.get("timeout", 30)
            )
    
    # Use shared config system with environment variables
    return CLIConfig()

