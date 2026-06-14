from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from aitbc import get_logger
from aitbc.rate_limiting import rate_limit

from ..auth.middleware import get_current_user, require_role
from ..auth.permissions import Permission, Role, permission_manager

logger = get_logger(__name__)
router = APIRouter()

@router.post('/users/{user_id}/role')
@rate_limit(rate=50, per=60)
async def assign_user_role(request: Request, user_id: str, role: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Assign role to user"""
    try:
        if not permission_manager.has_permission(current_user['user_id'], Permission.USER_MANAGE_ROLES):
            raise HTTPException(status_code=403, detail='Insufficient permissions')
        try:
            role_enum = Role(role.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f'Invalid role: {role}') from None
        result = permission_manager.assign_role(user_id, role_enum)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Error assigning user role: %s', e)
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.get('/users/{user_id}/role')
@rate_limit(rate=200, per=60)
async def get_user_role(request: Request, user_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Get user's role"""
    try:
        if not permission_manager.has_permission(current_user['user_id'], Permission.USER_VIEW):
            raise HTTPException(status_code=403, detail='Insufficient permissions')
        result = permission_manager.get_user_role(user_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Error getting user role: %s', e)
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.get('/users/{user_id}/permissions')
@rate_limit(rate=200, per=60)
async def get_user_permissions(request: Request, user_id: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Get user's permissions"""
    try:
        if user_id != current_user['user_id'] and (not permission_manager.has_permission(current_user['user_id'], Permission.USER_VIEW)):
            raise HTTPException(status_code=403, detail='Insufficient permissions')
        result = permission_manager.get_user_permissions(user_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Error getting user permissions: %s', e)
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post('/users/{user_id}/permissions/grant')
@rate_limit(rate=50, per=60)
async def grant_user_permission(request: Request, user_id: str, permission: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Grant custom permission to user"""
    try:
        if not permission_manager.has_permission(current_user['user_id'], Permission.USER_MANAGE_ROLES):
            raise HTTPException(status_code=403, detail='Insufficient permissions')
        try:
            permission_enum = Permission(permission)
        except ValueError:
            raise HTTPException(status_code=400, detail=f'Invalid permission: {permission}') from None
        result = permission_manager.grant_custom_permission(user_id, permission_enum)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Error granting user permission: %s', e)
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.delete('/users/{user_id}/permissions/{permission}')
@rate_limit(rate=50, per=60)
async def revoke_user_permission(request: Request, user_id: str, permission: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Revoke custom permission from user"""
    try:
        if not permission_manager.has_permission(current_user['user_id'], Permission.USER_MANAGE_ROLES):
            raise HTTPException(status_code=403, detail='Insufficient permissions')
        try:
            permission_enum = Permission(permission)
        except ValueError:
            raise HTTPException(status_code=400, detail=f'Invalid permission: {permission}') from None
        result = permission_manager.revoke_custom_permission(user_id, permission_enum)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Error revoking user permission: %s', e)
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.get('/roles')
@rate_limit(rate=200, per=60)
async def list_all_roles(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """List all available roles and their permissions"""
    try:
        if not permission_manager.has_permission(current_user['user_id'], Permission.USER_VIEW):
            raise HTTPException(status_code=403, detail='Insufficient permissions')
        result = permission_manager.list_all_roles()
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Error listing roles: %s', e)
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.get('/roles/{role}')
@rate_limit(rate=200, per=60)
async def get_role_permissions(request: Request, role: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Get all permissions for a specific role"""
    try:
        if not permission_manager.has_permission(current_user['user_id'], Permission.USER_VIEW):
            raise HTTPException(status_code=403, detail='Insufficient permissions')
        try:
            role_enum = Role(role.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f'Invalid role: {role}') from None
        result = permission_manager.get_role_permissions(role_enum)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Error getting role permissions: %s', e)
        raise HTTPException(status_code=500, detail='Failed to get role permissions') from e

@router.get('/auth/stats')
@rate_limit(rate=200, per=60)
async def get_permission_stats(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Get statistics about permissions and users"""
    try:
        if not permission_manager.has_permission(current_user['user_id'], Permission.SECURITY_VIEW):
            raise HTTPException(status_code=403, detail='Insufficient permissions')
        result = permission_manager.get_permission_stats()
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error('Error getting permission stats: %s', e)
        raise HTTPException(status_code=500, detail='Failed to get permission stats') from e

@router.get('/protected/admin')
@rate_limit(rate=100, per=60)
@require_role([Role.ADMIN])  # type: ignore
async def admin_only_endpoint(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Admin-only endpoint example"""
    return {'status': 'success', 'message': 'Welcome admin!', 'user': {'user_id': current_user.get('user_id'), 'username': current_user.get('username'), 'role': str(current_user.get('role')), 'permissions': current_user.get('permissions', []), 'auth_type': current_user.get('auth_type')}}

@router.get('/protected/operator')
@rate_limit(rate=100, per=60)
@require_role([Role.ADMIN, Role.OPERATOR])  # type: ignore
async def operator_endpoint(request: Request, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Operator and admin endpoint example"""
    return {'status': 'success', 'message': 'Welcome operator!', 'user': {'user_id': current_user.get('user_id'), 'username': current_user.get('username'), 'role': str(current_user.get('role')), 'permissions': current_user.get('permissions', []), 'auth_type': current_user.get('auth_type')}}
