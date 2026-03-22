import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from rbac_mlflow.auth.providers.base import TokenClaims
from rbac_mlflow.db import get_db
from rbac_mlflow.main import app
from rbac_mlflow.rbac.dependencies import get_team_roles
from rbac_mlflow.rbac.schemas import TeamRole

TEAM_ALPHA_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
AUTH_HEADERS = {"Authorization": "Bearer fake-token"}


def _mock_db() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    return session


def _patch_auth(claims: TokenClaims):
    """Return a context manager that patches the auth middleware provider."""
    mock_provider = AsyncMock()
    mock_provider.validate_token.return_value = claims
    return patch(
        "rbac_mlflow.auth.middleware.get_auth_provider",
        return_value=mock_provider,
    )


@pytest.fixture(autouse=True)
def _clear_overrides() -> Generator[None]:
    yield
    app.dependency_overrides.clear()


class TestCreateTeam:
    @pytest.mark.asyncio
    async def test_owner_can_create(
        self,
        carol_claims: TokenClaims,
        carol_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db()

        def _refresh_team(obj):
            obj.id = uuid.uuid4()
            obj.created_at = datetime.now(UTC)

        db.refresh = AsyncMock(side_effect=_refresh_team)
        app.dependency_overrides[get_team_roles] = lambda: carol_team_roles
        app.dependency_overrides[get_db] = lambda: db

        with _patch_auth(carol_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.post("/admin/teams", json={"name": "new-team"}, headers=AUTH_HEADERS)
        assert resp.status_code == 201
        assert resp.json()["name"] == "new-team"

    @pytest.mark.asyncio
    async def test_reader_forbidden(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: _mock_db()

        with _patch_auth(alice_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.post("/admin/teams", json={"name": "new-team"}, headers=AUTH_HEADERS)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_duplicate_returns_409(
        self,
        carol_claims: TokenClaims,
        carol_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db()
        db.commit = AsyncMock(side_effect=IntegrityError("", {}, Exception()))
        app.dependency_overrides[get_team_roles] = lambda: carol_team_roles
        app.dependency_overrides[get_db] = lambda: db

        with _patch_auth(carol_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.post("/admin/teams", json={"name": "dup"}, headers=AUTH_HEADERS)
        assert resp.status_code == 409


class TestCreateMapping:
    @pytest.mark.asyncio
    async def test_owner_can_create(
        self,
        carol_claims: TokenClaims,
        carol_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db()
        db.refresh = AsyncMock(
            side_effect=lambda obj: setattr(obj, "id", uuid.uuid4()),
        )
        app.dependency_overrides[get_team_roles] = lambda: carol_team_roles
        app.dependency_overrides[get_db] = lambda: db

        with _patch_auth(carol_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.post(
                    f"/admin/teams/{TEAM_ALPHA_ID}/mappings",
                    json={"group_name": "/new-group", "role": "reader"},
                    headers=AUTH_HEADERS,
                )
        assert resp.status_code == 201
        data = resp.json()
        assert data["group_name"] == "/new-group"
        assert data["role"] == "reader"

    @pytest.mark.asyncio
    async def test_engineer_forbidden(
        self,
        bob_claims: TokenClaims,
        bob_team_roles: list[TeamRole],
    ) -> None:
        app.dependency_overrides[get_team_roles] = lambda: bob_team_roles
        app.dependency_overrides[get_db] = lambda: _mock_db()

        with _patch_auth(bob_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.post(
                    f"/admin/teams/{TEAM_ALPHA_ID}/mappings",
                    json={"group_name": "/new-group", "role": "reader"},
                    headers=AUTH_HEADERS,
                )
        assert resp.status_code == 403


class TestDeleteMapping:
    @pytest.mark.asyncio
    async def test_owner_can_delete(
        self,
        carol_claims: TokenClaims,
        carol_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db()
        mock_result = MagicMock(rowcount=1)
        db.execute = AsyncMock(return_value=mock_result)
        app.dependency_overrides[get_team_roles] = lambda: carol_team_roles
        app.dependency_overrides[get_db] = lambda: db

        mapping_id = uuid.uuid4()
        with _patch_auth(carol_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.delete(
                    f"/admin/teams/{TEAM_ALPHA_ID}/mappings/{mapping_id}",
                    headers=AUTH_HEADERS,
                )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_not_found_returns_404(
        self,
        carol_claims: TokenClaims,
        carol_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db()
        mock_result = MagicMock(rowcount=0)
        db.execute = AsyncMock(return_value=mock_result)
        app.dependency_overrides[get_team_roles] = lambda: carol_team_roles
        app.dependency_overrides[get_db] = lambda: db

        mapping_id = uuid.uuid4()
        with _patch_auth(carol_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.delete(
                    f"/admin/teams/{TEAM_ALPHA_ID}/mappings/{mapping_id}",
                    headers=AUTH_HEADERS,
                )
        assert resp.status_code == 404


class TestLinkExperiment:
    @pytest.mark.asyncio
    async def test_owner_can_link(
        self,
        carol_claims: TokenClaims,
        carol_team_roles: list[TeamRole],
    ) -> None:
        app.dependency_overrides[get_team_roles] = lambda: carol_team_roles
        app.dependency_overrides[get_db] = lambda: _mock_db()

        with _patch_auth(carol_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.post(
                    f"/admin/teams/{TEAM_ALPHA_ID}/experiments",
                    json={"mlflow_experiment_id": "exp-123"},
                    headers=AUTH_HEADERS,
                )
        assert resp.status_code == 201
        assert resp.json()["mlflow_experiment_id"] == "exp-123"


class TestUnlinkExperiment:
    @pytest.mark.asyncio
    async def test_owner_can_unlink(
        self,
        carol_claims: TokenClaims,
        carol_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db()
        mock_result = MagicMock(rowcount=1)
        db.execute = AsyncMock(return_value=mock_result)
        app.dependency_overrides[get_team_roles] = lambda: carol_team_roles
        app.dependency_overrides[get_db] = lambda: db

        with _patch_auth(carol_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.delete(
                    f"/admin/teams/{TEAM_ALPHA_ID}/experiments/exp-123",
                    headers=AUTH_HEADERS,
                )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_not_found_returns_404(
        self,
        carol_claims: TokenClaims,
        carol_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db()
        mock_result = MagicMock(rowcount=0)
        db.execute = AsyncMock(return_value=mock_result)
        app.dependency_overrides[get_team_roles] = lambda: carol_team_roles
        app.dependency_overrides[get_db] = lambda: db

        with _patch_auth(carol_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.delete(
                    f"/admin/teams/{TEAM_ALPHA_ID}/experiments/exp-999",
                    headers=AUTH_HEADERS,
                )
        assert resp.status_code == 404
