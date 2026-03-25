import json
import uuid
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from rbac_mlflow.auth.providers.base import TokenClaims
from rbac_mlflow.db import get_db
from rbac_mlflow.main import app
from rbac_mlflow.mlflow_client import get_mlflow_client
from rbac_mlflow.rbac.dependencies import get_team_roles
from rbac_mlflow.rbac.schemas import TeamRole

TEAM_ALPHA_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEAM_BETA_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
DATASET_ID = "d-dddddddddddd4a24a60dc53189b6eccb"
EXPERIMENT_ID = "42"
AUTH_HEADERS = {"Authorization": "Bearer fake-token"}

SAMPLE_ROWS = [
    {"inputs": {"question": "What is 2+2?"}, "expectations": {"expected_response": "4"}}
]

MLFLOW_DATASET = {
    "dataset_id": DATASET_ID,
    "name": "rag-eval",
    "tags": json.dumps({"description": "Golden sample", "row_count": "1"}),
    "digest": "abc123",
    "created_time": 1774400000000,
    "last_update_time": 1774400000000,
}

MLFLOW_RECORDS = json.dumps([
    {
        "dataset_record_id": "dr-aabbcc",
        "dataset_id": DATASET_ID,
        **SAMPLE_ROWS[0],
        "outputs": {},
        "tags": {},
    }
])


def _mock_mlflow_for_list() -> AsyncMock:
    """MLflow client that returns a dataset list on search."""
    import httpx

    client = AsyncMock(spec=httpx.AsyncClient)

    def make_resp(data: dict) -> MagicMock:
        r = MagicMock()
        r.is_success = True
        r.status_code = 200
        r.json.return_value = data
        r.text = ""
        return r

    async def post_side(url: str, **kwargs) -> MagicMock:
        if "datasets/search" in url:
            return make_resp({"datasets": [MLFLOW_DATASET]})
        return make_resp({})

    client.post = AsyncMock(side_effect=post_side)
    client.get = AsyncMock(return_value=make_resp({}))
    return client


def _mock_mlflow_for_detail(found: bool = True) -> AsyncMock:
    """MLflow client for single-dataset GET (experiment-ids check + dataset + records)."""
    import httpx

    client = AsyncMock(spec=httpx.AsyncClient)

    def make_resp(data: dict, status: int = 200) -> MagicMock:
        r = MagicMock()
        r.is_success = status < 400
        r.status_code = status
        r.json.return_value = data
        r.text = ""
        return r

    async def get_side(url: str, **kwargs) -> MagicMock:
        if "experiment-ids" in url:
            return make_resp({"experiment_ids": [EXPERIMENT_ID] if found else []})
        if "records" in url:
            return make_resp({"records": MLFLOW_RECORDS})
        # dataset detail
        if found:
            return make_resp({"dataset": MLFLOW_DATASET})
        return make_resp({"error_code": "RESOURCE_DOES_NOT_EXIST"}, 404)

    client.get = AsyncMock(side_effect=get_side)
    client.post = AsyncMock(return_value=make_resp({}))
    return client


def _mock_mlflow_for_write() -> AsyncMock:
    """MLflow client for create/update/delete write operations."""
    import httpx

    client = AsyncMock(spec=httpx.AsyncClient)

    def make_resp(data: dict, status: int = 200) -> MagicMock:
        r = MagicMock()
        r.is_success = status < 400
        r.status_code = status
        r.json.return_value = data
        r.text = ""
        return r

    async def post_side(url: str, **kwargs) -> MagicMock:
        if "datasets/create" in url:
            return make_resp({"dataset": MLFLOW_DATASET})
        if "records" in url:
            return make_resp({"inserted_count": 1, "updated_count": 0})
        if "datasets/search" in url:
            return make_resp({"datasets": [MLFLOW_DATASET]})
        return make_resp({})

    async def get_side(url: str, **kwargs) -> MagicMock:
        if "experiment-ids" in url:
            return make_resp({"experiment_ids": [EXPERIMENT_ID]})
        if "records" in url:
            return make_resp({"records": MLFLOW_RECORDS})
        return make_resp({"dataset": MLFLOW_DATASET})

    async def delete_side(url: str, **kwargs) -> MagicMock:
        if "records" in url:
            return make_resp({"deleted_count": 1})
        return make_resp({})

    async def patch_side(url: str, **kwargs) -> MagicMock:
        return make_resp({})

    client.post = AsyncMock(side_effect=post_side)
    client.get = AsyncMock(side_effect=get_side)
    client.delete = AsyncMock(side_effect=delete_side)
    client.patch = AsyncMock(side_effect=patch_side)
    return client


def _mock_db_for_permission(team_id: uuid.UUID) -> AsyncMock:
    """Minimal DB mock for RBAC permission check only."""
    db = AsyncMock()

    async def execute_side(_stmt):
        result = MagicMock()
        row = MagicMock()
        row.team_id = team_id
        result.first.return_value = row
        return result

    db.execute = AsyncMock(side_effect=execute_side)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
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
    async def test_reader_sees_experiment_datasets(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_permission(TEAM_ALPHA_ID)
        mlflow = _mock_mlflow_for_list()
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(alice_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.get(
                    f"/experiments/{EXPERIMENT_ID}/datasets", headers=AUTH_HEADERS
                )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "rag-eval"
        assert data[0]["id"] == DATASET_ID
        assert data[0]["experiment_id"] == EXPERIMENT_ID

    async def test_cross_team_user_gets_403(
        self,
        dave_claims: TokenClaims,
        dave_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_permission(TEAM_ALPHA_ID)
        mlflow = _mock_mlflow_for_list()
        app.dependency_overrides[get_team_roles] = lambda: dave_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(dave_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.get(
                    f"/experiments/{EXPERIMENT_ID}/datasets", headers=AUTH_HEADERS
                )

        assert resp.status_code == 403


class TestGetDataset:
    async def test_reader_can_view_detail(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_permission(TEAM_ALPHA_ID)
        mlflow = _mock_mlflow_for_detail(found=True)
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(alice_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.get(
                    f"/experiments/{EXPERIMENT_ID}/datasets/{DATASET_ID}",
                    headers=AUTH_HEADERS,
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "rag-eval"
        assert data["id"] == DATASET_ID
        assert data["experiment_id"] == EXPERIMENT_ID
        assert len(data["rows"]) == 1

    async def test_dataset_from_other_experiment_returns_403(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_permission(TEAM_ALPHA_ID)
        mlflow = _mock_mlflow_for_detail(found=False)
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(alice_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.get(
                    f"/experiments/{EXPERIMENT_ID}/datasets/{DATASET_ID}",
                    headers=AUTH_HEADERS,
                )

        assert resp.status_code == 403


class TestCreateDataset:
    async def test_reader_cannot_create_dataset(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_permission(TEAM_ALPHA_ID)
        mlflow = _mock_mlflow_for_write()
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(alice_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.post(
                    f"/experiments/{EXPERIMENT_ID}/datasets",
                    json={"name": "new-ds", "rows": SAMPLE_ROWS},
                    headers=AUTH_HEADERS,
                )

        assert resp.status_code == 403

    async def test_engineer_can_create_dataset(
        self,
        bob_claims: TokenClaims,
        bob_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_permission(TEAM_ALPHA_ID)
        mlflow = _mock_mlflow_for_write()
        app.dependency_overrides[get_team_roles] = lambda: bob_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(bob_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.post(
                    f"/experiments/{EXPERIMENT_ID}/datasets",
                    json={"name": "new-ds", "rows": SAMPLE_ROWS},
                    headers=AUTH_HEADERS,
                )

        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == DATASET_ID
        assert data["name"] == "new-ds"


class TestUpdateDataset:
    async def test_reader_cannot_update_dataset(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_permission(TEAM_ALPHA_ID)
        mlflow = _mock_mlflow_for_write()
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(alice_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.put(
                    f"/experiments/{EXPERIMENT_ID}/datasets/{DATASET_ID}",
                    json={"rows": SAMPLE_ROWS},
                    headers=AUTH_HEADERS,
                )

        assert resp.status_code == 403

    async def test_engineer_can_update_dataset(
        self,
        bob_claims: TokenClaims,
        bob_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_permission(TEAM_ALPHA_ID)
        mlflow = _mock_mlflow_for_write()
        app.dependency_overrides[get_team_roles] = lambda: bob_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(bob_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.put(
                    f"/experiments/{EXPERIMENT_ID}/datasets/{DATASET_ID}",
                    json={"rows": SAMPLE_ROWS},
                    headers=AUTH_HEADERS,
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == DATASET_ID
        assert data["row_count"] == len(SAMPLE_ROWS)


class TestDeleteDataset:
    async def test_reader_cannot_delete_dataset(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_permission(TEAM_ALPHA_ID)
        mlflow = _mock_mlflow_for_write()
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(alice_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.delete(
                    f"/experiments/{EXPERIMENT_ID}/datasets/{DATASET_ID}",
                    headers=AUTH_HEADERS,
                )

        assert resp.status_code == 403

    async def test_engineer_can_delete_dataset(
        self,
        bob_claims: TokenClaims,
        bob_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_permission(TEAM_ALPHA_ID)
        mlflow = _mock_mlflow_for_write()
        app.dependency_overrides[get_team_roles] = lambda: bob_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(bob_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.delete(
                    f"/experiments/{EXPERIMENT_ID}/datasets/{DATASET_ID}",
                    headers=AUTH_HEADERS,
                )

        assert resp.status_code == 204
