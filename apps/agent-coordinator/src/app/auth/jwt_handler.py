"""
JWT Authentication Handler for AITBC Agent Coordinator
Implements JWT token generation, validation, and management
"""

import jwt
import bcrypt
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import secrets
import logging

logger = logging.getLogger(__name__)

class JWTHandler:
    """JWT token management and validation"""
    
    def __init__(self, secret_key: str = None):
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.algorithm = "HS256"
        self.token_expiry = timedelta(hours=24)
        self.refresh_expiry = timedelta(days=7)
        
    def generate_token(self, payload: Dict[str, Any], expires_delta: timedelta = None) -> Dict[str, Any]:
        """Generate JWT token with specified payload"""
        try:
            if expires_delta:
                expire = datetime.utcnow() + expires_delta
            else:
                expire = datetime.utcnow() + self.token_expiry
            
            # Add standard claims
            token_payload = {
                **payload,
                "exp": expire,
                "iat": datetime.utcnow(),
                "type": "access"
            }
            
            # Generate token
            token = jwt.encode(token_payload, self.secret_key, algorithm=self.algorithm)
            
            return {
                "status": "success",
                "token": token,
                "expires_at": expire.isoformat(),
                "token_type": "Bearer"
            }
            
        except Exception as e:
            logger.error(f"Error generating JWT token: {e}")
            return {"status": "error", "message": str(e)}
    
    def generate_refresh_token(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Generate refresh token for token renewal"""
        try:
            expire = datetime.utcnow() + self.refresh_expiry
            
            token_payload = {
                **payload,
                "exp": expire,
                "iat": datetime.utcnow(),
                "type": "refresh"
            }
            
            token = jwt.encode(token_payload, self.secret_key, algorithm=self.algorithm)
            
            return {
                "status": "success",
                "refresh_token": token,
                "expires_at": expire.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating refresh token: {e}")
            return {"status": "error", "message": str(e)}
    
    def validate_token(self, token: str) -> Dict[str, Any]:
        """Validate JWT token and return payload"""
        try:
            # Decode and validate token
            payload = jwt.decode(
                token, 
                self.secret_key, 
                algorithms=[self.algorithm],
                options={"verify_exp": True}
            )
            
            return {
                "status": "success",
                "valid": True,
                "payload": payload
            }
            
        except jwt.ExpiredSignatureError:
            return {
                "status": "error",
                "valid": False,
                "message": "Token has expired"
            }
        except jwt.InvalidTokenError as e:
            return {
                "status": "error",
                "valid": False,
                "message": f"Invalid token: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Error validating token: {e}")
            return {
                "status": "error",
                "valid": False,
                "message": f"Token validation error: {str(e)}"
            }
    
    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Generate new access token from refresh token"""
        try:
            # Validate refresh token
            validation = self.validate_token(refresh_token)
            
            if not validation["valid"] or validation["payload"].get("type") != "refresh":
                return {
                    "status": "error",
                    "message": "Invalid or expired refresh token"
                }
            
            # Extract user info from refresh token
            payload = validation["payload"]
            user_payload = {
                "user_id": payload.get("user_id"),
                "username": payload.get("username"),
                "role": payload.get("role"),
                "permissions": payload.get("permissions", [])
            }
            
            # Generate new access token
            return self.generate_token(user_payload)
            
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            return {"status": "error", "message": str(e)}
    
    def decode_token_without_validation(self, token: str) -> Dict[str, Any]:
        """Decode token without expiration validation (for debugging)"""
        try:
            payload = jwt.decode(
                token, 
                self.secret_key, 
                algorithms=[self.algorithm],
                options={"verify_exp": False}
            )
            
            return {
                "status": "success",
                "payload": payload
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error decoding token: {str(e)}"
            }

class PasswordManager:
    """Password hashing and verification using bcrypt"""
    
    @staticmethod
    def hash_password(password: str) -> Dict[str, Any]:
        """Hash password using bcrypt"""
        try:
            # Generate salt and hash password
            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
            
            return {
                "status": "success",
                "hashed_password": hashed.decode('utf-8'),
                "salt": salt.decode('utf-8')
            }
            
        except Exception as e:
            logger.error(f"Error hashing password: {e}")
            return {"status": "error", "message": str(e)}
    
    @staticmethod
    def verify_password(password: str, hashed_password: str) -> Dict[str, Any]:
        """Verify password against hashed password"""
        try:
            # Check password
            hashed_bytes = hashed_password.encode('utf-8')
            password_bytes = password.encode('utf-8')
            
            is_valid = bcrypt.checkpw(password_bytes, hashed_bytes)
            
            return {
                "status": "success",
                "valid": is_valid
            }
            
        except Exception as e:
            logger.error(f"Error verifying password: {e}")
            return {"status": "error", "message": str(e)}

class APIKeyManager:
    """API key generation and management"""
    
    def __init__(self):
        self.api_keys = {}  # In production, use secure storage
        
    def generate_api_key(self, user_id: str, permissions: List[str] = None) -> Dict[str, Any]:
        """Generate new API key for user"""
        try:
            # Generate secure API key
            api_key = secrets.token_urlsafe(32)
            
            # Store key metadata
            key_data = {
                "user_id": user_id,
                "permissions": permissions or [],
                "created_at": datetime.utcnow().isoformat(),
                "last_used": None,
                "usage_count": 0
            }
            
            self.api_keys[api_key] = key_data
            
            return {
                "status": "success",
                "api_key": api_key,
                "permissions": permissions or [],
                "created_at": key_data["created_at"]
            }
            
        except Exception as e:
            logger.error(f"Error generating API key: {e}")
            return {"status": "error", "message": str(e)}
    
    def validate_api_key(self, api_key: str) -> Dict[str, Any]:
        """Validate API key and return user info"""
        try:
            if api_key not in self.api_keys:
                return {
                    "status": "error",
                    "valid": False,
                    "message": "Invalid API key"
                }
            
            key_data = self.api_keys[api_key]
            
            # Update usage statistics
            key_data["last_used"] = datetime.utcnow().isoformat()
            key_data["usage_count"] += 1
            
            return {
                "status": "success",
                "valid": True,
                "user_id": key_data["user_id"],
                "permissions": key_data["permissions"]
            }
            
        except Exception as e:
            logger.error(f"Error validating API key: {e}")
            return {"status": "error", "message": str(e)}
    
    def revoke_api_key(self, api_key: str) -> Dict[str, Any]:
        """Revoke API key"""
        try:
            if api_key in self.api_keys:
                del self.api_keys[api_key]
                return {"status": "success", "message": "API key revoked"}
            else:
                return {"status": "error", "message": "API key not found"}
                
        except Exception as e:
            logger.error(f"Error revoking API key: {e}")
            return {"status": "error", "message": str(e)}

# Global instances
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

jwt_secret = os.getenv("JWT_SECRET", "production-jwt-secret-change-me")
jwt_handler = JWTHandler(jwt_secret)
password_manager = PasswordManager()
api_key_manager = APIKeyManager()
