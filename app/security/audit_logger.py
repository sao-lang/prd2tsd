"""审计日志 — 哈希链不可篡改。"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass
class AuditLogEntry:
    """审计日志条目。"""

    id: str
    action: str
    resource: str
    resource_id: str
    user_id: str
    org_id: str
    workspace_id: str
    detail: dict[str, Any]
    previous_hash: str
    current_hash: str
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。

        Returns:
            字典表示。
        """
        return {
            "id": self.id,
            "action": self.action,
            "resource": self.resource,
            "resource_id": self.resource_id,
            "user_id": self.user_id,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "detail": self.detail,
            "previous_hash": self.previous_hash,
            "current_hash": self.current_hash,
            "timestamp": self.timestamp.isoformat(),
        }


class AuditLogger:
    """审计日志记录器 — 哈希链不可篡改。

    每条日志包含前一条日志的哈希值，形成哈希链。
    篡改任意一条日志都会导致链断裂，可被检测。
    注意：当前使用内存存储（self._entries），重启后日志丢失。
    生产环境需迁移到 PostgreSQL 持久化。
    """
    # PRODUCTION: 生产环境需迁移到 PostgreSQL 持久化存储

    def __init__(self) -> None:
        """初始化审计日志记录器。"""
        self._entries: list[AuditLogEntry] = []
        self._last_hash = hashlib.sha256(b"genesis").hexdigest()

    async def log(
        self,
        action: str,
        resource: str,
        resource_id: str,
        user_id: str,
        org_id: str = "",
        workspace_id: str = "",
        detail: dict[str, Any] | None = None,
    ) -> AuditLogEntry:
        """记录一条审计日志。

        Args:
            action: 操作类型（create / read / update / delete）。
            resource: 资源类型（workspace / user / document）。
            resource_id: 资源 ID。
            user_id: 操作用户 ID。
            org_id: 组织 ID。
            workspace_id: 工作空间 ID。
            detail: 操作详情。

        Returns:
            创建的审计日志条目。
        """
        entry_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        entry_data = {
            "id": entry_id,
            "action": action,
            "resource": resource,
            "resource_id": resource_id,
            "user_id": user_id,
            "org_id": org_id,
            "workspace_id": workspace_id,
            "detail": detail or {},
            "previous_hash": self._last_hash,
            "timestamp": now.isoformat(),
        }

        # 计算当前哈希
        current_hash = self._compute_hash(entry_data)
        entry_data["current_hash"] = current_hash

        entry = AuditLogEntry(
            id=entry_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            user_id=user_id,
            org_id=org_id,
            workspace_id=workspace_id,
            detail=detail or {},
            previous_hash=self._last_hash,
            current_hash=current_hash,
            timestamp=now,
        )

        self._entries.append(entry)
        self._last_hash = current_hash
        return entry

    def get_entries(self, limit: int = 100) -> list[AuditLogEntry]:
        """获取审计日志条目。

        Args:
            limit: 返回条目数上限。

        Returns:
            审计日志条目列表，按时间倒序。
        """
        return sorted(self._entries, key=lambda e: e.timestamp, reverse=True)[:limit]

    def verify_hash_chain(self) -> bool:
        """验证哈希链完整性。

        Returns:
            True 表示未被篡改，False 表示检测到篡改。
        """
        if not self._entries:
            return True

        sorted_entries = sorted(self._entries, key=lambda e: e.timestamp)

        # 验证第一条日志的前置哈希
        if sorted_entries[0].previous_hash != hashlib.sha256(b"genesis").hexdigest():
            return False

        prev_hash = sorted_entries[0].current_hash

        for entry in sorted_entries[1:]:
            if entry.previous_hash != prev_hash:
                return False

            # 重新计算哈希验证
            entry_data = {
                "id": entry.id,
                "action": entry.action,
                "resource": entry.resource,
                "resource_id": entry.resource_id,
                "user_id": entry.user_id,
                "org_id": entry.org_id,
                "workspace_id": entry.workspace_id,
                "detail": entry.detail,
                "previous_hash": entry.previous_hash,
                "timestamp": entry.timestamp.isoformat(),
            }
            if self._compute_hash(entry_data) != entry.current_hash:
                return False

            prev_hash = entry.current_hash

        return True

    def clear(self) -> None:
        """清除所有审计日志。"""
        self._entries.clear()
        self._last_hash = hashlib.sha256(b"genesis").hexdigest()

    @staticmethod
    def _compute_hash(data: dict[str, Any]) -> str:
        """计算日志条目的 SHA-256 哈希。

        Args:
            data: 日志条目数据。

        Returns:
            十六进制哈希字符串。
        """
        serialized = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()


# 全局单例
audit_logger = AuditLogger()
