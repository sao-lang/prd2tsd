"""模型配置 API 集成测试。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_get_all_configs():
    """GET /api/v1/model-config 返回所有模型配置，API Key 被掩码。"""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/model-config")
        assert response.status_code == 200
        data = response.json()
        assert "llm" in data
        assert "embedding" in data


@pytest.mark.asyncio
async def test_update_config():
    """PUT /api/v1/model-config 修改配置后后续查询返回新值。"""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put("/api/v1/model-config", json={
            "type": "llm",
            "provider": "deepseek",
            "base_url": "https://custom.deepseek.com/v1",
        })
        assert response.status_code == 200

        # 验证已生效
        get_resp = await client.get("/api/v1/model-config?type=llm&provider=deepseek")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert "custom.deepseek.com" in data.get("base_url", "")


@pytest.mark.asyncio
async def test_update_routing_rule():
    """PUT /api/v1/model-config/routing 修改路由规则。"""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put("/api/v1/model-config/routing", json={
            "task_type": "analysis.requirement",
            "provider": "openai",
            "model": "gpt-4o",
        })
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_reset_runtime_config():
    """DELETE /api/v1/model-config/runtime 清除运行时配置。"""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/api/v1/model-config/runtime")
        assert resp.status_code == 200
