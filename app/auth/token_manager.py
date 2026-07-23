"""JWT 令牌管理器 — 签发/验证/刷新。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from app.core.config import settings


class TokenManager:
    """JWT 令牌管理器。

    负责 access_token 和 refresh_token 的签发、验证和刷新。
    """

    def __init__(
        self,
        secret_key: str = "",
        access_token_expire_minutes: int = 15,
        refresh_token_expire_days: int = 7,
    ) -> None:
        """初始化令牌管理器。

        Args:
            secret_key: JWT 签名密钥。
            access_token_expire_minutes: Access Token 过期分钟数。
            refresh_token_expire_days: Refresh Token 过期天数。
        """
        self._secret_key = secret_key or settings.SECRET_KEY
        self._access_expire = access_token_expire_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self._refresh_expire = refresh_token_expire_days or settings.REFRESH_TOKEN_EXPIRE_DAYS
        self._algorithm = "HS256"

    def create_access_token(
        self,
        user_id: str,
        org_id: str = "",
        ws_id: str = "",
        permissions: list[str] | None = None,
    ) -> str:
        """签发 Access Token。

        Args:
            user_id: 用户 ID。
            org_id: 组织 ID。
            ws_id: 工作空间 ID。
            permissions: 权限列表。

        Returns:
            JWT Access Token 字符串。
        """
        now = datetime.now(UTC)
        expire = now + timedelta(minutes=self._access_expire)

        payload = {
            "sub": user_id,
            "org_id": org_id,
            "ws_id": ws_id,
            "permissions": permissions or [],
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "jti": str(uuid.uuid4()),
            "type": "access",
        }

        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def create_refresh_token(self, user_id: str) -> str:
        """签发 Refresh Token。

        Args:
            user_id: 用户 ID。

        Returns:
            JWT Refresh Token 字符串。
        """
        now = datetime.now(UTC)
        expire = now + timedelta(days=self._refresh_expire)

        payload = {
            "sub": user_id,
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "jti": str(uuid.uuid4()),
            "type": "refresh",
        }

        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def verify_token(self, token: str) -> dict | None:
        """验证 JWT Token 并解析 Payload。

        Args:
            token: JWT Token 字符串。

        Returns:
            Payload 字典。验证失败返回 None。
        """
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])
            return payload
        except JWTError:
            return None

    def refresh_access_token(self, refresh_token: str) -> str | None:
        """使用 Refresh Token 刷新 Access Token。

        Args:
            refresh_token: Refresh Token 字符串。

        Returns:
            新的 Access Token。Refresh Token 无效时返回 None。
        """
        payload = self.verify_token(refresh_token)
        if payload is None:
            return None

        # 验证是 refresh token
        if payload.get("type") != "refresh":
            return None

        user_id = payload.get("sub", "")
        if not user_id:
            return None

        return self.create_access_token(user_id)

    def get_user_id_from_token(self, token: str) -> str | None:
        """从 Token 中提取用户 ID。

        Args:
            token: JWT Token 字符串。

        Returns:
            用户 ID。验证失败返回 None。
        """
        payload = self.verify_token(token)
        if payload is None:
            return None
        return payload.get("sub")


# 全局单例
token_manager = TokenManager()
