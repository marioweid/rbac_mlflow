import pytest
from httpx import ASGITransport, AsyncClient

from rbac_mlflow.main import app


@pytest.mark.asyncio
async def test_health_no_auth_required():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_me_requires_token():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/auth/me")
    assert resp.status_code == 401
    assert "Missing authentication token" in resp.text


@pytest.mark.asyncio
async def test_auth_me_invalid_token():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
    assert resp.status_code == 401
