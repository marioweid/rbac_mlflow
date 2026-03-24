import uuid
from collections.abc import Generator
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from rbac_mlflow.auth.providers.base import TokenClaims
from rbac_mlflow.db import get_db
from rbac_mlflow.main import app
from rbac_mlflow.rbac.dependencies import get_team_roles
from rbac_mlflow.rbac.schemas import TeamRole
from rbac_mlflow.s3_client import get_s3_client

TEAM_ALPHA_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEAM_BETA_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
DATASET_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
AUTH_HEADERS = {"Authorization": "Bearer fake-token"}

NOW = datetime(2026, 3, 23, 12, 0, 0)

SAMPLE_DATASET = MagicMock()
SAMPLE_DATASET.id = DATASET_ID
SAMPLE_DATASET.name = "rag-eval"
SAMPLE_DATASET.team_id = TEAM_ALPHA_ID
SAMPLE_DATASET.description = "Golden sample"
SAMPLE_DATASET.is_active = True
SAMPLE_DATASET.created_at = NOW

SAMPLE_VERSION = MagicMock()
SAMPLE_VERSION.id = uuid.uuid4()
SAMPLE_VERSION.dataset_id = DATASET_ID
SAMPLE_VERSION.version = 1
SAMPLE_VERSION.s3_key = "datasets/team-alpha/rag-eval/v1/data.jsonl"
SAMPLE_VERSION.row_count = 8
SAMPLE_VERSION.created_by = "alice-id"
SAMPLE_VERSION.created_at = NOW

SAMPLE_ROWS = [
    {"inputs": {"question": "What is 2+2?"}, "expectations": {"expected_response": "4"}}
]


def _mock_s3(rows: list[dict] | None = None) -> AsyncMock:
    s3 = AsyncMock()
    s3.upload_jsonl = AsyncMock(return_value=None)
    s3.download_jsonl = AsyncMock(return_value=rows or SAMPLE_ROWS)
    return s3


def _mock_db_for_list(datasets: list) -> AsyncMock:
    """Mock DB that returns dataset rows for list_datasets queries."""
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = datasets
    db.execute = AsyncMock(return_value=result)
    return db


def _mock_db_for_detail(team_id: uuid.UUID | None = TEAM_ALPHA_ID) -> AsyncMock:
    """Mock DB for single-dataset queries (permission check + detail)."""
    db = AsyncMock()

    call_count = 0

    async def execute_side_effect(_stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()

        if call_count == 1:
            # require_dataset_permission query: Dataset.team_id
            row = MagicMock()
            row.team_id = team_id
            result.first.return_value = row if team_id is not None else None
        elif call_count == 2:
            # get_dataset_detail: select(Dataset)
            result.scalar_one_or_none.return_value = SAMPLE_DATASET
        elif call_count == 3:
            # get_dataset_detail: select(DatasetVersion)
            result.scalars.return_value.all.return_value = [SAMPLE_VERSION]
        else:
            result.first.return_value = None
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = []

        return result

    db.execute = AsyncMock(side_effect=execute_side_effect)
    return db


def _mock_db_for_write(team_id: uuid.UUID = TEAM_ALPHA_ID) -> AsyncMock:
    """Mock DB for create/update/delete write operations."""
    db = AsyncMock()

    call_count = 0

    async def execute_side_effect(_stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()

        if call_count == 1:
            # require_dataset_permission or team resolution
            row = MagicMock()
            row.team_id = team_id
            result.first.return_value = row
        elif call_count == 2:
            # update_dataset: select(Dataset)
            result.scalar_one_or_none.return_value = SAMPLE_DATASET
        elif call_count == 3:
            # update_dataset: max version query
            result.scalar.return_value = 1
        else:
            result.scalar.return_value = None
            result.scalar_one_or_none.return_value = None

        return result

    db.execute = AsyncMock(side_effect=execute_side_effect)
    db.flush = AsyncMock(return_value=None)
    db.commit = AsyncMock(return_value=None)
    db.add = MagicMock()
    return db


def _patch_auth(claims: TokenClaims):
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


class TestListDatasets:
    async def test_reader_sees_own_team_datasets(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        row = MagicMock()
        row.Dataset = SAMPLE_DATASET
        row.latest_version = 1
        row.row_count = 8
        row.updated_at = NOW

        db = _mock_db_for_list([row])
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db

        with _patch_auth(alice_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.get("/datasets", headers=AUTH_HEADERS)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "rag-eval"
        assert data[0]["team_name"] == "team-alpha"

    async def test_user_with_no_teams_sees_empty(
        self,
        alice_claims: TokenClaims,
    ) -> None:
        app.dependency_overrides[get_team_roles] = lambda: []
        app.dependency_overrides[get_db] = lambda: AsyncMock()

        with _patch_auth(alice_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.get("/datasets", headers=AUTH_HEADERS)

        assert resp.status_code == 200
        assert resp.json() == []

    async def test_team_beta_cannot_see_team_alpha_datasets(
        self,
        dave_claims: TokenClaims,
        dave_team_roles: list[TeamRole],
    ) -> None:
        # DB returns empty list when filtering by team-beta IDs
        db = _mock_db_for_list([])
        app.dependency_overrides[get_team_roles] = lambda: dave_team_roles
        app.dependency_overrides[get_db] = lambda: db

        with _patch_auth(dave_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.get("/datasets", headers=AUTH_HEADERS)

        assert resp.status_code == 200
        assert resp.json() == []


class TestGetDataset:
    async def test_reader_can_view_detail(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_detail(TEAM_ALPHA_ID)
        s3 = _mock_s3()
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_s3_client] = lambda: s3

        with _patch_auth(alice_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.get(f"/datasets/{DATASET_ID}", headers=AUTH_HEADERS)

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "rag-eval"
        assert data["team_name"] == "team-alpha"
        assert len(data["versions"]) == 1
        assert data["versions"][0]["version"] == 1

    async def test_unknown_dataset_returns_404(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_detail(None)  # team_id=None → dataset not found
        s3 = _mock_s3()
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_s3_client] = lambda: s3

        with _patch_auth(alice_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.get(
                    f"/datasets/{uuid.uuid4()}", headers=AUTH_HEADERS
                )

        assert resp.status_code == 404

    async def test_reader_cannot_access_other_team_dataset(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        # Dataset belongs to team-beta; alice only has team-alpha
        db = _mock_db_for_detail(TEAM_BETA_ID)
        s3 = _mock_s3()
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_s3_client] = lambda: s3

        with _patch_auth(alice_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.get(f"/datasets/{DATASET_ID}", headers=AUTH_HEADERS)

        assert resp.status_code == 403


class TestCreateDataset:
    async def test_reader_cannot_create_dataset(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        db = AsyncMock()
        s3 = _mock_s3()
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_s3_client] = lambda: s3

        with _patch_auth(alice_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.post(
                    "/datasets",
                    json={
                        "name": "new-ds",
                        "team_name": "team-alpha",
                        "rows": SAMPLE_ROWS,
                    },
                    headers=AUTH_HEADERS,
                )

        assert resp.status_code == 403

    async def test_engineer_can_create_dataset(
        self,
        bob_claims: TokenClaims,
        bob_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_write(TEAM_ALPHA_ID)
        s3 = _mock_s3()
        app.dependency_overrides[get_team_roles] = lambda: bob_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_s3_client] = lambda: s3

        with _patch_auth(bob_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.post(
                    "/datasets",
                    json={
                        "name": "new-ds",
                        "team_name": "team-alpha",
                        "rows": SAMPLE_ROWS,
                    },
                    headers=AUTH_HEADERS,
                )

        assert resp.status_code == 201
        s3.upload_jsonl.assert_called_once()


class TestUpdateDataset:
    async def test_reader_cannot_update_dataset(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        # Dataset in team-alpha, alice is a reader → DATASET_WRITE denied
        db = _mock_db_for_detail(TEAM_ALPHA_ID)
        s3 = _mock_s3()
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_s3_client] = lambda: s3

        with _patch_auth(alice_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.put(
                    f"/datasets/{DATASET_ID}",
                    json={"rows": SAMPLE_ROWS},
                    headers=AUTH_HEADERS,
                )

        assert resp.status_code == 403

    async def test_engineer_can_update_dataset(
        self,
        bob_claims: TokenClaims,
        bob_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_write(TEAM_ALPHA_ID)
        s3 = _mock_s3()
        app.dependency_overrides[get_team_roles] = lambda: bob_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_s3_client] = lambda: s3

        with _patch_auth(bob_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.put(
                    f"/datasets/{DATASET_ID}",
                    json={"rows": SAMPLE_ROWS},
                    headers=AUTH_HEADERS,
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 2  # max was 1, new version is 2
        s3.upload_jsonl.assert_called_once()


class TestDeleteDataset:
    async def test_reader_cannot_delete_dataset(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_detail(TEAM_ALPHA_ID)
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db

        with _patch_auth(alice_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.delete(
                    f"/datasets/{DATASET_ID}", headers=AUTH_HEADERS
                )

        assert resp.status_code == 403

    async def test_engineer_can_delete_dataset(
        self,
        bob_claims: TokenClaims,
        bob_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_write(TEAM_ALPHA_ID)
        app.dependency_overrides[get_team_roles] = lambda: bob_team_roles
        app.dependency_overrides[get_db] = lambda: db

        with _patch_auth(bob_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.delete(
                    f"/datasets/{DATASET_ID}", headers=AUTH_HEADERS
                )

        assert resp.status_code == 204
