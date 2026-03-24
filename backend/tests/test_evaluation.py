"""Unit tests for the evaluation service (experiments/evaluation.py)."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from rbac_mlflow.experiments.evaluation import _score_rows, run_evaluation

TEAM_ALPHA_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEAM_BETA_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
DATASET_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
EXPERIMENT_ID = "1"
NOW = datetime(2026, 3, 23, 12, 0, 0)

SAMPLE_ROWS = [
    {"inputs": {"question": "Q1"}, "expectations": {"expected_response": "A1"}},
    {"inputs": {"question": "Q2"}, "expectations": {"expected_response": "A2"}},
]


def _mock_mlflow_client(run_id: str = "run-abc") -> AsyncMock:
    client = AsyncMock(spec=httpx.AsyncClient)
    return client


def _mock_s3(rows: list[dict] | None = None) -> AsyncMock:
    s3 = AsyncMock()
    s3.download_jsonl = AsyncMock(return_value=rows or SAMPLE_ROWS)
    return s3


def _make_dataset(team_id: uuid.UUID = TEAM_ALPHA_ID, name: str = "rag-eval") -> MagicMock:
    ds = MagicMock()
    ds.id = DATASET_ID
    ds.name = name
    ds.team_id = team_id
    ds.is_active = True
    ds.created_at = NOW
    return ds


def _make_version(version: int = 1) -> MagicMock:
    v = MagicMock()
    v.id = uuid.uuid4()
    v.dataset_id = DATASET_ID
    v.version = version
    v.s3_key = f"datasets/team-alpha/rag-eval/v{version}/data.jsonl"
    v.row_count = len(SAMPLE_ROWS)
    v.created_by = "bob-id"
    v.created_at = NOW
    return v


def _mock_db(dataset: MagicMock | None, version: MagicMock | None) -> AsyncMock:
    """Mock DB that returns dataset on first query and version on second."""
    db = AsyncMock()
    call_count = 0

    async def execute_side(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar_one_or_none.return_value = dataset
        else:
            result.scalar_one_or_none.return_value = version
        return result

    db.execute = AsyncMock(side_effect=execute_side)
    return db


class TestRunEvaluation:
    async def test_creates_run_and_returns_finished(self) -> None:
        dataset = _make_dataset()
        version = _make_version()
        db = _mock_db(dataset, version)
        s3 = _mock_s3()

        with (
            patch(
                "rbac_mlflow.experiments.evaluation.create_run",
                new_callable=AsyncMock,
                return_value={"info": {"run_id": "run-123"}},
            ) as mock_create,
            patch(
                "rbac_mlflow.experiments.evaluation.log_batch",
                new_callable=AsyncMock,
            ) as mock_log,
            patch(
                "rbac_mlflow.experiments.evaluation.update_run",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            client = AsyncMock(spec=httpx.AsyncClient)
            result = await run_evaluation(
                mlflow=client,
                s3=s3,
                db=db,
                experiment_id=EXPERIMENT_ID,
                dataset_id=DATASET_ID,
                dataset_version=None,
                run_name=None,
                user_sub="bob-id",
                experiment_team_id=TEAM_ALPHA_ID,
            )

        assert result.run_id == "run-123"
        assert result.status == "FINISHED"
        assert result.experiment_id == EXPERIMENT_ID
        mock_create.assert_called_once()
        mock_log.assert_called_once()
        mock_update.assert_called_once_with(client, "run-123", status="FINISHED")

    async def test_uses_custom_run_name_when_provided(self) -> None:
        dataset = _make_dataset()
        version = _make_version()
        db = _mock_db(dataset, version)
        s3 = _mock_s3()

        with (
            patch(
                "rbac_mlflow.experiments.evaluation.create_run",
                new_callable=AsyncMock,
                return_value={"info": {"run_id": "r1"}},
            ) as mock_create,
            patch("rbac_mlflow.experiments.evaluation.log_batch", new_callable=AsyncMock),
            patch("rbac_mlflow.experiments.evaluation.update_run", new_callable=AsyncMock),
        ):
            client = AsyncMock(spec=httpx.AsyncClient)
            result = await run_evaluation(
                mlflow=client,
                s3=s3,
                db=db,
                experiment_id=EXPERIMENT_ID,
                dataset_id=DATASET_ID,
                dataset_version=1,
                run_name="my-custom-run",
                user_sub="bob-id",
                experiment_team_id=TEAM_ALPHA_ID,
            )

        assert result.run_name == "my-custom-run"
        call_kwargs = mock_create.call_args
        assert call_kwargs.args[2] == "my-custom-run"

    async def test_uses_latest_version_when_none(self) -> None:
        dataset = _make_dataset()
        version = _make_version(version=3)
        db = _mock_db(dataset, version)
        s3 = _mock_s3()

        with (
            patch(
                "rbac_mlflow.experiments.evaluation.create_run",
                new_callable=AsyncMock,
                return_value={"info": {"run_id": "r1"}},
            ),
            patch("rbac_mlflow.experiments.evaluation.log_batch", new_callable=AsyncMock),
            patch("rbac_mlflow.experiments.evaluation.update_run", new_callable=AsyncMock),
        ):
            client = AsyncMock(spec=httpx.AsyncClient)
            result = await run_evaluation(
                mlflow=client,
                s3=s3,
                db=db,
                experiment_id=EXPERIMENT_ID,
                dataset_id=DATASET_ID,
                dataset_version=None,  # should pick latest = v3
                run_name=None,
                user_sub="bob-id",
                experiment_team_id=TEAM_ALPHA_ID,
            )

        # S3 key should be for v3
        s3.download_jsonl.assert_called_once_with(version.s3_key)
        assert result.status == "FINISHED"

    async def test_raises_404_if_dataset_not_found(self) -> None:
        db = _mock_db(dataset=None, version=None)
        s3 = _mock_s3()
        client = AsyncMock(spec=httpx.AsyncClient)

        with pytest.raises(HTTPException) as exc_info:
            await run_evaluation(
                mlflow=client,
                s3=s3,
                db=db,
                experiment_id=EXPERIMENT_ID,
                dataset_id=DATASET_ID,
                dataset_version=None,
                run_name=None,
                user_sub="bob-id",
                experiment_team_id=TEAM_ALPHA_ID,
            )

        assert exc_info.value.status_code == 404

    async def test_raises_403_if_team_mismatch(self) -> None:
        # Dataset belongs to team-beta, experiment to team-alpha
        dataset = _make_dataset(team_id=TEAM_BETA_ID)
        db = _mock_db(dataset, version=None)
        s3 = _mock_s3()
        client = AsyncMock(spec=httpx.AsyncClient)

        with pytest.raises(HTTPException) as exc_info:
            await run_evaluation(
                mlflow=client,
                s3=s3,
                db=db,
                experiment_id=EXPERIMENT_ID,
                dataset_id=DATASET_ID,
                dataset_version=None,
                run_name=None,
                user_sub="bob-id",
                experiment_team_id=TEAM_ALPHA_ID,
            )

        assert exc_info.value.status_code == 403

    async def test_marks_run_failed_on_scorer_error(self) -> None:
        dataset = _make_dataset()
        version = _make_version()
        db = _mock_db(dataset, version)
        s3 = _mock_s3()

        with (
            patch(
                "rbac_mlflow.experiments.evaluation.create_run",
                new_callable=AsyncMock,
                return_value={"info": {"run_id": "run-fail"}},
            ),
            patch(
                "rbac_mlflow.experiments.evaluation.log_batch",
                new_callable=AsyncMock,
                side_effect=RuntimeError("log failed"),
            ),
            patch(
                "rbac_mlflow.experiments.evaluation.update_run",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            client = AsyncMock(spec=httpx.AsyncClient)
            result = await run_evaluation(
                mlflow=client,
                s3=s3,
                db=db,
                experiment_id=EXPERIMENT_ID,
                dataset_id=DATASET_ID,
                dataset_version=None,
                run_name=None,
                user_sub="bob-id",
                experiment_team_id=TEAM_ALPHA_ID,
            )

        assert result.status == "FAILED"
        mock_update.assert_called_once_with(client, "run-fail", status="FAILED")

    async def test_logs_started_by_tag(self) -> None:
        dataset = _make_dataset()
        version = _make_version()
        db = _mock_db(dataset, version)
        s3 = _mock_s3()

        with (
            patch(
                "rbac_mlflow.experiments.evaluation.create_run",
                new_callable=AsyncMock,
                return_value={"info": {"run_id": "r1"}},
            ) as mock_create,
            patch("rbac_mlflow.experiments.evaluation.log_batch", new_callable=AsyncMock),
            patch("rbac_mlflow.experiments.evaluation.update_run", new_callable=AsyncMock),
        ):
            client = AsyncMock(spec=httpx.AsyncClient)
            await run_evaluation(
                mlflow=client,
                s3=s3,
                db=db,
                experiment_id=EXPERIMENT_ID,
                dataset_id=DATASET_ID,
                dataset_version=None,
                run_name=None,
                user_sub="carol-id",
                experiment_team_id=TEAM_ALPHA_ID,
            )

        tags = mock_create.call_args.args[3]
        assert tags["started_by"] == "carol-id"


class TestScoreRows:
    def test_identity_model_gives_perfect_scores(self) -> None:
        rows = [
            {"inputs": {"question": "Q"}, "expectations": {"expected_response": "A"}},
        ]
        exact, non_empty = _score_rows(rows)
        assert exact == [1.0]
        assert non_empty == [1.0]

    def test_missing_expected_response_scores_zero(self) -> None:
        rows = [{"inputs": {"question": "Q"}, "expectations": {}}]
        exact, non_empty = _score_rows(rows)
        assert exact == [0.0]
        assert non_empty == [0.0]

    def test_missing_expectations_key_scores_zero(self) -> None:
        rows = [{"inputs": {"question": "Q"}}]
        exact, non_empty = _score_rows(rows)
        assert exact == [0.0]
        assert non_empty == [0.0]

    def test_empty_rows_returns_empty_lists(self) -> None:
        exact, non_empty = _score_rows([])
        assert exact == []
        assert non_empty == []

    def test_multiple_rows_scored_independently(self) -> None:
        rows = [
            {"expectations": {"expected_response": "yes"}},
            {"expectations": {"expected_response": ""}},
            {"expectations": {"expected_response": "no"}},
        ]
        exact, non_empty = _score_rows(rows)
        assert exact == [1.0, 0.0, 1.0]
        assert non_empty == [1.0, 0.0, 1.0]
