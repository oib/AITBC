"""Configuration management for AITBC CLI"""

import os
import yaml
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv


@dataclass
class Config:
    """Configuration object for AITBC CLI"""
    coordinator_url: str = "http://127.0.0.1:8000"
    api_key: Optional[str] = None
    role: Optional[str] = None  # admin, client, miner, etc.
    config_dir: Path = field(default_factory=lambda: Path.home() / ".aitbc")
    config_file: Optional[str] = None
    blockchain_rpc_url: str = "http://127.0.0.1:8006"
    wallet_url: str = "http://127.0.0.1:8002"
    
    def _validate_localhost_urls(self):
        """Validate that all service URLs point to localhost"""
        localhost_prefixes = ["http://localhost:", "http://127.0.0.1:", "https://localhost:", "https://127.0.0.1:"]
        
        urls_to_check = [
            ("coordinator_url", self.coordinator_url),
            ("blockchain_rpc_url", self.blockchain_rpc_url),
            ("wallet_url", self.wallet_url)
        ]
        
        for url_name, url in urls_to_check:
            if not any(url.startswith(prefix) for prefix in localhost_prefixes):
                # Force to localhost if not already
                if url_name == "coordinator_url":
                    self.coordinator_url = "http://localhost:8000"
                elif url_name == "blockchain_rpc_url":
                    self.blockchain_rpc_url = "http://localhost:8006"
                elif url_name == "wallet_url":
                    self.wallet_url = "http://localhost:8002"
    
    def __post_init__(self):
        """Initialize configuration"""
        # Load environment variables
        load_dotenv()
        
        # Set default config file based on role if not specified
        if not self.config_file:
            if self.role:
                self.config_file = str(self.config_dir / f"{self.role}-config.yaml")
            else:
                self.config_file = str(self.config_dir / "config.yaml")
        
        # Load config from file if it exists
        self.load_from_file()
        
        # Override with environment variables
        if os.getenv("AITBC_URL"):
            self.coordinator_url = os.getenv("AITBC_URL")
        if os.getenv("AITBC_API_KEY"):
            self.api_key = os.getenv("AITBC_API_KEY")
        if os.getenv("AITBC_ROLE"):
            self.role = os.getenv("AITBC_ROLE")
        if os.getenv("AITBC_BLOCKCHAIN_RPC_URL"):
            self.blockchain_rpc_url = os.getenv("AITBC_BLOCKCHAIN_RPC_URL")
        if os.getenv("AITBC_WALLET_URL"):
            self.wallet_url = os.getenv("AITBC_WALLET_URL")
        
        # Validate and enforce localhost URLs
        self._validate_localhost_urls()
    
    def load_from_file(self):
        """Load configuration from YAML file"""
        if self.config_file and Path(self.config_file).exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = yaml.safe_load(f) or {}
                    
                self.coordinator_url = data.get('coordinator_url', self.coordinator_url)
                self.api_key = data.get('api_key', self.api_key)
                self.role = data.get('role', self.role)
                self.blockchain_rpc_url = data.get('blockchain_rpc_url', self.blockchain_rpc_url)
                self.wallet_url = data.get('wallet_url', self.wallet_url)
            except Exception as e:
                print(f"Warning: Could not load config file: {e}")
        
        # Validate and enforce localhost URLs after file loading
        self._validate_localhost_urls()
    
    def save_to_file(self):
        """Save configuration to YAML file"""
        if not self.config_file:
            return
            
        # Ensure config directory exists
        Path(self.config_file).parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            'coordinator_url': self.coordinator_url,
            'api_key': self.api_key,
            'blockchain_rpc_url': self.blockchain_rpc_url,
            'wallet_url': self.wallet_url
        }
        
        if self.role:
            data['role'] = self.role
        
        with open(self.config_file, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)


def get_config(config_file: Optional[str] = None, role: Optional[str] = None) -> Config:
    """Get configuration instance with optional role"""
    return Config(config_file=config_file, role=role)
