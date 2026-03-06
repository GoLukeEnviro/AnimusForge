"""
RBAC (Role-Based Access Control) Module for AnimusForge

Implements ADR-012: Role-Based Access Control Architecture

Features:
- Pydantic v2 Models for type-safe permissions
- Role Inheritance Support
- Attribute-based Conditions (ABAC)
- Resource-based Access Control
- Audit Logging for Access Decisions
- FastAPI Dependency for Authentication
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

# Configure audit logger
audit_logger = logging.getLogger("animus.rbac.audit")
audit_logger.setLevel(logging.INFO)


class ActionType(str, Enum):
    """Types of actions that can be performed on resources."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    MANAGE = "manage"
    AUDIT = "audit"


class ResourceType(str, Enum):
    """Types of resources in the AnimusForge system."""
    PERSONA = "persona"
    MEMORY = "memory"
    TOOL = "tool"
    SYSTEM = "system"
    AUDIT = "audit"


class Permission(BaseModel):
    """Represents a permission to perform an action on a resource."""
    
    resource: ResourceType
    action: ActionType
    conditions: Optional[Dict[str, Any]] = None
    
    model_config = {
        "frozen": False,
        "extra": "forbid"
    }
    
    def matches(self, resource: ResourceType, action: ActionType) -> bool:
        """Check if this permission matches the given resource and action."""
        return self.resource == resource and self.action == action
    
    def __hash__(self) -> int:
        return hash((self.resource, self.action))
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Permission):
            return False
        return self.resource == other.resource and self.action == other.action


class Role(BaseModel):
    """Represents a role with associated permissions."""
    
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(..., min_length=1, max_length=256)
    permissions: List[Permission] = Field(default_factory=list)
    inherits_from: Optional[str] = None
    
    model_config = {
        "extra": "forbid"
    }
    
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.islower():
            raise ValueError("Role name must be lowercase")
        return v


class User(BaseModel):
    """Represents a user with roles and attributes for ABAC."""
    
    id: str = Field(default_factory=lambda: str(uuid4()))
    username: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$")
    roles: List[str] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = {
        "extra": "forbid"
    }
    
    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v: List[str]) -> List[str]:
        return list(set(v))  # Remove duplicates


class AccessDecision(BaseModel):
    """Represents an access control decision for audit logging."""
    
    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    username: str
    resource: ResourceType
    action: ActionType
    resource_id: Optional[str] = None
    granted: bool
    reason: str
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    matched_permissions: List[str] = Field(default_factory=list)
    conditions_evaluated: Dict[str, Any] = Field(default_factory=dict)


class ConditionEvaluator:
    """Evaluates attribute-based conditions for permissions."""
    
    @staticmethod
    def evaluate(
        conditions: Optional[Dict[str, Any]],
        user: User,
        context: Optional[Dict[str, Any]] = None
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Evaluate conditions against user attributes and context.
        
        Returns a tuple of (result, evaluation_details).
        """
        if not conditions:
            return True, {}
        
        evaluation_details: Dict[str, Any] = {}
        context = context or {}
        
        for condition_key, condition_value in conditions.items():
            if condition_key == "owner_id":
                # Check if user owns the resource
                user_id = user.id
                resource_owner = context.get("owner_id")
                result = str(user_id) == str(resource_owner)
                evaluation_details["owner_check"] = {
                    "user_id": user_id,
                    "resource_owner": resource_owner,
                    "passed": result
                }
                if not result:
                    return False, evaluation_details
                    
            elif condition_key == "department":
                # Check if user is in specific department
                user_dept = user.attributes.get("department")
                result = user_dept == condition_value
                evaluation_details["department_check"] = {
                    "user_department": user_dept,
                    "required_department": condition_value,
                    "passed": result
                }
                if not result:
                    return False, evaluation_details
                    
            elif condition_key == "clearance_level":
                # Check user clearance level (numeric comparison)
                user_level = user.attributes.get("clearance_level", 0)
                required_level = condition_value
                result = user_level >= required_level
                evaluation_details["clearance_check"] = {
                    "user_level": user_level,
                    "required_level": required_level,
                    "passed": result
                }
                if not result:
                    return False, evaluation_details
                    
            elif condition_key == "time_restricted":
                # Check time-based restrictions
                if condition_value:
                    now = datetime.now(timezone.utc)
                    hour = now.hour
                    # Default business hours: 9-18
                    result = 9 <= hour < 18
                    evaluation_details["time_check"] = {
                        "current_hour": hour,
                        "business_hours": "9-18",
                        "passed": result
                    }
                    if not result:
                        return False, evaluation_details
                        
            elif condition_key == "ip_whitelist":
                # Check IP-based restrictions
                allowed_ips = condition_value if isinstance(condition_value, list) else [condition_value]
                user_ip = context.get("ip_address")
                result = user_ip in allowed_ips
                evaluation_details["ip_check"] = {
                    "user_ip": user_ip,
                    "allowed_ips": allowed_ips,
                    "passed": result
                }
                if not result:
                    return False, evaluation_details
                    
            elif condition_key == "custom":
                # Custom condition evaluator function
                evaluator: Optional[Callable] = context.get("custom_evaluator")
                if evaluator:
                    result = evaluator(user, context)
                    evaluation_details["custom_check"] = {"passed": result}
                    if not result:
                        return False, evaluation_details
        
        return True, evaluation_details


class RBACEngine:
    """
    Role-Based Access Control Engine with ABAC extensions.
    
    Features:
    - Role-based permission checking
    - Role inheritance
    - Attribute-based conditions
    - Resource-based access control
    - Audit logging
    """
    
    def __init__(self) -> None:
        self._roles: Dict[str, Role] = {}
        self._users: Dict[str, User] = {}
        self._resource_owners: Dict[str, str] = {}  # resource_id -> user_id
        self._audit_log: List[AccessDecision] = []
        self._initialize_default_roles()
    
    def _initialize_default_roles(self) -> None:
        """Initialize default roles according to ADR-012."""
        
        # Admin: Vollzugriff - alle Actions auf alle Ressourcen
        admin_permissions = [
            Permission(resource=res, action=act)
            for res in ResourceType
            for act in ActionType
        ]
        self._roles["admin"] = Role(
            name="admin",
            description="Vollzugriff - alle Actions auf alle Ressourcen",
            permissions=admin_permissions
        )
        
        # Operator: Betrieb - read, execute, manage auf System
        operator_permissions = [
            Permission(resource=ResourceType.SYSTEM, action=ActionType.READ),
            Permission(resource=ResourceType.SYSTEM, action=ActionType.EXECUTE),
            Permission(resource=ResourceType.SYSTEM, action=ActionType.MANAGE),
            Permission(resource=ResourceType.PERSONA, action=ActionType.READ),
            Permission(resource=ResourceType.MEMORY, action=ActionType.READ),
            Permission(resource=ResourceType.AUDIT, action=ActionType.READ),
        ]
        self._roles["operator"] = Role(
            name="operator",
            description="Betrieb - read, execute, manage auf System",
            permissions=operator_permissions
        )
        
        # Developer: Entwicklung - create, read, update auf Personas
        developer_permissions = [
            Permission(resource=ResourceType.PERSONA, action=ActionType.CREATE),
            Permission(resource=ResourceType.PERSONA, action=ActionType.READ),
            Permission(resource=ResourceType.PERSONA, action=ActionType.UPDATE),
            Permission(resource=ResourceType.MEMORY, action=ActionType.READ),
            Permission(resource=ResourceType.MEMORY, action=ActionType.CREATE),
            Permission(resource=ResourceType.TOOL, action=ActionType.READ),
        ]
        self._roles["developer"] = Role(
            name="developer",
            description="Entwicklung - create, read, update auf Personas",
            permissions=developer_permissions
        )
        
        # Analyst: Analyse - read, audit auf alle Ressourcen
        analyst_permissions = [
            Permission(resource=res, action=ActionType.READ)
            for res in ResourceType
        ] + [
            Permission(resource=res, action=ActionType.AUDIT)
            for res in ResourceType
        ]
        self._roles["analyst"] = Role(
            name="analyst",
            description="Analyse - read, audit auf alle Ressourcen",
            permissions=analyst_permissions
        )
        
        # User: Endbenutzer - read, execute auf eigene Personas
        user_permissions = [
            Permission(
                resource=ResourceType.PERSONA,
                action=ActionType.READ,
                conditions={"owner_id": True}
            ),
            Permission(
                resource=ResourceType.PERSONA,
                action=ActionType.EXECUTE,
                conditions={"owner_id": True}
            ),
            Permission(
                resource=ResourceType.MEMORY,
                action=ActionType.READ,
                conditions={"owner_id": True}
            ),
        ]
        self._roles["user"] = Role(
            name="user",
            description="Endbenutzer - read, execute auf eigene Personas",
            permissions=user_permissions
        )
    
    @property
    def roles(self) -> Dict[str, Role]:
        """Get all registered roles."""
        return self._roles.copy()
    
    @property
    def users(self) -> Dict[str, User]:
        """Get all registered users."""
        return self._users.copy()
    
    def register_role(self, role: Role) -> None:
        """Register a new role or update existing one."""
        self._roles[role.name] = role
    
    def unregister_role(self, role_name: str) -> bool:
        """Unregister a role. Returns True if role existed."""
        return self._roles.pop(role_name, None) is not None
    
    def register_user(self, user: User) -> None:
        """Register a new user or update existing one."""
        self._users[user.id] = user
    
    def unregister_user(self, user_id: str) -> bool:
        """Unregister a user. Returns True if user existed."""
        return self._users.pop(user_id, None) is not None
    
    def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID."""
        return self._users.get(user_id)
    
    def get_role(self, role_name: str) -> Optional[Role]:
        """Get a role by name."""
        return self._roles.get(role_name)
    
    def _resolve_permissions(self, role_name: str, visited: Optional[Set[str]] = None) -> List[Permission]:
        """
        Resolve all permissions for a role, including inherited permissions.
        Handles circular inheritance detection.
        """
        if visited is None:
            visited = set()
        
        if role_name in visited:
            # Circular inheritance detected
            audit_logger.warning(f"Circular inheritance detected for role: {role_name}")
            return []
        
        visited.add(role_name)
        
        role = self._roles.get(role_name)
        if not role:
            return []
        
        permissions = list(role.permissions)
        
        # Resolve inherited permissions
        if role.inherits_from:
            inherited = self._resolve_permissions(role.inherits_from, visited)
            permissions.extend(inherited)
        
        return permissions
    
    def get_permissions(self, user_id: str) -> List[Permission]:
        """
        Get all effective permissions for a user.
        
        Aggregates permissions from all assigned roles, including inherited ones.
        """
        user = self._users.get(user_id)
        if not user or not user.is_active:
            return []
        
        all_permissions: List[Permission] = []
        seen: Set[tuple] = set()
        
        for role_name in user.roles:
            role_permissions = self._resolve_permissions(role_name)
            for perm in role_permissions:
                perm_key = (perm.resource, perm.action)
                if perm_key not in seen:
                    seen.add(perm_key)
                    all_permissions.append(perm)
        
        return all_permissions
    
    def grant_role(self, user_id: str, role_name: str) -> bool:
        """
        Grant a role to a user.
        
        Returns True if role was granted, False if user/role doesn't exist
        or user already has the role.
        """
        user = self._users.get(user_id)
        if not user:
            return False
        
        if role_name not in self._roles:
            return False
        
        if role_name in user.roles:
            return False  # Already has role
        
        user.roles.append(role_name)
        return True
    
    def revoke_role(self, user_id: str, role_name: str) -> bool:
        """
        Revoke a role from a user.
        
        Returns True if role was revoked, False if user doesn't exist
        or didn't have the role.
        """
        user = self._users.get(user_id)
        if not user:
            return False
        
        if role_name not in user.roles:
            return False
        
        user.roles.remove(role_name)
        return True
    
    def register_resource_owner(self, resource_id: str, user_id: str) -> None:
        """Register the owner of a resource for resource-based access control."""
        self._resource_owners[resource_id] = user_id
    
    def unregister_resource_owner(self, resource_id: str) -> bool:
        """Unregister a resource owner. Returns True if resource existed."""
        return self._resource_owners.pop(resource_id, None) is not None
    
    def get_resource_owner(self, resource_id: str) -> Optional[str]:
        """Get the owner of a resource."""
        return self._resource_owners.get(resource_id)
    
    def check_permission(
        self,
        user_id: str,
        resource: ResourceType,
        action: ActionType,
        context: Optional[Dict[str, Any]] = None
    ) -> AccessDecision:
        """
        Check if a user has permission to perform an action on a resource.
        
        This is the main entry point for permission checking.
        Returns an AccessDecision with full audit information.
        """
        user = self._users.get(user_id)
        
        if not user:
            decision = AccessDecision(
                user_id=user_id,
                username="<unknown>",
                resource=resource,
                action=action,
                granted=False,
                reason="User not found"
            )
            self._log_decision(decision)
            return decision
        
        if not user.is_active:
            decision = AccessDecision(
                user_id=user_id,
                username=user.username,
                resource=resource,
                action=action,
                granted=False,
                reason="User is inactive"
            )
            self._log_decision(decision)
            return decision
        
        # Get all user permissions
        permissions = self.get_permissions(user_id)
        
        # Find matching permissions
        matched_perms: List[Permission] = []
        for perm in permissions:
            if perm.matches(resource, action):
                matched_perms.append(perm)
        
        if not matched_perms:
            decision = AccessDecision(
                user_id=user_id,
                username=user.username,
                resource=resource,
                action=action,
                granted=False,
                reason=f"No permission for {action.value} on {resource.value}"
            )
            self._log_decision(decision)
            return decision
        
        # Evaluate conditions for matched permissions
        context = context or {}
        for perm in matched_perms:
            if perm.conditions:
                # Add owner_id to context if available
                resource_id = context.get("resource_id")
                if resource_id and "owner_id" in perm.conditions:
                    context["owner_id"] = self._resource_owners.get(resource_id)
                
                passed, eval_details = ConditionEvaluator.evaluate(
                    perm.conditions, user, context
                )
                
                if passed:
                    decision = AccessDecision(
                        user_id=user_id,
                        username=user.username,
                        resource=resource,
                        action=action,
                        resource_id=resource_id,
                        granted=True,
                        reason="Permission granted with conditions satisfied",
                        matched_permissions=[f"{perm.resource.value}:{perm.action.value}" for perm in matched_perms],
                        conditions_evaluated=eval_details
                    )
                    self._log_decision(decision)
                    return decision
            else:
                # No conditions, permission granted
                decision = AccessDecision(
                    user_id=user_id,
                    username=user.username,
                    resource=resource,
                    action=action,
                    granted=True,
                    reason="Permission granted",
                    matched_permissions=[f"{perm.resource.value}:{perm.action.value}" for perm in matched_perms]
                )
                self._log_decision(decision)
                return decision
        
        # All matched permissions had conditions that failed
        decision = AccessDecision(
            user_id=user_id,
            username=user.username,
            resource=resource,
            action=action,
            granted=False,
            reason="Permission conditions not satisfied",
            matched_permissions=[f"{perm.resource.value}:{perm.action.value}" for perm in matched_perms],
            conditions_evaluated=eval_details if 'eval_details' in dir() else {}
        )
        self._log_decision(decision)
        return decision
    
    def check_resource_access(
        self,
        user_id: str,
        resource_id: str,
        action: ActionType,
        resource_type: Optional[ResourceType] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> AccessDecision:
        """
        Check if a user has access to a specific resource instance.
        
        This extends basic permission checking with resource-based access control.
        """
        context = context or {}
        context["resource_id"] = resource_id
        
        # Try to infer resource type from resource_id prefix if not provided
        if not resource_type:
            for res_type in ResourceType:
                if resource_id.startswith(f"{res_type.value}_"):
                    resource_type = res_type
                    break
        
        if not resource_type:
            resource_type = ResourceType.SYSTEM  # Default fallback
        
        return self.check_permission(user_id, resource_type, action, context)
    
    def _log_decision(self, decision: AccessDecision) -> None:
        """Log an access decision for audit purposes."""
        self._audit_log.append(decision)
        
        log_data = decision.model_dump()
        if decision.granted:
            audit_logger.info(f"ACCESS GRANTED: {log_data}")
        else:
            audit_logger.warning(f"ACCESS DENIED: {log_data}")
    
    def get_audit_log(
        self,
        user_id: Optional[str] = None,
        granted: Optional[bool] = None,
        limit: int = 100
    ) -> List[AccessDecision]:
        """
        Get audit log entries, optionally filtered.
        
        Args:
            user_id: Filter by user ID
            granted: Filter by granted status
            limit: Maximum number of entries to return
        """
        log = self._audit_log
        
        if user_id:
            log = [d for d in log if d.user_id == user_id]
        
        if granted is not None:
            log = [d for d in log if d.granted == granted]
        
        return log[-limit:]
    
    def clear_audit_log(self) -> int:
        """Clear the audit log. Returns number of entries cleared."""
        count = len(self._audit_log)
        self._audit_log.clear()
        return count


# FastAPI Integration
from typing import Annotated

try:
    from fastapi import Depends, HTTPException, Request, status
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    
    security = HTTPBearer(auto_error=False)
    
    # Global RBAC engine instance
    _rbac_engine: Optional[RBACEngine] = None
    
    def get_rbac_engine() -> RBACEngine:
        """Get the global RBAC engine instance."""
        global _rbac_engine
        if _rbac_engine is None:
            _rbac_engine = RBACEngine()
        return _rbac_engine
    
    def set_rbac_engine(engine: RBACEngine) -> None:
        """Set the global RBAC engine instance."""
        global _rbac_engine
        _rbac_engine = engine
    
    async def get_current_user(
        request: Request,
        credentials: Annotated[
            Optional[HTTPAuthorizationCredentials],
            Depends(security)
        ] = None
    ) -> User:
        """
        FastAPI dependency to get the current authenticated user.
        
        This is a placeholder implementation. In production, this would
        validate JWT tokens, session cookies, or API keys.
        """
        # Placeholder: Extract user from request state or headers
        # In production, implement proper authentication
        user_id = request.headers.get("X-User-ID")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )
        
        engine = get_rbac_engine()
        user = engine.get_user(user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is inactive"
            )
        
        return user
    
    def require_permission(
        resource: ResourceType,
        action: ActionType
    ) -> Callable:
        """
        FastAPI dependency factory for permission checking.
        
        Usage:
            @router.get("/personas")
            async def list_personas(
                user: User = Depends(require_permission(ResourceType.PERSONA, ActionType.READ))
            ):
                ...
        """
        async def dependency(
            user: Annotated[User, Depends(get_current_user)],
            request: Request
        ) -> User:
            engine = get_rbac_engine()
            
            context = {
                "ip_address": request.client.host if request.client else None,
                "resource_id": request.path_params.get("id")
            }
            
            decision = engine.check_permission(
                user.id, resource, action, context
            )
            
            if not decision.granted:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=decision.reason
                )
            
            return user
        
        return Depends(dependency)
    
    # Type aliases for cleaner dependency injection
    CurrentUser = Annotated[User, Depends(get_current_user)]
    
except ImportError:
    # FastAPI not installed
    pass


# Convenience functions
def create_rbac_engine() -> RBACEngine:
    """Create and return a new RBAC engine with default roles."""
    return RBACEngine()


def create_user(
    username: str,
    roles: Optional[List[str]] = None,
    attributes: Optional[Dict[str, Any]] = None
) -> User:
    """Create a new user with the specified roles and attributes."""
    return User(
        username=username,
        roles=roles or [],
        attributes=attributes or {}
    )


__all__ = [
    "ActionType",
    "ResourceType",
    "Permission",
    "Role",
    "User",
    "AccessDecision",
    "ConditionEvaluator",
    "RBACEngine",
    "create_rbac_engine",
    "create_user",
]
