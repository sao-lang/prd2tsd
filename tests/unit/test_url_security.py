"""URL 安全校验（SSRF 防护）单元测试。"""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from app.web_indexing.url_security import UrlSecurityError, validate_url


class TestValidateUrl:
    """validate_url SSRF 防护测试。"""

    @pytest.mark.parametrize("url", [
        "",
        "   ",
        "https://" + "a" * 5000,
    ])
    def test_rejects_empty_or_too_long(self, url: str) -> None:
        """验证空 URL 与超长 URL 被拒绝。"""
        with pytest.raises(UrlSecurityError):
            validate_url(url)

    @pytest.mark.parametrize("url", [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "gopher://example.com",
    ])
    def test_rejects_non_http_scheme(self, url: str) -> None:
        """验证非 http/https 协议被拒绝。"""
        with pytest.raises(UrlSecurityError):
            validate_url(url)

    @pytest.mark.parametrize("url", [
        "http://localhost:8000/x",
        "http://127.0.0.1/x",
        "http://0.0.0.0/x",
        "http://192.168.1.1/x",
        "http://10.0.0.1/x",
        "http://172.16.0.1/x",
        "http://172.31.255.254/x",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/x",
    ])
    def test_rejects_private_or_loopback(self, url: str) -> None:
        """验证环回/私网/链路本地/元数据地址被拦截。"""
        with pytest.raises(UrlSecurityError):
            validate_url(url)

    def test_accepts_public_ip(self) -> None:
        """验证公网 IP 被接受。"""
        assert validate_url("http://8.8.8.8/x") == "http://8.8.8.8/x"

    def test_accepts_public_hostname(self) -> None:
        """验证解析到公网的域名被接受。"""
        with patch.object(socket, "getaddrinfo", return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
        ]):
            assert validate_url("https://example.com/a") == "https://example.com/a"

    def test_rejects_hostname_resolving_to_private(self) -> None:
        """验证域名解析到内网地址被拦截（DNS rebinding 防护）。"""
        with (
            patch.object(socket, "getaddrinfo", return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
            ]),
            pytest.raises(UrlSecurityError, match="内网"),
        ):
            validate_url("https://evil.example.com/x")

    def test_rejects_hostname_resolve_failure(self) -> None:
        """验证域名解析失败被拒绝。"""
        with (
            patch.object(socket, "getaddrinfo", side_effect=socket.gaierror("nxdomain")),
            pytest.raises(UrlSecurityError, match="解析失败"),
        ):
            validate_url("https://nonexistent.example.com/x")

    def test_allow_private_flag(self) -> None:
        """验证 allow_private=True 时放行内网地址（测试/内网部署场景）。"""
        assert (
            validate_url("http://127.0.0.1/x", allow_private=True)
            == "http://127.0.0.1/x"
        )
        assert (
            validate_url("http://localhost:8000/x", allow_private=True)
            == "http://localhost:8000/x"
        )
