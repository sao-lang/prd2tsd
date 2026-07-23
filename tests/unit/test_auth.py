"""Auth 单元测试 — JWT、权限检查。"""

from __future__ import annotations

from app.auth.permissions import PermissionChecker
from app.auth.token_manager import TokenManager

token_manager = TokenManager(
    secret_key="test-secret-key-for-unit-tests",
    access_token_expire_minutes=15,
    refresh_token_expire_days=7,
)
permission_checker = PermissionChecker()


def test_create_and_verify_access_token():
    """验证 Access Token 签发和验证。"""
    token = token_manager.create_access_token(
        user_id="user-1",
        org_id="org-1",
        ws_id="ws-1",
        permissions=["workspace:read", "prd:write"],
    )
    assert token is not None
    assert isinstance(token, str)

    payload = token_manager.verify_token(token)
    assert payload is not None
    assert payload["sub"] == "user-1"
    assert payload["org_id"] == "org-1"
    assert payload["ws_id"] == "ws-1"
    assert "workspace:read" in payload["permissions"]
    assert payload["type"] == "access"


def test_create_and_verify_refresh_token():
    """验证 Refresh Token 签发和验证。"""
    token = token_manager.create_refresh_token(user_id="user-1")
    assert token is not None

    payload = token_manager.verify_token(token)
    assert payload is not None
    assert payload["sub"] == "user-1"
    assert payload["type"] == "refresh"


def test_refresh_access_token():
    """验证使用 Refresh Token 刷新 Access Token。"""
    refresh_token = token_manager.create_refresh_token("user-1")
    new_access = token_manager.refresh_access_token(refresh_token)
    assert new_access is not None

    payload = token_manager.verify_token(new_access)
    assert payload is not None
    assert payload["sub"] == "user-1"
    assert payload["type"] == "access"


def test_invalid_token():
    """验证无效 Token 返回 None。"""
    payload = token_manager.verify_token("invalid-token")
    assert payload is None


def test_permission_check():
    """验证权限检查正确。"""
    user_permissions = ["workspace:read", "prd:write"]

    assert permission_checker.check_permission("workspace:read", user_permissions) is True
    assert permission_checker.check_permission("workspace:delete", user_permissions) is False


def test_has_any_permission():
    """验证任意权限检查（OR 逻辑）。"""
    user_permissions = ["workspace:read"]

    assert permission_checker.has_any_permission(
        ["workspace:read", "prd:write"], user_permissions
    ) is True
    assert permission_checker.has_any_permission(
        ["workspace:delete", "prd:write"], user_permissions
    ) is False


def test_get_role_permissions():
    """验证获取角色权限。"""
    admin_perms = permission_checker.get_role_permissions("admin")
    assert "workspace:create" in admin_perms
    assert "prd:delete" in admin_perms

    viewer_perms = permission_checker.get_role_permissions("viewer")
    assert "workspace:read" in viewer_perms
    assert "prd:create" not in viewer_perms
