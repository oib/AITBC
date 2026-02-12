"""Authentication and credential management for AITBC CLI"""

import keyring
import os
from typing import Optional, Dict
from ..utils import success, error, warning


class AuthManager:
    """Manages authentication credentials using secure keyring storage"""
    
    SERVICE_NAME = "aitbc-cli"
    
    def __init__(self):
        self.keyring = keyring.get_keyring()
    
    def store_credential(self, name: str, api_key: str, environment: str = "default"):
        """Store an API key securely"""
        try:
            key = f"{environment}_{name}"
            self.keyring.set_password(self.SERVICE_NAME, key, api_key)
            success(f"Credential '{name}' stored for environment '{environment}'")
        except Exception as e:
            error(f"Failed to store credential: {e}")
    
    def get_credential(self, name: str, environment: str = "default") -> Optional[str]:
        """Retrieve an API key"""
        try:
            key = f"{environment}_{name}"
            return self.keyring.get_password(self.SERVICE_NAME, key)
        except Exception as e:
            warning(f"Failed to retrieve credential: {e}")
            return None
    
    def delete_credential(self, name: str, environment: str = "default"):
        """Delete an API key"""
        try:
            key = f"{environment}_{name}"
            self.keyring.delete_password(self.SERVICE_NAME, key)
            success(f"Credential '{name}' deleted for environment '{environment}'")
        except Exception as e:
            error(f"Failed to delete credential: {e}")
    
    def list_credentials(self, environment: str = None) -> Dict[str, str]:
        """List all stored credentials (without showing the actual keys)"""
        # Note: keyring doesn't provide a direct way to list all keys
        # This is a simplified version that checks for common credential names
        credentials = []
        envs = [environment] if environment else ["default", "dev", "staging", "prod"]
        names = ["client", "miner", "admin"]
        
        for env in envs:
            for name in names:
                key = f"{env}_{name}"
                if self.get_credential(name, env):
                    credentials.append(f"{name}@{env}")
        
        return credentials
    
    def store_env_credential(self, name: str):
        """Store credential from environment variable"""
        env_var = f"{name.upper()}_API_KEY"
        api_key = os.getenv(env_var)
        
        if not api_key:
            error(f"Environment variable {env_var} not set")
            return False
        
        self.store_credential(name, api_key)
        return True
