"""RBAC enforcer — Check(user, action, resource)."""

from aura_sdk.models.governance import ROLE_PERMISSIONS, Permission, Role


class RBACEnforcer:
    """Enforces role-based access control."""

    @staticmethod
    def check(role: Role | str, permission: Permission | str) -> bool:
        """Check if a role has a permission.

        Args:
            role: Role enum or string.
            permission: Permission enum or string.

        Returns:
            True if the role has the permission.
        """
        if isinstance(role, str):
            role = Role(role)
        if isinstance(permission, str):
            permission = Permission(permission)
        return permission in ROLE_PERMISSIONS.get(role, [])

    @staticmethod
    def check_any(role: Role | str, permissions: list[Permission | str]) -> bool:
        """Check if a role has any of the permissions."""
        return any(RBACEnforcer.check(role, p) for p in permissions)

    @staticmethod
    def list_permissions(role: Role | str) -> list[Permission]:
        """List all permissions for a role."""
        if isinstance(role, str):
            role = Role(role)
        return list(ROLE_PERMISSIONS.get(role, []))
