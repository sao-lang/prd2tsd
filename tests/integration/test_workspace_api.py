"""工作空间 API 集成测试。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_health_check():
    """验证健康检查接口。"""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")


@pytest.mark.asyncio
async def test_root_endpoint():
    """验证根路径。"""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "app" in data
        assert "version" in data
