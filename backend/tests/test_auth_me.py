from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from rbac_mlflow.auth.providers.base import TokenClaims
from rbac_mlflow.main import app


@pytest.mark.asyncio
async def test_auth_me_with_valid_token():
    fake_claims = TokenClaims(
        sub="alice-id",
        email="alice@example.com",
        groups=["/team-alpha/readers"],
    )

    with patch("rbac_mlflow.auth.middleware.get_auth_provider") as mock_get:
        mock_provider = AsyncMock()
        mock_provider.validate_token.return_value = fake_claims
        mock_get.return_value = mock_provider

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/auth/me",
                headers={"Authorization": "Bearer fake-valid-token"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["sub"] == "alice-id"
    assert data["email"] == "alice@example.com"
    assert data["groups"] == ["/team-alpha/readers"]
