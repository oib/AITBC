"""Configuration module for AITBC CLI"""

import os
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aitbc.config.hub import hub_agent_url, hub_coordinator_url, hub_exchange_url


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
    exchange_service_url: str = Field(
        default="",
        description="Exchange Service URL. Hub-only locally; empty means resolve from HUB_DISCOVERY_URL / HUB_EXCHANGE_URL.",
    )
    gpu_service_url: str = Field(default="http://localhost:8101", description="GPU Service URL")
    marketplace_service_url: str = Field(default="http://localhost:8102", description="Marketplace Service URL")
    coordinator_api_url: str = Field(default="", description="Coordinator API URL")
    trading_service_url: str = Field(default="http://localhost:8104", description="Trading Service URL")
    governance_service_url: str = Field(default="http://localhost:8105", description="Governance Service URL")
    agent_coordinator_url: str = Field(
        default="",
        description="Agent Coordinator URL. Hub-only locally; empty means resolve from HUB_DISCOVERY_URL / HUB_AGENT_URL.",
    )
    edge_api_host: str = Field(default="localhost", description="Edge API host")
    edge_api_port: int = Field(default=8111, description="Edge API port")
    wallet_daemon_url: str = Field(default="http://localhost:8108", description="Wallet daemon URL")
    wallet_url: str = Field(default="http://localhost:8108", description="Wallet daemon URL (alias for compatibility)")
    blockchain_rpc_url: str = Field(default="http://localhost:8202", description="Blockchain RPC URL")
    explorer_api_url: str = Field(default="http://localhost:8100", description="Blockchain Explorer API URL")

    # Chain configuration
    chain_id: str = Field(default="", description="Default chain ID for multichain operations (from CHAIN_ID env var)")
    # The wallet holding the genesis allocation — the account AIT transfers are sent *from*.
    # This is not the block proposer: the proposer is a signing identity and holds no funds
    # (see docs/getting-started/node/blockchain-setup.md). Matches the meaning
    # GENESIS_WALLET_ADDRESS already has in bridge-monitor and blockchain-node escrow.
    genesis_wallet_address: str = Field(
        default="ait1db5247d03ca2e40f3995a583b2c097ab703efd4d",
        description="Wallet holding the genesis allocation (from GENESIS_WALLET_ADDRESS env var)",
    )
    # SecretStr so it cannot land in a log line or traceback via repr.
    genesis_wallet_private_key: SecretStr | None = Field(
        default=None,
        description="Signing key for genesis_wallet_address (from GENESIS_WALLET_PRIVATE_KEY env var)",
    )
    hub_discovery_url: str | None = Field(
        default=None, description="Hub discovery DNS for cross-node operations (from HUB_DISCOVERY_URL env var)"
    )

    # Authentication
    api_key: str | None = Field(default=None, description="API key for authentication")

    # Request settings
    timeout: int = Field(default=30, description="Request timeout in seconds")

    # Config file path (for backward compatibility)
    config_file: str | None = Field(default=None, description="Path to config file")

    @model_validator(mode="after")
    def _resolve_hub_only_urls(self) -> "CLIConfig":
        """Fill hub-only service URLs from the env files when the caller left them empty.

        ``localhost:8106`` / ``:8107`` are not valid defaults off a hub (V23-92).
        The host comes from ``HUB_DISCOVERY_URL`` (or the explicit
        ``HUB_AGENT_URL`` / ``HUB_EXCHANGE_URL``) in process env or
        ``/etc/aitbc/{blockchain,node}.env``.
        """
        if not self.coordinator_api_url:
            resolved = hub_coordinator_url()
            if resolved:
                self.coordinator_api_url = resolved
        if not self.agent_coordinator_url:
            resolved = hub_agent_url()
            if resolved:
                self.agent_coordinator_url = resolved
        if not self.exchange_service_url:
            resolved = hub_exchange_url()
            if resolved:
                self.exchange_service_url = resolved
            else:
                # Fallback to the local blockchain RPC so cross-chain CLI
                # commands can reach the in-process cross-chain endpoints.
                rpc = (self.blockchain_rpc_url or "http://localhost:8202").rstrip("/")
                if not rpc.endswith("/rpc"):
                    rpc = f"{rpc}/rpc"
                self.exchange_service_url = rpc
        return self

    @property
    def coordinator_url(self) -> str:
        """Deprecated alias for coordinator_api_url"""
        return self.coordinator_api_url


def _parse_env_file(env_path: Path) -> dict[str, str]:
    """Parse a simple KEY=VALUE env file, ignoring comments and blank lines."""
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(("#", ";")):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            values[key] = value
    return values


def _resolve_api_key(config_data: dict[str, Any]) -> str | None:
    """Resolve the API key from config, env, and credential files."""
    if config_data.get("api_key"):
        return str(config_data["api_key"])

    if os.environ.get("AITBC_API_KEY"):
        return os.environ["AITBC_API_KEY"]

    env_files = [
        Path.home() / ".aitbc" / "credentials.env",
        Path("/etc/aitbc/aitbc-cli.env"),
        Path("/etc/aitbc/aitbc-coordinator-api.env"),
    ]
    for env_path in env_files:
        parsed = _parse_env_file(env_path)
        if parsed.get("AITBC_API_KEY"):
            return parsed["AITBC_API_KEY"]
        miner_keys = parsed.get("MINER_API_KEYS", "")
        if miner_keys:
            miner_keys = miner_keys.strip()
            if miner_keys.startswith("["):
                try:
                    import json

                    keys = json.loads(miner_keys)
                    if keys:
                        return str(keys[0])
                except (json.JSONDecodeError, IndexError):
                    pass
            elif "," in miner_keys:
                return miner_keys.split(",")[0].strip()
            else:
                return miner_keys

    return None


def _load_config_file(config_path: Path) -> dict[str, Any]:
    """Load a YAML/JSON config file and normalize legacy aliases."""
    import yaml

    with open(config_path) as f:
        config_data = yaml.safe_load(f) or {}

    # Legacy alias: "coordinator_url" maps to the job coordinator API.
    if "coordinator_url" in config_data and "coordinator_api_url" not in config_data:
        config_data["coordinator_api_url"] = config_data.pop("coordinator_url")

    return config_data


def get_config(config_file: str | None = None) -> CLIConfig:
    """Load CLI configuration from shared config system"""
    # Determine the config file to load. If not explicitly provided, look for
    # the repository/working-directory .aitbc.yaml.
    if config_file:
        config_path = Path(config_file)
    else:
        config_path = Path.cwd() / ".aitbc.yaml"

    if config_path.exists():
        config_data = _load_config_file(config_path)

        # Override with config file values
        api_key = _resolve_api_key(config_data)
        return CLIConfig(
            coordinator_api_url=config_data.get("coordinator_api_url", ""),
            agent_coordinator_url=config_data.get("agent_coordinator_url", ""),
            wallet_daemon_url=config_data.get("wallet_url", "http://localhost:8108"),
            api_key=api_key,
            timeout=config_data.get("timeout", 30),
        )

    # Use shared config system with environment variables
    return CLIConfig()
