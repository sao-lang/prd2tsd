"""调试登录问题。"""
import httpx, asyncio

async def main():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8006") as c:
        r = await c.post("/api/v1/auth/register", json={
            "email": "debug@test.com", "password": "test123456", "display_name": "调试"
        })
        print(f"注册: {r.status_code} {r.text[:200]}")
        
        r = await c.post("/api/v1/auth/login", json={
            "email": "debug@test.com", "password": "test123456"
        })
        print(f"登录: {r.status_code} {r.text[:300]}")

asyncio.run(main())
