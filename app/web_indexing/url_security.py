"""URL 安全校验 — SSRF 防护（协议白名单 + 内网地址拦截）。

Block E B2：URL 文档分析前置安全校验。
- 协议白名单：仅允许 http/https
- 主机名检查：环回、本机、私网、链路本地、保留、组播地址一律拦截
- DNS 解析后二次检查解析到的所有 IP（防域名指向内网）
- URL 长度限制

注：DNS 解析为阻塞操作，调用方应通过 `asyncio.to_thread` 在事件循环外执行。
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = ("http", "https")
MAX_URL_LENGTH = 4096

# 环回/本机主机名（大小写不敏感）
_LOCALHOST_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost"}


class UrlSecurityError(ValueError):
    """URL 校验失败（协议非法 / 指向内网 / 解析失败）。"""


def validate_url(url: str, *, allow_private: bool = False) -> str:
    """校验 URL 并防 SSRF。

    Args:
        url: 待校验 URL。
        allow_private: 是否允许内网地址（默认 False，禁止）。

    Returns:
        规范化后的 URL。

    Raises:
        UrlSecurityError: URL 为空/过长/协议非法/指向内网/解析失败。
    """
    if not url or not url.strip():
        raise UrlSecurityError("URL 不能为空")
    if len(url) > MAX_URL_LENGTH:
        raise UrlSecurityError(f"URL 过长（超过 {MAX_URL_LENGTH} 字符）")

    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UrlSecurityError(f"不支持的协议: {parsed.scheme or '无'}（仅允许 http/https）")
    if not parsed.hostname:
        raise UrlSecurityError("URL 缺少主机名")

    if not allow_private:
        _assert_public_host(parsed.hostname)

    return url


def _is_private_ip(ip: str) -> bool:
    """判断 IP 是否为内网/环回/保留等不可公开访问地址。

    Args:
        ip: IP 地址字符串。

    Returns:
        是否应拦截。
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _assert_public_host(hostname: str) -> None:
    """断言主机名解析结果全部为公网地址。

    Args:
        hostname: 主机名或 IP 字面量。

    Raises:
        UrlSecurityError: 主机名指向本机/内网/保留地址，或解析失败。
    """
    lowered = hostname.lower()
    if lowered in _LOCALHOST_NAMES:
        raise UrlSecurityError(f"禁止访问本机地址: {hostname}")

    # IP 字面量直接检查（try/else 避免 except 捕获自身抛出的 UrlSecurityError）
    try:
        ipaddress.ip_address(hostname)  # 非 IP 字面量会抛 ValueError
    except ValueError:
        pass  # 非 IP 字面量，走域名解析
    else:
        if _is_private_ip(hostname):
            raise UrlSecurityError(f"禁止访问内网地址: {hostname}")
        return

    # DNS 解析并检查所有结果（防域名解析到内网）
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UrlSecurityError(f"域名解析失败: {hostname}") from exc
    if not infos:
        raise UrlSecurityError(f"域名无解析结果: {hostname}")

    for info in infos:
        resolved_ip = str(info[4][0])
        if _is_private_ip(resolved_ip):
            raise UrlSecurityError(f"域名解析到内网地址: {hostname} -> {resolved_ip}")
