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
    coordinator_url: str = "http://127.0.0.1:18000"
    api_key: Optional[str] = None
    config_dir: Path = field(default_factory=lambda: Path.home() / ".aitbc")
    config_file: Optional[str] = None
    
    def __post_init__(self):
        """Initialize configuration"""
        # Load environment variables
        load_dotenv()
        
        # Set default config file if not specified
        if not self.config_file:
            self.config_file = str(self.config_dir / "config.yaml")
        
        # Load config from file if it exists
        self.load_from_file()
        
        # Override with environment variables
        if os.getenv("AITBC_URL"):
            self.coordinator_url = os.getenv("AITBC_URL")
        if os.getenv("AITBC_API_KEY"):
            self.api_key = os.getenv("AITBC_API_KEY")
    
    def load_from_file(self):
        """Load configuration from YAML file"""
        if self.config_file and Path(self.config_file).exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = yaml.safe_load(f) or {}
                    
                self.coordinator_url = data.get('coordinator_url', self.coordinator_url)
                self.api_key = data.get('api_key', self.api_key)
            except Exception as e:
                print(f"Warning: Could not load config file: {e}")
    
    def save_to_file(self):
        """Save configuration to YAML file"""
        if not self.config_file:
            return
            
        # Ensure config directory exists
        Path(self.config_file).parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            'coordinator_url': self.coordinator_url,
            'api_key': self.api_key
        }
        
        with open(self.config_file, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)


def get_config(config_file: Optional[str] = None) -> Config:
    """Get configuration instance"""
    return Config(config_file=config_file)
