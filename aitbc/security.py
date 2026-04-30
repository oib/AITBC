"""
Security utilities for AITBC
Provides token generation, session management, API key management, and secret management
"""

import os
import secrets
import hashlib
import time
import json
from typing import Optional, Dict, Any
from datetime import datetime, UTC, timedelta
from cryptography.fernet import Fernet


def generate_token(length: int = 32, prefix: str = "") -> str:
    """Generate a secure random token"""
    token = secrets.token_urlsafe(length)
    return f"{prefix}{token}" if prefix else token


def generate_api_key(prefix: str = "aitbc") -> str:
    """Generate a secure API key with prefix"""
    random_part = secrets.token_urlsafe(32)
    return f"{prefix}_{random_part}"


def validate_token_format(token: str, min_length: int = 16) -> bool:
    """Validate token format"""
    return bool(token) and len(token) >= min_length and all(c.isalnum() or c in '-_' for c in token)


def validate_api_key(api_key: str, prefix: str = "aitbc") -> bool:
    """Validate API key format"""
    if not api_key or not api_key.startswith(f"{prefix}_"):
        return False
    token_part = api_key[len(prefix)+1:]
    return validate_token_format(token_part)


class SessionManager:
    """Simple in-memory session manager"""
    
    def __init__(self, session_timeout: int = 3600):
        """Initialize session manager with timeout in seconds"""
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.session_timeout = session_timeout
    
    def create_session(self, user_id: str, data: Optional[Dict[str, Any]] = None) -> str:
        """Create a new session"""
        session_id = generate_token()
        self.sessions[session_id] = {
            "user_id": user_id,
            "data": data or {},
            "created_at": time.time(),
            "expires_at": time.time() + self.session_timeout
        }
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data"""
        session = self.sessions.get(session_id)
        if not session:
            return None
        
        # Check if session expired
        if time.time() > session["expires_at"]:
            del self.sessions[session_id]
            return None
        
        return session
    
    def update_session(self, session_id: str, data: Dict[str, Any]) -> bool:
        """Update session data"""
        session = self.get_session(session_id)
        if not session:
            return False
        
        session["data"].update(data)
        return True
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False
    
    def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions"""
        current_time = time.time()
        expired_keys = [
            key for key, session in self.sessions.items()
            if current_time > session["expires_at"]
        ]
        
        for key in expired_keys:
            del self.sessions[key]
        
        return len(expired_keys)


class APIKeyManager:
    """API key management with storage"""
    
    def __init__(self, storage_path: Optional[str] = None):
        """Initialize API key manager"""
        self.storage_path = storage_path
        self.keys: Dict[str, Dict[str, Any]] = {}
        
        if storage_path:
            self._load_keys()
    
    def create_api_key(self, user_id: str, scopes: Optional[list[str]] = None, name: Optional[str] = None) -> str:
        """Create a new API key"""
        api_key = generate_api_key()
        self.keys[api_key] = {
            "user_id": user_id,
            "scopes": scopes or ["read"],
            "name": name,
            "created_at": datetime.now(datetime.UTC).isoformat(),
            "last_used": None
        }
        
        if self.storage_path:
            self._save_keys()
        
        return api_key
    
    def validate_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Validate API key and return key data"""
        key_data = self.keys.get(api_key)
        if not key_data:
            return None
        
        # Update last used
        key_data["last_used"] = datetime.now(datetime.UTC).isoformat()
        if self.storage_path:
            self._save_keys()
        
        return key_data
    
    def revoke_api_key(self, api_key: str) -> bool:
        """Revoke an API key"""
        if api_key in self.keys:
            del self.keys[api_key]
            if self.storage_path:
                self._save_keys()
            return True
        return False
    
    def list_user_keys(self, user_id: str) -> list[str]:
        """List all API keys for a user"""
        return [
            key for key, data in self.items()
            if data["user_id"] == user_id
        ]
    
    def _load_keys(self):
        """Load keys from storage"""
        if self.storage_path and os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    self.keys = json.load(f)
            except Exception:
                self.keys = {}
    
    def _save_keys(self):
        """Save keys to storage"""
        if self.storage_path:
            try:
                with open(self.storage_path, 'w') as f:
                    json.dump(self.keys, f)
            except Exception:
                pass
    
    def items(self):
        """Return key items"""
        return self.keys.items()


def generate_secure_random_string(length: int = 32) -> str:
    """Generate a cryptographically secure random string"""
    return secrets.token_urlsafe(length)


def generate_secure_random_int(min_val: int = 0, max_val: int = 2**32) -> int:
    """Generate a cryptographically secure random integer"""
    return secrets.randbelow(max_val - min_val) + min_val


class SecretManager:
    """Simple secret management with encryption"""
    
    def __init__(self, encryption_key: Optional[str] = None):
        """Initialize secret manager"""
        if encryption_key:
            self.fernet = Fernet(encryption_key)
        else:
            # Generate a new key if none provided
            self.fernet = Fernet(Fernet.generate_key())
        
        self.secrets: Dict[str, str] = {}
    
    def set_secret(self, key: str, value: str) -> None:
        """Store an encrypted secret"""
        encrypted = self.fernet.encrypt(value.encode('utf-8'))
        self.secrets[key] = encrypted.decode('utf-8')
    
    def get_secret(self, key: str) -> Optional[str]:
        """Retrieve and decrypt a secret"""
        encrypted = self.secrets.get(key)
        if not encrypted:
            return None
        
        try:
            decrypted = self.fernet.decrypt(encrypted.encode('utf-8'))
            return decrypted.decode('utf-8')
        except Exception:
            return None
    
    def delete_secret(self, key: str) -> bool:
        """Delete a secret"""
        if key in self.secrets:
            del self.secrets[key]
            return True
        return False
    
    def list_secrets(self) -> list[str]:
        """List all secret keys"""
        return list(self.secrets.keys())
    
    def get_encryption_key(self) -> str:
        """Get the encryption key (for backup purposes)"""
        return self.fernet._signing_key.decode('utf-8')


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """Hash a password with salt"""
    if salt is None:
        salt = secrets.token_hex(16)
    
    # Use PBKDF2 for password hashing
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    import base64
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt.encode('utf-8'),
        iterations=100000,
    )
    hashed = kdf.derive(password.encode('utf-8'))
    return base64.b64encode(hashed).decode('utf-8'), salt


def verify_password(password: str, hashed_password: str, salt: str) -> bool:
    """Verify a password against a hash"""
    new_hash, _ = hash_password(password, salt)
    return new_hash == hashed_password


def generate_nonce(length: int = 16) -> str:
    """Generate a nonce for cryptographic operations"""
    return secrets.token_hex(length)


def generate_hmac(data: str, secret: str) -> str:
    """Generate HMAC-SHA256 signature"""
    import hmac
    return hmac.new(
        secret.encode('utf-8'),
        data.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()


def verify_hmac(data: str, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature"""
    computed = generate_hmac(data, secret)
    return secrets.compare_digest(computed, signature)
