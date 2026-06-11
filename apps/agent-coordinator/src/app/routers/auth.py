# mypy: ignore-errors
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit

from ..auth.jwt_handler import api_key_manager, jwt_handler
from ..auth.middleware import get_current_user
from ..auth.permissions import Permission, Role, permission_manager

logger = get_logger(__name__)
router = APIRouter()

# Authentication endpoints
@router.post("/auth/login")
@rate_limit(rate=50, per=60)
async def login(
    request: Request, login_data: dict[str, str]
):
    """User login with username and password"""
    try:
        username = login_data.get("username")
        password = login_data.get("password")

        if not username or not password:
            raise HTTPException(status_code=422, detail="Username and password are required")

        # In a real implementation, verify credentials against database
        # For demo, we'll create a simple user
        import os

        demo_users = {
            "admin": os.getenv("DEMO_ADMIN_PASSWORD"),
            "operator": os.getenv("DEMO_OPERATOR_PASSWORD"),
            "user": os.getenv("DEMO_USER_PASSWORD")
        }

        # Require environment variables for demo credentials - no hardcoded fallbacks
        if username in demo_users and demo_users[username] is None:
            raise HTTPException(status_code=500, detail=f"{username.capitalize()} password not configured in environment")

        if username == "admin" and password == demo_users["admin"]:
            user_id = "admin_001"
            role = Role.ADMIN
        elif username == "operator" and password == demo_users["operator"]:
            user_id = "operator_001"
            role = Role.OPERATOR
        elif username == "user" and password == demo_users["user"]:
            user_id = "user_001"
            role = Role.USER
        else:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Assign role to user
        permission_manager.assign_role(user_id, role)

        # Generate JWT token
        token_result = jwt_handler.generate_token({
            "user_id": user_id,
            "username": username,
            "role": role.value,
            "permissions": [perm.value for perm in permission_manager.user_permissions.get(user_id, set())]
        })

        # Generate refresh token
        refresh_result = jwt_handler.generate_refresh_token({
            "user_id": user_id,
            "username": username,
            "role": role.value
        })

        return {
            "status": "success",
            "user_id": user_id,
            "username": username,
            "role": role.value,
            "access_token": token_result["token"],
            "refresh_token": refresh_result["refresh_token"],
            "expires_at": token_result["expires_at"],
            "token_type": token_result["token_type"]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/auth/refresh")
@rate_limit(rate=100, per=60)
async def refresh_token(
    request: Request, refresh_data: dict[str, str]
):
    """Refresh access token using refresh token"""
    try:
        refresh_token = refresh_data.get("refresh_token")

        if not refresh_token:
            raise HTTPException(status_code=422, detail="Refresh token is required")

        result = jwt_handler.refresh_access_token(refresh_token)

        if result["status"] == "error":
            raise HTTPException(status_code=401, detail=result["message"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing token: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/auth/validate")
@rate_limit(rate=200, per=60)
async def validate_token(
    request: Request, validate_data: dict[str, str]
):
    """Validate JWT token"""
    try:
        token = validate_data.get("token")

        if not token:
            raise HTTPException(status_code=422, detail="Token is required")

        result = jwt_handler.validate_token(token)

        if not result["valid"]:
            raise HTTPException(status_code=401, detail=result["message"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating token: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/auth/api-key/generate")
@rate_limit(rate=50, per=60)
async def generate_api_key(
    request: Request,
    user_id: str,
    permissions: list[str] = None,
    current_user: dict[str, Any] = Depends(get_current_user)
):
    """Generate API key for user"""
    try:
        # Check if user has permission to generate API keys
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_MANAGE):
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        result = api_key_manager.generate_api_key(user_id, permissions)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/auth/api-key/validate")
@rate_limit(rate=200, per=60)
async def validate_api_key(
    request: Request, api_key: str
):
    """Validate API key"""
    try:
        result = api_key_manager.validate_api_key(api_key)

        if not result["valid"]:
            raise HTTPException(status_code=401, detail="Invalid API key")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/auth/api-key/{api_key}")
@rate_limit(rate=50, per=60)
async def revoke_api_key(
    request: Request,
    api_key: str,
    current_user: dict[str, Any] = Depends(get_current_user)
):
    """Revoke API key"""
    try:
        # Check if user has permission to manage API keys
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_MANAGE):
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        result = api_key_manager.revoke_api_key(api_key)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))
