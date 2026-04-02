"""
Permissions and Role-Based Access Control for AITBC Agent Coordinator
Implements RBAC with roles, permissions, and access control
"""

from enum import Enum
from typing import Dict, List, Set, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

class Permission(Enum):
    """System permissions enumeration"""
    
    # Agent Management
    AGENT_REGISTER = "agent:register"
    AGENT_UNREGISTER = "agent:unregister"
    AGENT_UPDATE_STATUS = "agent:update_status"
    AGENT_VIEW = "agent:view"
    AGENT_DISCOVER = "agent:discover"
    
    # Task Management
    TASK_SUBMIT = "task:submit"
    TASK_VIEW = "task:view"
    TASK_UPDATE = "task:update"
    TASK_CANCEL = "task:cancel"
    TASK_ASSIGN = "task:assign"
    
    # Load Balancing
    LOAD_BALANCER_VIEW = "load_balancer:view"
    LOAD_BALANCER_UPDATE = "load_balancer:update"
    LOAD_BALANCER_STRATEGY = "load_balancer:strategy"
    
    # Registry Management
    REGISTRY_VIEW = "registry:view"
    REGISTRY_UPDATE = "registry:update"
    REGISTRY_STATS = "registry:stats"
    
    # Communication
    MESSAGE_SEND = "message:send"
    MESSAGE_BROADCAST = "message:broadcast"
    MESSAGE_VIEW = "message:view"
    
    # AI/ML Features
    AI_LEARNING_EXPERIENCE = "ai:learning:experience"
    AI_LEARNING_STATS = "ai:learning:stats"
    AI_LEARNING_PREDICT = "ai:learning:predict"
    AI_LEARNING_RECOMMEND = "ai:learning:recommend"
    
    AI_NEURAL_CREATE = "ai:neural:create"
    AI_NEURAL_TRAIN = "ai:neural:train"
    AI_NEURAL_PREDICT = "ai:neural:predict"
    
    AI_MODEL_CREATE = "ai:model:create"
    AI_MODEL_TRAIN = "ai:model:train"
    AI_MODEL_PREDICT = "ai:model:predict"
    
    # Consensus
    CONSENSUS_NODE_REGISTER = "consensus:node:register"
    CONSENSUS_PROPOSAL_CREATE = "consensus:proposal:create"
    CONSENSUS_PROPOSAL_VOTE = "consensus:proposal:vote"
    CONSENSUS_ALGORITHM = "consensus:algorithm"
    CONSENSUS_STATS = "consensus:stats"
    
    # System Administration
    SYSTEM_HEALTH = "system:health"
    SYSTEM_STATS = "system:stats"
    SYSTEM_CONFIG = "system:config"
    SYSTEM_LOGS = "system:logs"
    
    # User Management
    USER_CREATE = "user:create"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    USER_VIEW = "user:view"
    USER_MANAGE_ROLES = "user:manage_roles"
    
    # Security
    SECURITY_VIEW = "security:view"
    SECURITY_MANAGE = "security:manage"
    SECURITY_AUDIT = "security:audit"

class Role(Enum):
    """System roles enumeration"""
    
    ADMIN = "admin"
    OPERATOR = "operator"
    USER = "user"
    READONLY = "readonly"
    AGENT = "agent"
    API_USER = "api_user"

@dataclass
class RolePermission:
    """Role to permission mapping"""
    role: Role
    permissions: Set[Permission]
    description: str

class PermissionManager:
    """Permission and role management system"""
    
    def __init__(self):
        self.role_permissions = self._initialize_role_permissions()
        self.user_roles = {}  # {user_id: role}
        self.user_permissions = {}  # {user_id: set(permissions)}
        self.custom_permissions = {}  # {user_id: set(permissions)}
    
    def _initialize_role_permissions(self) -> Dict[Role, Set[Permission]]:
        """Initialize default role permissions"""
        return {
            Role.ADMIN: {
                # Full access to everything
                Permission.AGENT_REGISTER, Permission.AGENT_UNREGISTER,
                Permission.AGENT_UPDATE_STATUS, Permission.AGENT_VIEW, Permission.AGENT_DISCOVER,
                Permission.TASK_SUBMIT, Permission.TASK_VIEW, Permission.TASK_UPDATE,
                Permission.TASK_CANCEL, Permission.TASK_ASSIGN,
                Permission.LOAD_BALANCER_VIEW, Permission.LOAD_BALANCER_UPDATE,
                Permission.LOAD_BALANCER_STRATEGY,
                Permission.REGISTRY_VIEW, Permission.REGISTRY_UPDATE, Permission.REGISTRY_STATS,
                Permission.MESSAGE_SEND, Permission.MESSAGE_BROADCAST, Permission.MESSAGE_VIEW,
                Permission.AI_LEARNING_EXPERIENCE, Permission.AI_LEARNING_STATS,
                Permission.AI_LEARNING_PREDICT, Permission.AI_LEARNING_RECOMMEND,
                Permission.AI_NEURAL_CREATE, Permission.AI_NEURAL_TRAIN, Permission.AI_NEURAL_PREDICT,
                Permission.AI_MODEL_CREATE, Permission.AI_MODEL_TRAIN, Permission.AI_MODEL_PREDICT,
                Permission.CONSENSUS_NODE_REGISTER, Permission.CONSENSUS_PROPOSAL_CREATE,
                Permission.CONSENSUS_PROPOSAL_VOTE, Permission.CONSENSUS_ALGORITHM, Permission.CONSENSUS_STATS,
                Permission.SYSTEM_HEALTH, Permission.SYSTEM_STATS, Permission.SYSTEM_CONFIG,
                Permission.SYSTEM_LOGS,
                Permission.USER_CREATE, Permission.USER_UPDATE, Permission.USER_DELETE,
                Permission.USER_VIEW, Permission.USER_MANAGE_ROLES,
                Permission.SECURITY_VIEW, Permission.SECURITY_MANAGE, Permission.SECURITY_AUDIT
            },
            
            Role.OPERATOR: {
                # Operational access (no user management)
                Permission.AGENT_REGISTER, Permission.AGENT_UNREGISTER,
                Permission.AGENT_UPDATE_STATUS, Permission.AGENT_VIEW, Permission.AGENT_DISCOVER,
                Permission.TASK_SUBMIT, Permission.TASK_VIEW, Permission.TASK_UPDATE,
                Permission.TASK_CANCEL, Permission.TASK_ASSIGN,
                Permission.LOAD_BALANCER_VIEW, Permission.LOAD_BALANCER_UPDATE,
                Permission.LOAD_BALANCER_STRATEGY,
                Permission.REGISTRY_VIEW, Permission.REGISTRY_UPDATE, Permission.REGISTRY_STATS,
                Permission.MESSAGE_SEND, Permission.MESSAGE_BROADCAST, Permission.MESSAGE_VIEW,
                Permission.AI_LEARNING_EXPERIENCE, Permission.AI_LEARNING_STATS,
                Permission.AI_LEARNING_PREDICT, Permission.AI_LEARNING_RECOMMEND,
                Permission.AI_NEURAL_CREATE, Permission.AI_NEURAL_TRAIN, Permission.AI_NEURAL_PREDICT,
                Permission.AI_MODEL_CREATE, Permission.AI_MODEL_TRAIN, Permission.AI_MODEL_PREDICT,
                Permission.CONSENSUS_NODE_REGISTER, Permission.CONSENSUS_PROPOSAL_CREATE,
                Permission.CONSENSUS_PROPOSAL_VOTE, Permission.CONSENSUS_ALGORITHM, Permission.CONSENSUS_STATS,
                Permission.SYSTEM_HEALTH, Permission.SYSTEM_STATS
            },
            
            Role.USER: {
                # Basic user access
                Permission.AGENT_VIEW, Permission.AGENT_DISCOVER,
                Permission.TASK_VIEW,
                Permission.LOAD_BALANCER_VIEW,
                Permission.REGISTRY_VIEW, Permission.REGISTRY_STATS,
                Permission.MESSAGE_VIEW,
                Permission.AI_LEARNING_STATS,
                Permission.AI_LEARNING_PREDICT, Permission.AI_LEARNING_RECOMMEND,
                Permission.AI_NEURAL_PREDICT, Permission.AI_MODEL_PREDICT,
                Permission.CONSENSUS_STATS,
                Permission.SYSTEM_HEALTH
            },
            
            Role.READONLY: {
                # Read-only access
                Permission.AGENT_VIEW,
                Permission.LOAD_BALANCER_VIEW,
                Permission.REGISTRY_VIEW, Permission.REGISTRY_STATS,
                Permission.MESSAGE_VIEW,
                Permission.AI_LEARNING_STATS,
                Permission.CONSENSUS_STATS,
                Permission.SYSTEM_HEALTH
            },
            
            Role.AGENT: {
                # Agent-specific access
                Permission.AGENT_UPDATE_STATUS,
                Permission.TASK_VIEW, Permission.TASK_UPDATE,
                Permission.MESSAGE_SEND, Permission.MESSAGE_VIEW,
                Permission.AI_LEARNING_EXPERIENCE,
                Permission.SYSTEM_HEALTH
            },
            
            Role.API_USER: {
                # API user access (limited)
                Permission.AGENT_VIEW, Permission.AGENT_DISCOVER,
                Permission.TASK_SUBMIT, Permission.TASK_VIEW,
                Permission.LOAD_BALANCER_VIEW,
                Permission.REGISTRY_STATS,
                Permission.AI_LEARNING_STATS,
                Permission.AI_LEARNING_PREDICT,
                Permission.SYSTEM_HEALTH
            }
        }
    
    def assign_role(self, user_id: str, role: Role) -> Dict[str, Any]:
        """Assign role to user"""
        try:
            self.user_roles[user_id] = role
            self.user_permissions[user_id] = self.role_permissions.get(role, set())
            
            return {
                "status": "success",
                "user_id": user_id,
                "role": role.value,
                "permissions": [perm.value for perm in self.user_permissions[user_id]]
            }
            
        except Exception as e:
            logger.error(f"Error assigning role: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_user_role(self, user_id: str) -> Dict[str, Any]:
        """Get user's role"""
        try:
            role = self.user_roles.get(user_id)
            if not role:
                return {"status": "error", "message": "User role not found"}
            
            return {
                "status": "success",
                "user_id": user_id,
                "role": role.value
            }
            
        except Exception as e:
            logger.error(f"Error getting user role: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_user_permissions(self, user_id: str) -> Dict[str, Any]:
        """Get user's permissions"""
        try:
            # Get role-based permissions
            role_perms = self.user_permissions.get(user_id, set())
            
            # Get custom permissions
            custom_perms = self.custom_permissions.get(user_id, set())
            
            # Combine permissions
            all_permissions = role_perms.union(custom_perms)
            
            return {
                "status": "success",
                "user_id": user_id,
                "permissions": [perm.value for perm in all_permissions],
                "role_permissions": len(role_perms),
                "custom_permissions": len(custom_perms),
                "total_permissions": len(all_permissions)
            }
            
        except Exception as e:
            logger.error(f"Error getting user permissions: {e}")
            return {"status": "error", "message": str(e)}
    
    def has_permission(self, user_id: str, permission: Permission) -> bool:
        """Check if user has specific permission"""
        try:
            user_perms = self.user_permissions.get(user_id, set())
            custom_perms = self.custom_permissions.get(user_id, set())
            
            return permission in user_perms or permission in custom_perms
            
        except Exception as e:
            logger.error(f"Error checking permission: {e}")
            return False
    
    def has_permissions(self, user_id: str, permissions: List[Permission]) -> Dict[str, Any]:
        """Check if user has all specified permissions"""
        try:
            results = {}
            for perm in permissions:
                results[perm.value] = self.has_permission(user_id, perm)
            
            all_granted = all(results.values())
            
            return {
                "status": "success",
                "user_id": user_id,
                "all_permissions_granted": all_granted,
                "permission_results": results
            }
            
        except Exception as e:
            logger.error(f"Error checking permissions: {e}")
            return {"status": "error", "message": str(e)}
    
    def grant_custom_permission(self, user_id: str, permission: Permission) -> Dict[str, Any]:
        """Grant custom permission to user"""
        try:
            if user_id not in self.custom_permissions:
                self.custom_permissions[user_id] = set()
            
            self.custom_permissions[user_id].add(permission)
            
            return {
                "status": "success",
                "user_id": user_id,
                "permission": permission.value,
                "total_custom_permissions": len(self.custom_permissions[user_id])
            }
            
        except Exception as e:
            logger.error(f"Error granting custom permission: {e}")
            return {"status": "error", "message": str(e)}
    
    def revoke_custom_permission(self, user_id: str, permission: Permission) -> Dict[str, Any]:
        """Revoke custom permission from user"""
        try:
            if user_id in self.custom_permissions:
                self.custom_permissions[user_id].discard(permission)
                
                return {
                    "status": "success",
                    "user_id": user_id,
                    "permission": permission.value,
                    "remaining_custom_permissions": len(self.custom_permissions[user_id])
                }
            else:
                return {
                    "status": "error",
                    "message": "No custom permissions found for user"
                }
                
        except Exception as e:
            logger.error(f"Error revoking custom permission: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_role_permissions(self, role: Role) -> Dict[str, Any]:
        """Get all permissions for a role"""
        try:
            permissions = self.role_permissions.get(role, set())
            
            return {
                "status": "success",
                "role": role.value,
                "permissions": [perm.value for perm in permissions],
                "total_permissions": len(permissions)
            }
            
        except Exception as e:
            logger.error(f"Error getting role permissions: {e}")
            return {"status": "error", "message": str(e)}
    
    def list_all_roles(self) -> Dict[str, Any]:
        """List all available roles and their permissions"""
        try:
            roles_data = {}
            
            for role, permissions in self.role_permissions.items():
                roles_data[role.value] = {
                    "description": self._get_role_description(role),
                    "permissions": [perm.value for perm in permissions],
                    "total_permissions": len(permissions)
                }
            
            return {
                "status": "success",
                "total_roles": len(roles_data),
                "roles": roles_data
            }
            
        except Exception as e:
            logger.error(f"Error listing roles: {e}")
            return {"status": "error", "message": str(e)}
    
    def _get_role_description(self, role: Role) -> str:
        """Get description for role"""
        descriptions = {
            Role.ADMIN: "Full system access including user management",
            Role.OPERATOR: "Operational access without user management",
            Role.USER: "Basic user access for viewing and basic operations",
            Role.READONLY: "Read-only access to system information",
            Role.AGENT: "Agent-specific access for automated operations",
            Role.API_USER: "Limited API access for external integrations"
        }
        return descriptions.get(role, "No description available")
    
    def get_permission_stats(self) -> Dict[str, Any]:
        """Get statistics about permissions and users"""
        try:
            stats = {
                "total_permissions": len(Permission),
                "total_roles": len(Role),
                "total_users": len(self.user_roles),
                "users_by_role": {},
                "custom_permission_users": len(self.custom_permissions)
            }
            
            # Count users by role
            for user_id, role in self.user_roles.items():
                role_name = role.value
                stats["users_by_role"][role_name] = stats["users_by_role"].get(role_name, 0) + 1
            
            return {
                "status": "success",
                "stats": stats
            }
            
        except Exception as e:
            logger.error(f"Error getting permission stats: {e}")
            return {"status": "error", "message": str(e)}

# Global permission manager instance
permission_manager = PermissionManager()
