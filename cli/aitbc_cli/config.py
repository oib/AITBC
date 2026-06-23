"""Configuration module for AITBC CLI"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseAITBCConfig(BaseSettings):
    """Base configuration class"""

    pass


BLOCKCHAIN_RPC_PORT = 8202


class CLIConfig(BaseAITBCConfig):
    """CLI-specific configuration inheriting from shared BaseAITBCConfig"""

    model_config = SettingsConfigDict(
        env_file=[
            str(Path("/etc/aitbc/blockchain.env")),
            str(Path("/etc/aitbc/blockchain-secrets.env")),
            str(Path("/etc/aitbc/node.env")),
        ],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # CLI-specific settings
    app_name: str = Field(default="AITBC CLI", description="CLI application name")
    app_version: str = Field(default="2.1.0", description="CLI version")

    # Service URLs
    exchange_service_url: str = Field(default="http://localhost:8106/api/v1", description="Exchange Service URL")
    gpu_service_url: str = Field(default="http://localhost:8101", description="GPU Service URL")
    marketplace_service_url: str = Field(default="http://localhost:8102", description="Marketplace Service URL")
    trading_service_url: str = Field(default="http://localhost:8104", description="Trading Service URL")
    governance_service_url: str = Field(default="http://localhost:8105", description="Governance Service URL")
    agent_coordinator_url: str = Field(default="http://localhost:8107", description="Agent Coordinator URL")
    edge_api_host: str = Field(default="localhost", description="Edge API host")
    edge_api_port: int = Field(default=8103, description="Edge API port")
    wallet_daemon_url: str = Field(default="http://localhost:8108", description="Wallet daemon URL")
    wallet_url: str = Field(default="http://localhost:8108", description="Wallet daemon URL (alias for compatibility)")
    blockchain_rpc_url: str = Field(default="http://localhost:8202", description="Blockchain RPC URL")
    explorer_api_url: str = Field(default="http://localhost:8100", description="Blockchain Explorer API URL")

    # Chain configuration
    chain_id: str = Field(default="", description="Default chain ID for multichain operations (from CHAIN_ID env var)")
    hub_discovery_url: str | None = Field(
        default=None, description="Hub discovery DNS for cross-node operations (from HUB_DISCOVERY_URL env var)"
    )

    # Authentication
    api_key: str | None = Field(default=None, description="API key for authentication")

    # Request settings
    timeout: int = Field(default=30, description="Request timeout in seconds")

    # Config file path (for backward compatibility)
    config_file: str | None = Field(default=None, description="Path to config file")


def get_config(config_file: str | None = None) -> CLIConfig:
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
                agent_coordinator_url=config_data.get("agent_coordinator_url", "http://localhost:8107"),
                wallet_daemon_url=config_data.get("wallet_url", "http://localhost:8003"),
                api_key=config_data.get("api_key"),
                timeout=config_data.get("timeout", 30),
            )

    # Use shared config system with environment variables
    return CLIConfig()
