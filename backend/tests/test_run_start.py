"""RBAC and router tests for POST /experiments/{id}/runs."""

import uuid
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from rbac_mlflow.auth.providers.base import TokenClaims
from rbac_mlflow.db import get_db
from rbac_mlflow.experiments.schemas import StartRunResponse
from rbac_mlflow.main import app
from rbac_mlflow.mlflow_client import get_mlflow_client
from rbac_mlflow.rbac.dependencies import get_team_roles
from rbac_mlflow.rbac.schemas import TeamRole
from rbac_mlflow.s3_client import get_s3_client

TEAM_ALPHA_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEAM_BETA_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
DATASET_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
EXPERIMENT_ID = "42"
AUTH_HEADERS = {"Authorization": "Bearer fake-token"}

START_BODY = {
    "dataset_id": str(DATASET_ID),
    "dataset_version": 1,
    "run_name": "test-run",
}

GOOD_RESPONSE = StartRunResponse(
    run_id="run-xyz",
    experiment_id=EXPERIMENT_ID,
    run_name="test-run",
    status="FINISHED",
)


def _patch_auth(claims: TokenClaims):
    mock_provider = AsyncMock()
    mock_provider.validate_token.return_value = claims
    return patch(
        "rbac_mlflow.auth.middleware.get_auth_provider",
        return_value=mock_provider,
    )


def _mock_db_for_experiment(team_id: uuid.UUID) -> AsyncMock:
    """Mock DB that returns a team_id for the experiment permission check and
    absorbs the audit log commit."""
    db = AsyncMock()
    call_count = 0

    async def execute_side(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        row = MagicMock()
        row.team_id = team_id
        result.first.return_value = row
        return result

    db.execute = AsyncMock(side_effect=execute_side)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


def _mock_mlflow() -> AsyncMock:
    return AsyncMock(spec=httpx.AsyncClient)


def _mock_s3() -> AsyncMock:
    s3 = AsyncMock()
    s3.download_jsonl = AsyncMock(return_value=[])
    return s3


@pytest.fixture(autouse=True)
def _clear_overrides() -> Generator[None]:
    yield
    app.dependency_overrides.clear()


class TestStartRunRBAC:
    async def test_reader_cannot_start_run(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_experiment(TEAM_ALPHA_ID)
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: _mock_mlflow()

        with _patch_auth(alice_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.post(
                    f"/experiments/{EXPERIMENT_ID}/runs",
                    json=START_BODY,
                    headers=AUTH_HEADERS,
                )

        assert resp.status_code == 403

    async def test_engineer_can_start_run(
        self,
        bob_claims: TokenClaims,
        bob_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_experiment(TEAM_ALPHA_ID)
        s3 = _mock_s3()
        app.dependency_overrides[get_team_roles] = lambda: bob_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_s3_client] = lambda: s3
        app.dependency_overrides[get_mlflow_client] = lambda: _mock_mlflow()

        with (
            _patch_auth(bob_claims),
            patch(
                "rbac_mlflow.experiments.router.run_evaluation",
                new_callable=AsyncMock,
                return_value=GOOD_RESPONSE,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.post(
                    f"/experiments/{EXPERIMENT_ID}/runs",
                    json=START_BODY,
                    headers=AUTH_HEADERS,
                )

        assert resp.status_code == 201

    async def test_owner_can_start_run(
        self,
        carol_claims: TokenClaims,
        carol_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_experiment(TEAM_ALPHA_ID)
        s3 = _mock_s3()
        app.dependency_overrides[get_team_roles] = lambda: carol_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_s3_client] = lambda: s3
        app.dependency_overrides[get_mlflow_client] = lambda: _mock_mlflow()

        with (
            _patch_auth(carol_claims),
            patch(
                "rbac_mlflow.experiments.router.run_evaluation",
                new_callable=AsyncMock,
                return_value=GOOD_RESPONSE,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.post(
                    f"/experiments/{EXPERIMENT_ID}/runs",
                    json=START_BODY,
                    headers=AUTH_HEADERS,
                )

        assert resp.status_code == 201

    async def test_response_shape(
        self,
        bob_claims: TokenClaims,
        bob_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_experiment(TEAM_ALPHA_ID)
        s3 = _mock_s3()
        app.dependency_overrides[get_team_roles] = lambda: bob_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_s3_client] = lambda: s3
        app.dependency_overrides[get_mlflow_client] = lambda: _mock_mlflow()

        with (
            _patch_auth(bob_claims),
            patch(
                "rbac_mlflow.experiments.router.run_evaluation",
                new_callable=AsyncMock,
                return_value=GOOD_RESPONSE,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.post(
                    f"/experiments/{EXPERIMENT_ID}/runs",
                    json=START_BODY,
                    headers=AUTH_HEADERS,
                )

        data = resp.json()
        assert data["run_id"] == "run-xyz"
        assert data["experiment_id"] == EXPERIMENT_ID
        assert data["run_name"] == "test-run"
        assert data["status"] == "FINISHED"

    async def test_audit_event_logged_on_success(
        self,
        bob_claims: TokenClaims,
        bob_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_experiment(TEAM_ALPHA_ID)
        s3 = _mock_s3()
        app.dependency_overrides[get_team_roles] = lambda: bob_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_s3_client] = lambda: s3
        app.dependency_overrides[get_mlflow_client] = lambda: _mock_mlflow()

        with (
            _patch_auth(bob_claims),
            patch(
                "rbac_mlflow.experiments.router.run_evaluation",
                new_callable=AsyncMock,
                return_value=GOOD_RESPONSE,
            ),
            patch(
                "rbac_mlflow.experiments.router.log_audit_event",
                new_callable=AsyncMock,
            ) as mock_audit,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                await c.post(
                    f"/experiments/{EXPERIMENT_ID}/runs",
                    json=START_BODY,
                    headers=AUTH_HEADERS,
                )

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args
        assert call_kwargs.kwargs["action"] == "run.start"
        assert call_kwargs.kwargs["user_sub"] == "bob-id"

    async def test_cross_team_user_cannot_start_run(
        self,
        dave_claims: TokenClaims,
        dave_team_roles: list[TeamRole],
    ) -> None:
        # Experiment belongs to team-alpha; dave is in team-beta only
        db = _mock_db_for_experiment(TEAM_ALPHA_ID)
        app.dependency_overrides[get_team_roles] = lambda: dave_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: _mock_mlflow()

        with _patch_auth(dave_claims):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.post(
                    f"/experiments/{EXPERIMENT_ID}/runs",
                    json=START_BODY,
                    headers=AUTH_HEADERS,
                )

        assert resp.status_code == 403

    async def test_custom_run_name_passed_to_evaluation(
        self,
        bob_claims: TokenClaims,
        bob_team_roles: list[TeamRole],
    ) -> None:
        db = _mock_db_for_experiment(TEAM_ALPHA_ID)
        s3 = _mock_s3()
        app.dependency_overrides[get_team_roles] = lambda: bob_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_s3_client] = lambda: s3
        app.dependency_overrides[get_mlflow_client] = lambda: _mock_mlflow()

        custom_name = "my-special-run"

        with (
            _patch_auth(bob_claims),
            patch(
                "rbac_mlflow.experiments.router.run_evaluation",
                new_callable=AsyncMock,
                return_value=StartRunResponse(
                    run_id="r1",
                    experiment_id=EXPERIMENT_ID,
                    run_name=custom_name,
                    status="FINISHED",
                ),
            ) as mock_eval,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                await c.post(
                    f"/experiments/{EXPERIMENT_ID}/runs",
                    json={**START_BODY, "run_name": custom_name},
                    headers=AUTH_HEADERS,
                )

        call_kwargs = mock_eval.call_args.kwargs
        assert call_kwargs["run_name"] == custom_name
