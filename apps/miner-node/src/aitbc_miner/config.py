from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MinerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    node_id: str = "node-dev-1"
    coordinator_base_url: str = "http://127.0.0.1:8011/v1"
    auth_token: str = "REDACTED_MINER_KEY"
    region: Optional[str] = None

    workspace_root: Path = Field(default=Path("/var/lib/aitbc/miner/jobs"))
    cache_root: Path = Field(default=Path("/var/lib/aitbc/miner/cache"))

    heartbeat_interval_seconds: int = 15
    heartbeat_jitter_pct: int = 10
    heartbeat_timeout_seconds: int = 60

    poll_interval_seconds: int = 3
    max_backoff_seconds: int = 60

    max_concurrent_cpu: int = 1
    max_concurrent_gpu: int = 1

    enable_cli_runner: bool = True
    enable_python_runner: bool = True

    allowlist_dir: Path = Field(default=Path("/etc/aitbc/miner/allowlist.d"))

    log_level: str = "INFO"
    log_path: Optional[Path] = None


settings = MinerSettings()
