from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from aitbc import get_logger
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from .. import state
from ..auth.jwt_handler import api_key_manager, jwt_handler
from ..auth.middleware import get_current_user, require_role
from ..auth.permissions import Permission, Role, permission_manager
from ..ai.advanced_ai import ai_integration
from ..ai.realtime_learning import learning_system
from ..consensus.distributed_consensus import distributed_consensus
from ..models import AgentRegistrationRequest, AgentStatusUpdate, MessageRequest, TaskSubmission
from ..monitoring.alerting import alert_manager
from ..monitoring.prometheus_metrics import metrics_registry, performance_monitor
from ..protocols.communication import MessageType, create_protocol
from ..protocols.message_types import create_task_message
from ..routing.agent_discovery import create_agent_info
from ..routing.load_balancer import LoadBalancingStrategy, TaskPriority

logger = get_logger(__name__)
router = APIRouter()

# User management endpoints
@router.post("/users/{user_id}/role")
async def assign_user_role(
    user_id: str,
    role: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Assign role to user"""
    try:
        # Check if user has permission to manage roles
        if not permission_manager.has_permission(current_user["user_id"], Permission.USER_MANAGE_ROLES):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        try:
            role_enum = Role(role.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid role: {role}")
        
        result = permission_manager.assign_role(user_id, role_enum)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning user role: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/{user_id}/role")
async def get_user_role(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get user's role"""
    try:
        # Check if user has permission to view users
        if not permission_manager.has_permission(current_user["user_id"], Permission.USER_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        result = permission_manager.get_user_role(user_id)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user role: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/{user_id}/permissions")
async def get_user_permissions(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get user's permissions"""
    try:
        # Users can view their own permissions, admins can view any
        if user_id != current_user["user_id"] and not permission_manager.has_permission(current_user["user_id"], Permission.USER_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        result = permission_manager.get_user_permissions(user_id)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user permissions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users/{user_id}/permissions/grant")
async def grant_user_permission(
    user_id: str,
    permission: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Grant custom permission to user"""
    try:
        # Check if user has permission to manage permissions
        if not permission_manager.has_permission(current_user["user_id"], Permission.USER_MANAGE_ROLES):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        try:
            permission_enum = Permission(permission)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid permission: {permission}")
        
        result = permission_manager.grant_custom_permission(user_id, permission_enum)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error granting user permission: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/users/{user_id}/permissions/{permission}")
async def revoke_user_permission(
    user_id: str,
    permission: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Revoke custom permission from user"""
    try:
        # Check if user has permission to manage permissions
        if not permission_manager.has_permission(current_user["user_id"], Permission.USER_MANAGE_ROLES):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        try:
            permission_enum = Permission(permission)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid permission: {permission}")
        
        result = permission_manager.revoke_custom_permission(user_id, permission_enum)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking user permission: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Role and permission management endpoints
@router.get("/roles")
async def list_all_roles(current_user: Dict[str, Any] = Depends(get_current_user)):
    """List all available roles and their permissions"""
    try:
        # Check if user has permission to view roles
        if not permission_manager.has_permission(current_user["user_id"], Permission.USER_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        result = permission_manager.list_all_roles()
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing roles: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/roles/{role}")
async def get_role_permissions(
    role: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get all permissions for a specific role"""
    try:
        # Check if user has permission to view roles
        if not permission_manager.has_permission(current_user["user_id"], Permission.USER_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        try:
            role_enum = Role(role.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid role: {role}")
        
        result = permission_manager.get_role_permissions(role_enum)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting role permissions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/auth/stats")
async def get_permission_stats(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get statistics about permissions and users"""
    try:
        # Check if user has permission to view security stats
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        result = permission_manager.get_permission_stats()
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting permission stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Protected endpoint example
@router.get("/protected/admin")
@require_role([Role.ADMIN])
async def admin_only_endpoint(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Admin-only endpoint example"""
    return {
        "status": "success",
        "message": "Welcome admin!",
        "user": {
            "user_id": current_user.get("user_id"),
            "username": current_user.get("username"),
            "role": str(current_user.get("role")),
            "permissions": current_user.get("permissions", []),
            "auth_type": current_user.get("auth_type")
        }
    }

@router.get("/protected/operator")
@require_role([Role.ADMIN, Role.OPERATOR])
async def operator_endpoint(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Operator and admin endpoint example"""
    return {
        "status": "success",
        "message": "Welcome operator!",
        "user": {
            "user_id": current_user.get("user_id"),
            "username": current_user.get("username"),
            "role": str(current_user.get("role")),
            "permissions": current_user.get("permissions", []),
            "auth_type": current_user.get("auth_type")
        }
    }
