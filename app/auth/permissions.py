"""权限检查器 — RBAC + ABAC。"""

from __future__ import annotations

# 预定义的系统权限
SYSTEM_PERMISSIONS: dict[str, list[str]] = {
    "admin": [
        "workspace:create",
        "workspace:read",
        "workspace:update",
        "workspace:delete",
        "workspace:manage_members",
        "prd:create",
        "prd:read",
        "prd:update",
        "prd:delete",
        "model_config:read",
        "model_config:update",
    ],
    "editor": [
        "workspace:read",
        "prd:create",
        "prd:read",
        "prd:update",
    ],
    "viewer": [
        "workspace:read",
        "prd:read",
    ],
}


class PermissionChecker:
    """权限检查器。

    支持 RBAC（基于角色的权限检查）和简单的 ABAC（基于属性的权限检查）。
    """

    def __init__(self) -> None:
        """初始化权限检查器。"""
        self._role_permissions = SYSTEM_PERMISSIONS.copy()

    def check_permission(
        self,
        required: str,
        user_permissions: list[str],
    ) -> bool:
        """检查用户是否拥有指定权限。

        Args:
            required: 所需权限名。
            user_permissions: 用户拥有的权限列表。

        Returns:
            是否有权限。
        """
        return required in user_permissions

    def get_role_permissions(self, role_name: str) -> list[str]:
        """获取角色的预定义权限列表。

        Args:
            role_name: 角色名。

        Returns:
            权限列表。角色不存在时返回空列表。
        """
        return self._role_permissions.get(role_name, [])

    def check_workspace_access(
        self,
        user_id: str,
        workspace_id: str,
        user_workspaces: list[str],
    ) -> bool:
        """检查用户是否有权访问某工作空间。

        Args:
            user_id: 用户 ID。
            workspace_id: 工作空间 ID。
            user_workspaces: 用户所属的工作空间 ID 列表。

        Returns:
            是否有访问权限。
        """
        return workspace_id in user_workspaces

    def has_any_permission(
        self,
        required: list[str],
        user_permissions: list[str],
    ) -> bool:
        """检查用户是否拥有任意一项权限（OR 逻辑）。

        Args:
            required: 所需权限列表（满足其一即可）。
            user_permissions: 用户拥有的权限列表。

        Returns:
            是否有至少一项权限。
        """
        return any(p in user_permissions for p in required)


# 全局单例
permission_checker = PermissionChecker()
