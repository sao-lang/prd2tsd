"""自定义异常基类。"""

from __future__ import annotations


class Prd2TsdError(Exception):
    """应用基础异常。"""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500) -> None:
        """初始化异常。

        Args:
            message: 错误描述。
            code: 错误码。
            status_code: HTTP 状态码。
        """
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(self.message)


class NotFoundError(Prd2TsdError):
    """资源不存在异常。"""

    def __init__(self, message: str = "资源不存在", code: str = "NOT_FOUND") -> None:
        super().__init__(message=message, code=code, status_code=404)


class AuthenticationError(Prd2TsdError):
    """认证失败异常。"""

    def __init__(self, message: str = "认证失败", code: str = "AUTH_FAILED") -> None:
        super().__init__(message=message, code=code, status_code=401)


class PermissionDeniedError(Prd2TsdError):
    """权限不足异常。"""

    def __init__(self, message: str = "权限不足", code: str = "PERMISSION_DENIED") -> None:
        super().__init__(message=message, code=code, status_code=403)


class ValidationError(Prd2TsdError):
    """数据验证失败异常。"""

    def __init__(self, message: str = "数据验证失败", code: str = "VALIDATION_ERROR") -> None:
        super().__init__(message=message, code=code, status_code=400)


class ServiceConnectionError(Prd2TsdError):
    """基础设施连接失败异常。"""

    def __init__(self, message: str = "服务连接失败", code: str = "CONNECTION_ERROR") -> None:
        super().__init__(message=message, code=code, status_code=503)
