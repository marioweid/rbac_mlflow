import uuid
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
AUTH_HEADERS = {"Authorization": "Bearer fake-token"}

SAMPLE_EXPERIMENT = {
    "experiment_id": "1",
    "name": "rag-eval",
    "artifact_location": "s3://mlflow/1",
    "lifecycle_stage": "active",
    "creation_time": 1678886400000,
    "last_update_time": 1678886500000,
}

SAMPLE_RUN = {
    "info": {
        "run_id": "run-abc",
        "run_name": "eval-1",
        "experiment_id": "1",
        "status": "FINISHED",
        "start_time": 1678886400000,
        "end_time": 1678886500000,
        "artifact_uri": "s3://mlflow/1/run-abc/artifacts",
        "lifecycle_stage": "active",
    },
    "data": {
        "metrics": [{"key": "accuracy", "value": 0.95, "timestamp": 1678886450000, "step": 0}],
        "params": [{"key": "model", "value": "gpt-4"}],
        "tags": [{"key": "mlflow.runName", "value": "eval-1"}],
    },
}


def _mock_mlflow_response(status_code=200, json_data=None, text=""):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


def _mock_mlflow_client():
    """Create a mock httpx.AsyncClient with default responses."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.return_value = _mock_mlflow_response(json_data={"experiment": SAMPLE_EXPERIMENT})
    client.post.return_value = _mock_mlflow_response(
        json_data={"runs": [SAMPLE_RUN], "next_page_token": None}
    )
    return client


def _mock_db_with_experiments(links: dict[str, uuid.UUID]):
    """Create a mock DB session that returns experiment links.

    Args:
        links: mapping of mlflow_experiment_id -> team_id
    """
    db = AsyncMock()

    def _execute_side_effect(stmt):
        result = MagicMock()
        rows = []
        for exp_id, team_id in links.items():
            row = MagicMock()
            row.mlflow_experiment_id = exp_id
            row.team_id = team_id
            rows.append(row)
        result.all.return_value = rows
        # For the permission dependency (single row lookup)
        if rows:
            first_row = MagicMock()
            first_row.team_id = rows[0].team_id
            result.first.return_value = first_row
        else:
            result.first.return_value = None
        return result

    db.execute = AsyncMock(side_effect=_execute_side_effect)
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


class TestListExperiments:
    @pytest.mark.asyncio
    async def test_reader_sees_own_team_experiments(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        mlflow = _mock_mlflow_client()
        db = _mock_db_with_experiments({"1": TEAM_ALPHA_ID})
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(alice_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/experiments", headers=AUTH_HEADERS)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["experiment_id"] == "1"
        assert data[0]["team_name"] == "team-alpha"

    @pytest.mark.asyncio
    async def test_user_with_no_teams_sees_empty(
        self,
        alice_claims: TokenClaims,
    ) -> None:
        mlflow = _mock_mlflow_client()
        app.dependency_overrides[get_team_roles] = lambda: []
        app.dependency_overrides[get_db] = lambda: AsyncMock()
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(alice_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/experiments", headers=AUTH_HEADERS)

        assert resp.status_code == 200
        assert resp.json() == []


class TestGetExperiment:
    @pytest.mark.asyncio
    async def test_reader_can_view_detail(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        mlflow = _mock_mlflow_client()
        db = _mock_db_with_experiments({"1": TEAM_ALPHA_ID})
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(alice_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/experiments/1", headers=AUTH_HEADERS)

        assert resp.status_code == 200
        data = resp.json()
        assert data["experiment_id"] == "1"
        assert data["name"] == "rag-eval"

    @pytest.mark.asyncio
    async def test_unlinked_experiment_returns_404(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        mlflow = _mock_mlflow_client()
        db = _mock_db_with_experiments({})
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(alice_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/experiments/999", headers=AUTH_HEADERS)

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reader_cannot_access_other_team(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        mlflow = _mock_mlflow_client()
        # Experiment "2" is linked to team-beta, alice only has team-alpha
        db = AsyncMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.team_id = TEAM_BETA_ID
        mock_result.first.return_value = mock_row
        db.execute.return_value = mock_result

        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(alice_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/experiments/2", headers=AUTH_HEADERS)

        assert resp.status_code == 403


class TestListRuns:
    @pytest.mark.asyncio
    async def test_reader_can_list_runs(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        mlflow = _mock_mlflow_client()
        db = _mock_db_with_experiments({"1": TEAM_ALPHA_ID})
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(alice_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/experiments/1/runs", headers=AUTH_HEADERS)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["runs"]) == 1
        assert data["runs"][0]["run_id"] == "run-abc"


class TestGetRunDetail:
    @pytest.mark.asyncio
    async def test_reader_can_view_run(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        mlflow = AsyncMock(spec=httpx.AsyncClient)
        mlflow.get.return_value = _mock_mlflow_response(json_data={"run": SAMPLE_RUN})
        mlflow.post.return_value = _mock_mlflow_response(
            json_data={"runs": [], "next_page_token": None}
        )
        db = _mock_db_with_experiments({"1": TEAM_ALPHA_ID})
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(alice_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/experiments/1/runs/run-abc", headers=AUTH_HEADERS)

        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == "run-abc"
        assert data["experiment_id"] == "1"
        assert len(data["metrics"]) == 1
        assert data["metrics"][0]["key"] == "accuracy"

    @pytest.mark.asyncio
    async def test_run_from_wrong_experiment_returns_404(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        wrong_run = {
            "info": {
                "run_id": "run-xyz",
                "experiment_id": "2",
                "status": "FINISHED",
            },
            "data": {},
        }
        mlflow = AsyncMock(spec=httpx.AsyncClient)
        mlflow.get.return_value = _mock_mlflow_response(json_data={"run": wrong_run})
        db = _mock_db_with_experiments({"1": TEAM_ALPHA_ID})
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(alice_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/experiments/1/runs/run-xyz", headers=AUTH_HEADERS)

        assert resp.status_code == 404
