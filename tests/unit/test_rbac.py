"""
Unit Tests for RBAC Module (SPRINT1-004)

Comprehensive tests for Role-Based Access Control implementation.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

from animus_core.rbac import (
    ActionType,
    ResourceType,
    Permission,
    Role,
    User,
    AccessDecision,
    ConditionEvaluator,
    RBACEngine,
    create_rbac_engine,
    create_user,
)


class TestActionType:
    """Tests for ActionType enum."""
    
    def test_all_action_types_exist(self):
        """Verify all required action types are defined."""
        expected = {"create", "read", "update", "delete", "execute", "manage", "audit"}
        actual = {action.value for action in ActionType}
        assert expected == actual
    
    def test_action_type_string_conversion(self):
        """Test string conversion of ActionType."""
        assert ActionType.CREATE.value == "create"
        assert ActionType.READ.value == "read"


class TestResourceType:
    """Tests for ResourceType enum."""
    
    def test_all_resource_types_exist(self):
        """Verify all required resource types are defined."""
        expected = {"persona", "memory", "tool", "system", "audit"}
        actual = {res.value for res in ResourceType}
        assert expected == actual
    
    def test_resource_type_string_conversion(self):
        """Test string conversion of ResourceType."""
        assert ResourceType.PERSONA.value == "persona"
        assert ResourceType.SYSTEM.value == "system"


class TestPermission:
    """Tests for Permission model."""
    
    def test_create_permission_basic(self):
        """Test basic permission creation."""
        perm = Permission(
            resource=ResourceType.PERSONA,
            action=ActionType.READ
        )
        assert perm.resource == ResourceType.PERSONA
        assert perm.action == ActionType.READ
        assert perm.conditions is None
    
    def test_create_permission_with_conditions(self):
        """Test permission creation with conditions."""
        conditions = {"owner_id": True, "department": "engineering"}
        perm = Permission(
            resource=ResourceType.PERSONA,
            action=ActionType.UPDATE,
            conditions=conditions
        )
        assert perm.conditions == conditions
    
    def test_permission_matches(self):
        """Test permission matching logic."""
        perm = Permission(resource=ResourceType.PERSONA, action=ActionType.READ)
        
        assert perm.matches(ResourceType.PERSONA, ActionType.READ) is True
        assert perm.matches(ResourceType.PERSONA, ActionType.UPDATE) is False
        assert perm.matches(ResourceType.SYSTEM, ActionType.READ) is False
    
    def test_permission_hash_and_equality(self):
        """Test permission hashing and equality."""
        perm1 = Permission(resource=ResourceType.PERSONA, action=ActionType.READ)
        perm2 = Permission(resource=ResourceType.PERSONA, action=ActionType.READ)
        perm3 = Permission(resource=ResourceType.PERSONA, action=ActionType.UPDATE)
        
        assert perm1 == perm2
        assert perm1 != perm3
        assert hash(perm1) == hash(perm2)
        
        # Test in set
        perm_set = {perm1, perm2, perm3}
        assert len(perm_set) == 2
    
    def test_permission_frozen_config(self):
        """Test that extra fields are forbidden."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            Permission(
                resource=ResourceType.PERSONA,
                action=ActionType.READ,
                extra_field="not_allowed"
            )


class TestRole:
    """Tests for Role model."""
    
    def test_create_role_basic(self):
        """Test basic role creation."""
        role = Role(
            name="test_role",
            description="Test role for testing"
        )
        assert role.name == "test_role"
        assert role.description == "Test role for testing"
        assert role.permissions == []
        assert role.inherits_from is None
    
    def test_create_role_with_permissions(self):
        """Test role creation with permissions."""
        perms = [
            Permission(resource=ResourceType.PERSONA, action=ActionType.READ),
            Permission(resource=ResourceType.PERSONA, action=ActionType.CREATE),
        ]
        role = Role(
            name="creator",
            description="Creator role",
            permissions=perms
        )
        assert len(role.permissions) == 2
    
    def test_create_role_with_inheritance(self):
        """Test role creation with inheritance."""
        role = Role(
            name="junior_dev",
            description="Junior Developer",
            inherits_from="developer"
        )
        assert role.inherits_from == "developer"
    
    def test_role_name_validation_lowercase(self):
        """Test role name must be lowercase."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            Role(name="InvalidName", description="Invalid role")
    
    def test_role_name_validation_pattern(self):
        """Test role name pattern validation."""
        # Valid names
        Role(name="admin", description="Admin")
        Role(name="super_admin", description="Super Admin")
        Role(name="admin2", description="Admin 2")
        
        # Invalid names
        with pytest.raises(Exception):
            Role(name="1admin", description="Starts with number")
        with pytest.raises(Exception):
            Role(name="admin-name", description="Contains hyphen")


class TestUser:
    """Tests for User model."""
    
    def test_create_user_basic(self):
        """Test basic user creation."""
        user = User(username="testuser")
        assert user.username == "testuser"
        assert user.roles == []
        assert user.attributes == {}
        assert user.is_active is True
        assert user.id is not None
    
    def test_create_user_with_roles(self):
        """Test user creation with roles."""
        user = User(
            username="developer1",
            roles=["developer", "analyst"]
        )
        assert set(user.roles) == {"developer", "analyst"}
    
    def test_create_user_with_attributes(self):
        """Test user creation with ABAC attributes."""
        user = User(
            username="jdoe",
            attributes={
                "department": "engineering",
                "clearance_level": 3
            }
        )
        assert user.attributes["department"] == "engineering"
        assert user.attributes["clearance_level"] == 3
    
    def test_user_roles_deduplication(self):
        """Test that duplicate roles are removed."""
        user = User(
            username="test",
            roles=["admin", "admin", "developer", "developer"]
        )
        assert len(user.roles) == 2
    
    def test_user_username_validation(self):
        """Test username validation."""
        # Valid usernames
        User(username="john")
        User(username="JohnDoe")
        User(username="user_123")
        
        # Invalid usernames
        with pytest.raises(Exception):
            User(username="")
        with pytest.raises(Exception):
            User(username="123user")
    
    def test_user_created_at_default(self):
        """Test that created_at is set automatically."""
        before = datetime.now(timezone.utc)
        user = User(username="test")
        after = datetime.now(timezone.utc)
        
        assert before <= user.created_at <= after


class TestConditionEvaluator:
    """Tests for ConditionEvaluator."""
    
    def test_evaluate_no_conditions(self):
        """Test evaluation with no conditions."""
        user = User(username="test")
        passed, details = ConditionEvaluator.evaluate(None, user, {})
        assert passed is True
        assert details == {}
    
    def test_evaluate_owner_id_condition_pass(self):
        """Test owner_id condition when user is owner."""
        user = User(id="user123", username="test")
        conditions = {"owner_id": True}
        context = {"owner_id": "user123"}
        
        passed, details = ConditionEvaluator.evaluate(conditions, user, context)
        assert passed is True
        assert details["owner_check"]["passed"] is True
    
    def test_evaluate_owner_id_condition_fail(self):
        """Test owner_id condition when user is not owner."""
        user = User(id="user123", username="test")
        conditions = {"owner_id": True}
        context = {"owner_id": "user456"}
        
        passed, details = ConditionEvaluator.evaluate(conditions, user, context)
        assert passed is False
        assert details["owner_check"]["passed"] is False
    
    def test_evaluate_department_condition_pass(self):
        """Test department condition when matching."""
        user = User(
            username="test",
            attributes={"department": "engineering"}
        )
        conditions = {"department": "engineering"}
        
        passed, details = ConditionEvaluator.evaluate(conditions, user, {})
        assert passed is True
    
    def test_evaluate_department_condition_fail(self):
        """Test department condition when not matching."""
        user = User(
            username="test",
            attributes={"department": "sales"}
        )
        conditions = {"department": "engineering"}
        
        passed, details = ConditionEvaluator.evaluate(conditions, user, {})
        assert passed is False
    
    def test_evaluate_clearance_level_condition_pass(self):
        """Test clearance level condition when sufficient."""
        user = User(
            username="test",
            attributes={"clearance_level": 5}
        )
        conditions = {"clearance_level": 3}
        
        passed, details = ConditionEvaluator.evaluate(conditions, user, {})
        assert passed is True
    
    def test_evaluate_clearance_level_condition_fail(self):
        """Test clearance level condition when insufficient."""
        user = User(
            username="test",
            attributes={"clearance_level": 2}
        )
        conditions = {"clearance_level": 3}
        
        passed, details = ConditionEvaluator.evaluate(conditions, user, {})
        assert passed is False
    
    def test_evaluate_time_restricted_condition(self):
        """Test time-based condition."""
        user = User(username="test")
        conditions = {"time_restricted": True}
        
        # This test may pass or fail depending on when it runs
        # Just verify the condition is evaluated
        passed, details = ConditionEvaluator.evaluate(conditions, user, {})
        assert "time_check" in details
    
    def test_evaluate_ip_whitelist_condition_pass(self):
        """Test IP whitelist condition when IP is allowed."""
        user = User(username="test")
        conditions = {"ip_whitelist": ["192.168.1.1", "10.0.0.1"]}
        context = {"ip_address": "192.168.1.1"}
        
        passed, details = ConditionEvaluator.evaluate(conditions, user, context)
        assert passed is True
    
    def test_evaluate_ip_whitelist_condition_fail(self):
        """Test IP whitelist condition when IP is not allowed."""
        user = User(username="test")
        conditions = {"ip_whitelist": ["192.168.1.1"]}
        context = {"ip_address": "10.0.0.1"}
        
        passed, details = ConditionEvaluator.evaluate(conditions, user, context)
        assert passed is False
    
    def test_evaluate_custom_condition(self):
        """Test custom condition evaluator."""
        user = User(username="test")
        conditions = {"custom": True}
        
        # Custom evaluator that always returns True
        custom_evaluator = Mock(return_value=True)
        context = {"custom_evaluator": custom_evaluator}
        
        passed, details = ConditionEvaluator.evaluate(conditions, user, context)
        assert passed is True
        custom_evaluator.assert_called_once()


class TestRBACEngine:
    """Tests for RBACEngine class."""
    
    @pytest.fixture
    def engine(self):
        """Create a fresh RBAC engine for each test."""
        return RBACEngine()
    
    def test_engine_initialization(self, engine):
        """Test that engine initializes with default roles."""
        assert "admin" in engine.roles
        assert "operator" in engine.roles
        assert "developer" in engine.roles
        assert "analyst" in engine.roles
        assert "user" in engine.roles
    
    def test_admin_role_has_all_permissions(self, engine):
        """Test that admin role has all permissions."""
        admin_role = engine.get_role("admin")
        assert admin_role is not None
        
        # Admin should have all combinations
        expected_count = len(ResourceType) * len(ActionType)
        assert len(admin_role.permissions) == expected_count
    
    def test_operator_role_permissions(self, engine):
        """Test operator role has correct permissions."""
        perms = engine.get_role("operator").permissions
        resource_actions = [(p.resource, p.action) for p in perms]
        
        assert (ResourceType.SYSTEM, ActionType.READ) in resource_actions
        assert (ResourceType.SYSTEM, ActionType.EXECUTE) in resource_actions
        assert (ResourceType.SYSTEM, ActionType.MANAGE) in resource_actions
        assert (ResourceType.PERSONA, ActionType.READ) in resource_actions
    
    def test_developer_role_permissions(self, engine):
        """Test developer role has correct permissions."""
        perms = engine.get_role("developer").permissions
        resource_actions = [(p.resource, p.action) for p in perms]
        
        assert (ResourceType.PERSONA, ActionType.CREATE) in resource_actions
        assert (ResourceType.PERSONA, ActionType.READ) in resource_actions
        assert (ResourceType.PERSONA, ActionType.UPDATE) in resource_actions
        assert (ResourceType.PERSONA, ActionType.DELETE) not in resource_actions
    
    def test_analyst_role_permissions(self, engine):
        """Test analyst role has read and audit permissions."""
        perms = engine.get_role("analyst").permissions
        
        for res in ResourceType:
            assert any(p.resource == res and p.action == ActionType.READ for p in perms)
            assert any(p.resource == res and p.action == ActionType.AUDIT for p in perms)
    
    def test_user_role_has_conditions(self, engine):
        """Test that user role has owner-based conditions."""
        user_role = engine.get_role("user")
        
        # User role permissions should have owner_id conditions
        for perm in user_role.permissions:
            assert perm.conditions is not None
            assert "owner_id" in perm.conditions
    
    def test_register_and_get_user(self, engine):
        """Test user registration and retrieval."""
        user = User(username="testuser", roles=["developer"])
        engine.register_user(user)
        
        retrieved = engine.get_user(user.id)
        assert retrieved is not None
        assert retrieved.username == "testuser"
        assert "developer" in retrieved.roles
    
    def test_unregister_user(self, engine):
        """Test user unregistration."""
        user = User(username="testuser")
        engine.register_user(user)
        
        result = engine.unregister_user(user.id)
        assert result is True
        assert engine.get_user(user.id) is None
    
    def test_register_and_get_role(self, engine):
        """Test custom role registration."""
        custom_role = Role(
            name="custom_role",
            description="Custom role",
            permissions=[
                Permission(resource=ResourceType.PERSONA, action=ActionType.READ)
            ]
        )
        engine.register_role(custom_role)
        
        retrieved = engine.get_role("custom_role")
        assert retrieved is not None
        assert retrieved.description == "Custom role"
    
    def test_unregister_role(self, engine):
        """Test role unregistration."""
        custom_role = Role(name="temp_role", description="Temporary")
        engine.register_role(custom_role)
        
        result = engine.unregister_role("temp_role")
        assert result is True
        assert engine.get_role("temp_role") is None
    
    def test_grant_role(self, engine):
        """Test granting a role to a user."""
        user = User(username="testuser", roles=[])
        engine.register_user(user)
        
        result = engine.grant_role(user.id, "developer")
        assert result is True
        assert "developer" in engine.get_user(user.id).roles
    
    def test_grant_role_already_exists(self, engine):
        """Test granting a role that user already has."""
        user = User(username="testuser", roles=["developer"])
        engine.register_user(user)
        
        result = engine.grant_role(user.id, "developer")
        assert result is False
    
    def test_grant_role_nonexistent_role(self, engine):
        """Test granting a nonexistent role."""
        user = User(username="testuser", roles=[])
        engine.register_user(user)
        
        result = engine.grant_role(user.id, "nonexistent")
        assert result is False
    
    def test_revoke_role(self, engine):
        """Test revoking a role from a user."""
        user = User(username="testuser", roles=["developer"])
        engine.register_user(user)
        
        result = engine.revoke_role(user.id, "developer")
        assert result is True
        assert "developer" not in engine.get_user(user.id).roles
    
    def test_revoke_role_not_assigned(self, engine):
        """Test revoking a role that user doesn't have."""
        user = User(username="testuser", roles=[])
        engine.register_user(user)
        
        result = engine.revoke_role(user.id, "developer")
        assert result is False
    
    def test_get_permissions_single_role(self, engine):
        """Test getting permissions for a user with single role."""
        user = User(username="testuser", roles=["developer"])
        engine.register_user(user)
        
        perms = engine.get_permissions(user.id)
        resource_actions = [(p.resource, p.action) for p in perms]
        
        assert (ResourceType.PERSONA, ActionType.CREATE) in resource_actions
        assert (ResourceType.PERSONA, ActionType.READ) in resource_actions
        assert (ResourceType.PERSONA, ActionType.UPDATE) in resource_actions
    
    def test_get_permissions_multiple_roles(self, engine):
        """Test getting permissions for a user with multiple roles."""
        user = User(username="testuser", roles=["developer", "analyst"])
        engine.register_user(user)
        
        perms = engine.get_permissions(user.id)
        resource_actions = [(p.resource, p.action) for p in perms]
        
        # Developer permissions
        assert (ResourceType.PERSONA, ActionType.CREATE) in resource_actions
        # Analyst permissions
        assert (ResourceType.SYSTEM, ActionType.AUDIT) in resource_actions
    
    def test_get_permissions_inactive_user(self, engine):
        """Test that inactive users get no permissions."""
        user = User(username="testuser", roles=["admin"], is_active=False)
        engine.register_user(user)
        
        perms = engine.get_permissions(user.id)
        assert perms == []
    
    def test_check_permission_admin_granted(self, engine):
        """Test admin user has access to everything."""
        user = User(username="admin", roles=["admin"])
        engine.register_user(user)
        
        for resource in ResourceType:
            for action in ActionType:
                decision = engine.check_permission(user.id, resource, action)
                assert decision.granted is True, f"Failed for {resource}:{action}"
    
    def test_check_permission_developer_granted(self, engine):
        """Test developer has expected permissions."""
        user = User(username="dev", roles=["developer"])
        engine.register_user(user)
        
        # Should be granted
        decision = engine.check_permission(
            user.id, ResourceType.PERSONA, ActionType.CREATE
        )
        assert decision.granted is True
        
        decision = engine.check_permission(
            user.id, ResourceType.PERSONA, ActionType.UPDATE
        )
        assert decision.granted is True
    
    def test_check_permission_developer_denied(self, engine):
        """Test developer doesn't have unexpected permissions."""
        user = User(username="dev", roles=["developer"])
        engine.register_user(user)
        
        # Should be denied
        decision = engine.check_permission(
            user.id, ResourceType.PERSONA, ActionType.DELETE
        )
        assert decision.granted is False
        
        decision = engine.check_permission(
            user.id, ResourceType.SYSTEM, ActionType.MANAGE
        )
        assert decision.granted is False
    
    def test_check_permission_user_nonexistent(self, engine):
        """Test permission check for nonexistent user."""
        decision = engine.check_permission(
            "nonexistent", ResourceType.PERSONA, ActionType.READ
        )
        assert decision.granted is False
        assert "not found" in decision.reason.lower()
    
    def test_check_permission_inactive_user(self, engine):
        """Test permission check for inactive user."""
        user = User(username="inactive", roles=["admin"], is_active=False)
        engine.register_user(user)
        
        decision = engine.check_permission(
            user.id, ResourceType.PERSONA, ActionType.READ
        )
        assert decision.granted is False
        assert "inactive" in decision.reason.lower()
    
    def test_check_permission_with_owner_condition_pass(self, engine):
        """Test user role permission with owner condition satisfied."""
        user = User(username="regular", roles=["user"])
        engine.register_user(user)
        
        # Register resource owner
        resource_id = "persona_123"
        engine.register_resource_owner(resource_id, user.id)
        
        decision = engine.check_permission(
            user.id,
            ResourceType.PERSONA,
            ActionType.READ,
            context={"resource_id": resource_id}
        )
        assert decision.granted is True
    
    def test_check_permission_with_owner_condition_fail(self, engine):
        """Test user role permission with owner condition not satisfied."""
        user = User(username="regular", roles=["user"])
        engine.register_user(user)
        
        # Resource owned by different user
        resource_id = "persona_456"
        engine.register_resource_owner(resource_id, "other_user_id")
        
        decision = engine.check_permission(
            user.id,
            ResourceType.PERSONA,
            ActionType.READ,
            context={"resource_id": resource_id}
        )
        assert decision.granted is False
        assert "condition" in decision.reason.lower()
    
    def test_role_inheritance(self, engine):
        """Test role inheritance resolution."""
        # Create base role
        base_role = Role(
            name="base_role",
            description="Base role",
            permissions=[
                Permission(resource=ResourceType.PERSONA, action=ActionType.READ)
            ]
        )
        engine.register_role(base_role)
        
        # Create derived role
        derived_role = Role(
            name="derived_role",
            description="Derived role",
            permissions=[
                Permission(resource=ResourceType.PERSONA, action=ActionType.CREATE)
            ],
            inherits_from="base_role"
        )
        engine.register_role(derived_role)
        
        # User with derived role should have both permissions
        user = User(username="test", roles=["derived_role"])
        engine.register_user(user)
        
        perms = engine.get_permissions(user.id)
        resource_actions = [(p.resource, p.action) for p in perms]
        
        assert (ResourceType.PERSONA, ActionType.CREATE) in resource_actions
        assert (ResourceType.PERSONA, ActionType.READ) in resource_actions
    
    def test_circular_inheritance_detection(self, engine):
        """Test detection of circular inheritance."""
        # Create roles with circular inheritance
        role_a = Role(
            name="role_a",
            description="Role A",
            permissions=[
                Permission(resource=ResourceType.PERSONA, action=ActionType.READ)
            ],
            inherits_from="role_b"
        )
        engine.register_role(role_a)
        
        role_b = Role(
            name="role_b",
            description="Role B",
            permissions=[
                Permission(resource=ResourceType.PERSONA, action=ActionType.CREATE)
            ],
            inherits_from="role_a"
        )
        engine.register_role(role_b)
        
        # Should handle circular inheritance gracefully
        user = User(username="test", roles=["role_a"])
        engine.register_user(user)
        
        # Should still get direct permissions
        perms = engine.get_permissions(user.id)
        assert len(perms) >= 1
    
    def test_resource_ownership_management(self, engine):
        """Test resource ownership registration and retrieval."""
        resource_id = "persona_abc123"
        user_id = "user_xyz789"
        
        engine.register_resource_owner(resource_id, user_id)
        assert engine.get_resource_owner(resource_id) == user_id
        
        result = engine.unregister_resource_owner(resource_id)
        assert result is True
        assert engine.get_resource_owner(resource_id) is None
    
    def test_check_resource_access(self, engine):
        """Test resource-based access control."""
        user = User(username="regular", roles=["user"])
        engine.register_user(user)
        
        resource_id = "persona_test123"
        engine.register_resource_owner(resource_id, user.id)
        
        # Should grant access to owned resource
        decision = engine.check_resource_access(
            user.id, resource_id, ActionType.READ
        )
        assert decision.granted is True
    
    def test_check_resource_access_infers_type(self, engine):
        """Test resource type inference from resource ID."""
        user = User(username="admin", roles=["admin"])
        engine.register_user(user)
        
        # Resource ID with persona prefix
        decision = engine.check_resource_access(
            user.id, "persona_123", ActionType.READ
        )
        assert decision.granted is True
        
        # Resource ID with system prefix
        decision = engine.check_resource_access(
            user.id, "system_456", ActionType.READ
        )
        assert decision.granted is True
    
    def test_audit_logging(self, engine):
        """Test audit logging of access decisions."""
        user = User(username="test", roles=["developer"])
        engine.register_user(user)
        
        # Make some access decisions
        engine.check_permission(user.id, ResourceType.PERSONA, ActionType.READ)
        engine.check_permission(user.id, ResourceType.SYSTEM, ActionType.MANAGE)
        
        # Get audit log
        log = engine.get_audit_log()
        assert len(log) >= 2
        
        # Check log entries
        granted_entries = [d for d in log if d.granted]
        denied_entries = [d for d in log if not d.granted]
        
        assert len(granted_entries) >= 1
        assert len(denied_entries) >= 1
    
    def test_audit_log_filtering(self, engine):
        """Test audit log filtering options."""
        user1 = User(username="user1", roles=["admin"])
        user2 = User(username="user2", roles=["developer"])
        engine.register_user(user1)
        engine.register_user(user2)
        
        # Generate some audit entries
        engine.check_permission(user1.id, ResourceType.PERSONA, ActionType.READ)
        engine.check_permission(user2.id, ResourceType.SYSTEM, ActionType.MANAGE)
        
        # Filter by user
        user1_log = engine.get_audit_log(user_id=user1.id)
        assert all(d.user_id == user1.id for d in user1_log)
        
        # Filter by granted status
        granted_log = engine.get_audit_log(granted=True)
        assert all(d.granted for d in granted_log)
        
        denied_log = engine.get_audit_log(granted=False)
        assert all(not d.granted for d in denied_log)
    
    def test_audit_log_limit(self, engine):
        """Test audit log limit parameter."""
        user = User(username="test", roles=["admin"])
        engine.register_user(user)
        
        # Generate many entries
        for _ in range(20):
            engine.check_permission(user.id, ResourceType.PERSONA, ActionType.READ)
        
        # Test limit
        log = engine.get_audit_log(limit=5)
        assert len(log) == 5
    
    def test_clear_audit_log(self, engine):
        """Test clearing the audit log."""
        user = User(username="test", roles=["admin"])
        engine.register_user(user)
        
        engine.check_permission(user.id, ResourceType.PERSONA, ActionType.READ)
        assert len(engine.get_audit_log()) > 0
        
        count = engine.clear_audit_log()
        assert count > 0
        assert len(engine.get_audit_log()) == 0


class TestAccessDecision:
    """Tests for AccessDecision model."""
    
    def test_access_decision_creation(self):
        """Test access decision model creation."""
        decision = AccessDecision(
            user_id="user123",
            username="testuser",
            resource=ResourceType.PERSONA,
            action=ActionType.READ,
            granted=True,
            reason="Permission granted"
        )
        
        assert decision.user_id == "user123"
        assert decision.granted is True
        assert decision.decision_id is not None
        assert decision.evaluated_at is not None
    
    def test_access_decision_with_details(self):
        """Test access decision with all details."""
        decision = AccessDecision(
            user_id="user123",
            username="testuser",
            resource=ResourceType.PERSONA,
            action=ActionType.READ,
            resource_id="persona_456",
            granted=True,
            reason="Permission granted with conditions",
            matched_permissions=["persona:read"],
            conditions_evaluated={"owner_check": {"passed": True}}
        )
        
        assert decision.resource_id == "persona_456"
        assert len(decision.matched_permissions) == 1
        assert decision.conditions_evaluated is not None


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""
    
    def test_create_rbac_engine(self):
        """Test create_rbac_engine function."""
        engine = create_rbac_engine()
        assert isinstance(engine, RBACEngine)
        assert "admin" in engine.roles
    
    def test_create_user(self):
        """Test create_user convenience function."""
        user = create_user(
            username="testuser",
            roles=["developer"],
            attributes={"department": "engineering"}
        )
        
        assert user.username == "testuser"
        assert user.roles == ["developer"]
        assert user.attributes == {"department": "engineering"}


class TestFastAPIIntegration:
    """Tests for FastAPI integration (if available)."""
    
    def test_fastapi_imports_available(self):
        """Test that FastAPI integration is available."""
        try:
            from animus_core.rbac import get_rbac_engine, set_rbac_engine
            assert callable(get_rbac_engine)
            assert callable(set_rbac_engine)
        except ImportError:
            pytest.skip("FastAPI not installed")
    
    def test_global_rbac_engine(self):
        """Test global RBAC engine management."""
        try:
            from animus_core.rbac import get_rbac_engine, set_rbac_engine
            
            engine = RBACEngine()
            set_rbac_engine(engine)
            
            retrieved = get_rbac_engine()
            assert retrieved is engine
        except ImportError:
            pytest.skip("FastAPI not installed")


@pytest.mark.integration
class TestRBACIntegration:
    """Integration tests for RBAC system."""
    
    def test_full_workflow(self):
        """Test complete RBAC workflow."""
        engine = RBACEngine()
        
        # Create users with different roles
        admin = User(username="admin_user", roles=["admin"])
        developer = User(username="dev_user", roles=["developer"])
        analyst = User(username="analyst_user", roles=["analyst"])
        regular = User(username="regular_user", roles=["user"])
        
        engine.register_user(admin)
        engine.register_user(developer)
        engine.register_user(analyst)
        engine.register_user(regular)
        
        # Create a resource owned by regular user
        resource_id = "persona_123"
        engine.register_resource_owner(resource_id, regular.id)
        
        # Admin should have full access
        for action in ActionType:
            decision = engine.check_permission(
                admin.id, ResourceType.PERSONA, action
            )
            assert decision.granted, f"Admin should have {action}"
        
        # Developer should have create/read/update
        assert engine.check_permission(
            developer.id, ResourceType.PERSONA, ActionType.CREATE
        ).granted
        assert engine.check_permission(
            developer.id, ResourceType.PERSONA, ActionType.READ
        ).granted
        assert engine.check_permission(
            developer.id, ResourceType.PERSONA, ActionType.UPDATE
        ).granted
        assert not engine.check_permission(
            developer.id, ResourceType.PERSONA, ActionType.DELETE
        ).granted
        
        # Analyst should have read and audit
        assert engine.check_permission(
            analyst.id, ResourceType.PERSONA, ActionType.READ
        ).granted
        assert engine.check_permission(
            analyst.id, ResourceType.PERSONA, ActionType.AUDIT
        ).granted
        assert not engine.check_permission(
            analyst.id, ResourceType.PERSONA, ActionType.CREATE
        ).granted
        
        # Regular user should have read/execute on own resource
        assert engine.check_permission(
            regular.id, ResourceType.PERSONA, ActionType.READ,
            context={"resource_id": resource_id}
        ).granted
        assert engine.check_permission(
            regular.id, ResourceType.PERSONA, ActionType.EXECUTE,
            context={"resource_id": resource_id}
        ).granted
        assert not engine.check_permission(
            regular.id, ResourceType.PERSONA, ActionType.CREATE
        ).granted
    
    def test_role_change_affects_permissions(self):
        """Test that role changes immediately affect permissions."""
        engine = RBACEngine()
        user = User(username="test", roles=["user"])
        engine.register_user(user)
        
        # Initially limited permissions
        decision = engine.check_permission(
            user.id, ResourceType.PERSONA, ActionType.CREATE
        )
        assert not decision.granted
        
        # Grant developer role
        engine.grant_role(user.id, "developer")
        
        # Now should have create permission
        decision = engine.check_permission(
            user.id, ResourceType.PERSONA, ActionType.CREATE
        )
        assert decision.granted
        
        # Revoke developer role
        engine.revoke_role(user.id, "developer")
        
        # Should no longer have create permission
        decision = engine.check_permission(
            user.id, ResourceType.PERSONA, ActionType.CREATE
        )
        assert not decision.granted
    
    def test_complex_inheritance_chain(self):
        """Test multi-level role inheritance."""
        engine = RBACEngine()
        
        # Create inheritance chain: senior_dev -> developer -> viewer
        viewer = Role(
            name="viewer",
            description="Can only read",
            permissions=[
                Permission(resource=ResourceType.PERSONA, action=ActionType.READ)
            ]
        )
        engine.register_role(viewer)
        
        developer = Role(
            name="dev_plus",
            description="Developer plus",
            permissions=[
                Permission(resource=ResourceType.PERSONA, action=ActionType.CREATE),
                Permission(resource=ResourceType.PERSONA, action=ActionType.UPDATE)
            ],
            inherits_from="viewer"
        )
        engine.register_role(developer)
        
        senior = Role(
            name="senior_dev",
            description="Senior Developer",
            permissions=[
                Permission(resource=ResourceType.PERSONA, action=ActionType.DELETE)
            ],
            inherits_from="dev_plus"
        )
        engine.register_role(senior)
        
        # User with senior_dev should have all permissions
        user = User(username="senior", roles=["senior_dev"])
        engine.register_user(user)
        
        perms = engine.get_permissions(user.id)
        resource_actions = [(p.resource, p.action) for p in perms]
        
        assert (ResourceType.PERSONA, ActionType.READ) in resource_actions
        assert (ResourceType.PERSONA, ActionType.CREATE) in resource_actions
        assert (ResourceType.PERSONA, ActionType.UPDATE) in resource_actions
        assert (ResourceType.PERSONA, ActionType.DELETE) in resource_actions


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
