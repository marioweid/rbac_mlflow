"""Regression tests for the GoldenSample experiment.

Unit tests (always run via pytest -q):
  - Fixture parsing and field validation
  - API RBAC isolation: team-alpha sees GoldenSample, team-beta sees nothing

Integration tests (require live services, run via make golden-test):
  - Baseline run exists in MLflow with FINISHED status
  - Expected metrics are present and within acceptable thresholds

Mark: integration tests use @pytest.mark.integration and are skipped by
default. Run `pytest -m integration` after seeding to execute them.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
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

FIXTURE_PATH = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "golden_sample.jsonl"

TEAM_ALPHA_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEAM_BETA_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
AUTH_HEADERS = {"Authorization": "Bearer fake-token"}

GOLDEN_EXPERIMENT_ID = "42"
GOLDEN_EXPERIMENT = {
    "experiment_id": GOLDEN_EXPERIMENT_ID,
    "name": "GoldenSample",
    "artifact_location": "s3://mlflow-artifacts/42",
    "lifecycle_stage": "active",
    "creation_time": 1700000000000,
    "last_update_time": 1700000001000,
}
BASELINE_RUN = {
    "info": {
        "run_id": "baseline-run-id",
        "run_name": "baseline",
        "experiment_id": GOLDEN_EXPERIMENT_ID,
        "status": "FINISHED",
        "start_time": 1700000000000,
        "end_time": 1700000060000,
        "artifact_uri": f"s3://mlflow-artifacts/{GOLDEN_EXPERIMENT_ID}/baseline-run-id/artifacts",
        "lifecycle_stage": "active",
    },
    "data": {
        "metrics": [
            {"key": "exact_match/mean", "value": 1.0, "timestamp": 1700000060000, "step": 0},
            {"key": "is_non_empty/mean", "value": 1.0, "timestamp": 1700000060000, "step": 0},
            {"key": "row_count", "value": 8.0, "timestamp": 1700000060000, "step": 0},
        ],
        "params": [
            {"key": "dataset_path", "value": "s3://mlflow-artifacts/datasets/golden_sample/v1/data.jsonl"},
            {"key": "scorer", "value": "deterministic"},
        ],
        "tags": [{"key": "mlflow.runName", "value": "baseline"}],
    },
}


# ── Fixture: helpers ──────────────────────────────────────────────────────────


def _mock_mlflow_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.json.return_value = json_data or {}
    resp.text = ""
    return resp


def _mock_mlflow_client_golden() -> AsyncMock:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.return_value = _mock_mlflow_response(
        json_data={"experiment": GOLDEN_EXPERIMENT}
    )
    client.post.return_value = _mock_mlflow_response(
        json_data={"runs": [BASELINE_RUN], "next_page_token": None}
    )
    return client


def _mock_db_with_golden(team_id: uuid.UUID) -> AsyncMock:
    db = AsyncMock()

    def _execute_side_effect(stmt):
        result = MagicMock()
        row = MagicMock()
        row.mlflow_experiment_id = GOLDEN_EXPERIMENT_ID
        row.team_id = team_id
        result.all.return_value = [row]
        result.first.return_value = row
        return result

    db.execute = AsyncMock(side_effect=_execute_side_effect)
    return db


def _mock_db_empty() -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    result.first.return_value = None
    db.execute = AsyncMock(return_value=result)
    return db


def _patch_auth(claims: TokenClaims):
    mock_provider = AsyncMock()
    mock_provider.validate_token.return_value = claims
    return patch("rbac_mlflow.auth.middleware.get_auth_provider", return_value=mock_provider)


# ── Unit tests: fixture validation ────────────────────────────────────────────


class TestGoldenFixture:
    def test_fixture_file_exists(self) -> None:
        assert FIXTURE_PATH.exists(), f"Fixture not found at {FIXTURE_PATH}"

    def test_fixture_parses_to_at_least_eight_rows(self) -> None:
        rows = [json.loads(line) for line in FIXTURE_PATH.read_text().splitlines() if line.strip()]
        assert len(rows) >= 8, f"Expected >= 8 rows, got {len(rows)}"

    def test_fixture_rows_have_required_fields(self) -> None:
        rows = [json.loads(line) for line in FIXTURE_PATH.read_text().splitlines() if line.strip()]
        for i, row in enumerate(rows):
            assert "inputs" in row, f"Row {i} missing 'inputs'"
            assert "question" in row["inputs"], f"Row {i} missing 'inputs.question'"
            assert "expectations" in row, f"Row {i} missing 'expectations'"
            assert "expected_response" in row["expectations"], (
                f"Row {i} missing 'expectations.expected_response'"
            )

    def test_fixture_field_types_are_non_empty_strings(self) -> None:
        rows = [json.loads(line) for line in FIXTURE_PATH.read_text().splitlines() if line.strip()]
        non_empty_rows = [r for r in rows if r["inputs"]["question"]]
        # At least 7 of 8 rows should have non-empty questions (one is the empty-input edge case)
        assert len(non_empty_rows) >= 7
        for row in rows:
            assert isinstance(row["inputs"]["question"], str)
            assert isinstance(row["expectations"]["expected_response"], str)
            assert len(row["expectations"]["expected_response"]) > 0


# ── Unit tests: RBAC isolation via API ───────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


class TestGoldenSampleRbacIsolation:
    @pytest.mark.asyncio
    async def test_team_alpha_reader_sees_golden_experiment(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
    ) -> None:
        mlflow = _mock_mlflow_client_golden()
        db = _mock_db_with_golden(TEAM_ALPHA_ID)
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
        assert data[0]["name"] == "GoldenSample"
        assert data[0]["team_name"] == "team-alpha"

    @pytest.mark.asyncio
    async def test_team_beta_reader_sees_empty_dashboard(
        self,
        dave_claims: TokenClaims,
        dave_team_roles: list[TeamRole],
    ) -> None:
        """Dave (team-beta) must get an empty list — no access to GoldenSample."""
        mlflow = _mock_mlflow_client_golden()
        # DB returns no links for team-beta
        db = _mock_db_empty()
        app.dependency_overrides[get_team_roles] = lambda: dave_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(dave_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/experiments", headers=AUTH_HEADERS)

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_team_beta_cannot_access_golden_experiment_directly(
        self,
        dave_claims: TokenClaims,
        dave_team_roles: list[TeamRole],
    ) -> None:
        """Dave gets 404 when accessing GoldenSample experiment by ID."""
        mlflow = _mock_mlflow_client_golden()
        db = _mock_db_empty()
        app.dependency_overrides[get_team_roles] = lambda: dave_team_roles
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(dave_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get(f"/experiments/{GOLDEN_EXPERIMENT_ID}", headers=AUTH_HEADERS)

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_golden_experiment_linked_to_alpha_not_beta(
        self,
        alice_claims: TokenClaims,
        alice_team_roles: list[TeamRole],
        dave_claims: TokenClaims,
        dave_team_roles: list[TeamRole],
    ) -> None:
        """GoldenSample is linked to team-alpha: alice sees it, dave does not."""
        mlflow = _mock_mlflow_client_golden()
        alpha_db = _mock_db_with_golden(TEAM_ALPHA_ID)
        beta_db = _mock_db_empty()

        # Alice (team-alpha) sees it
        app.dependency_overrides[get_team_roles] = lambda: alice_team_roles
        app.dependency_overrides[get_db] = lambda: alpha_db
        app.dependency_overrides[get_mlflow_client] = lambda: mlflow

        with _patch_auth(alice_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                alpha_resp = await c.get("/experiments", headers=AUTH_HEADERS)

        app.dependency_overrides[get_team_roles] = lambda: dave_team_roles
        app.dependency_overrides[get_db] = lambda: beta_db

        with _patch_auth(dave_claims):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                beta_resp = await c.get("/experiments", headers=AUTH_HEADERS)

        assert len(alpha_resp.json()) == 1
        assert alpha_resp.json()[0]["name"] == "GoldenSample"
        assert beta_resp.json() == []


# ── Integration tests (require live services) ─────────────────────────────────


@pytest.mark.integration
class TestGoldenSampleIntegration:
    """Tests that require a live MLflow instance seeded with golden data.

    Run: pytest -m integration --mlflow-uri http://localhost:5000
    Or:  make golden-test
    """

    @pytest.fixture(autouse=True)
    def _mlflow_uri(self, request) -> str:
        uri = request.config.getoption("--mlflow-uri", default=None) or os.environ.get(
            "MLFLOW_TRACKING_URI", "http://localhost:5000"
        )
        self._uri = uri
        return uri

    def _get_experiment(self) -> dict:
        import urllib.request
        import urllib.error

        url = f"{self._uri}/api/2.0/mlflow/experiments/get-by-name?experiment_name=GoldenSample"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                return json.loads(resp.read())["experiment"]
        except urllib.error.HTTPError as exc:
            pytest.fail(f"Could not fetch GoldenSample experiment: {exc}")

    def _search_baseline_run(self, experiment_id: str) -> dict | None:
        import urllib.request
        import json as _json

        url = f"{self._uri}/api/2.0/mlflow/runs/search"
        body = _json.dumps({
            "experiment_ids": [experiment_id],
            "filter": "tags.mlflow.runName = 'baseline' AND attributes.status = 'FINISHED'",
            "max_results": 1,
        }).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            runs = _json.loads(resp.read()).get("runs", [])
        return runs[0] if runs else None

    def test_golden_experiment_exists(self) -> None:
        exp = self._get_experiment()
        assert exp["name"] == "GoldenSample"
        assert exp["lifecycle_stage"] == "active"

    def test_baseline_run_exists_and_finished(self) -> None:
        exp = self._get_experiment()
        run = self._search_baseline_run(exp["experiment_id"])
        assert run is not None, "No FINISHED baseline run found in GoldenSample"
        assert run["info"]["status"] == "FINISHED"
        assert run["info"]["run_name"] == "baseline"

    def test_baseline_metrics_present(self) -> None:
        exp = self._get_experiment()
        run = self._search_baseline_run(exp["experiment_id"])
        assert run is not None
        metric_keys = {m["key"] for m in run["data"].get("metrics", [])}
        assert "exact_match/mean" in metric_keys
        assert "is_non_empty/mean" in metric_keys

    def test_baseline_metrics_within_threshold(self) -> None:
        exp = self._get_experiment()
        run = self._search_baseline_run(exp["experiment_id"])
        assert run is not None
        metrics = {m["key"]: m["value"] for m in run["data"].get("metrics", [])}
        assert metrics.get("exact_match/mean", 0.0) >= 0.9, (
            f"exact_match/mean {metrics.get('exact_match/mean')} below threshold 0.9"
        )
        assert metrics.get("is_non_empty/mean", 0.0) >= 0.95, (
            f"is_non_empty/mean {metrics.get('is_non_empty/mean')} below threshold 0.95"
        )


