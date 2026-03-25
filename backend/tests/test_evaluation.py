"""Unit tests for the evaluation service (experiments/evaluation.py)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from rbac_mlflow.experiments.evaluation import _score_rows, run_evaluation

DATASET_ID = "d-dddddddddddd4a24a60dc53189b6eccb"
EXPERIMENT_ID = "1"
OTHER_EXPERIMENT_ID = "999"

SAMPLE_ROWS = [
    {"inputs": {"question": "Q1"}, "expectations": {"expected_response": "A1"}},
    {"inputs": {"question": "Q2"}, "expectations": {"expected_response": "A2"}},
]

MLFLOW_DATASET = {
    "dataset_id": DATASET_ID,
    "name": "rag-eval",
    "tags": json.dumps({"description": "", "row_count": "2"}),
    "digest": "abc123",
    "created_time": 1774400000000,
    "last_update_time": 1774400000000,
}

MLFLOW_RECORDS = json.dumps([
    {
        "dataset_record_id": f"dr-{i}",
        "dataset_id": DATASET_ID,
        **row,
        "outputs": {},
        "tags": {},
    }
    for i, row in enumerate(SAMPLE_ROWS)
])


def _make_mlflow_mock(
    experiment_ids: list[str] | None = None,
    dataset: dict | None = None,
    records: str | None = None,
) -> AsyncMock:
    """Build an MLflow async client mock for evaluation tests."""
    exp_ids = experiment_ids if experiment_ids is not None else [EXPERIMENT_ID]
    ds = dataset if dataset is not None else MLFLOW_DATASET
    recs = records if records is not None else MLFLOW_RECORDS

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
            return make_resp({"experiment_ids": exp_ids})
        if "records" in url:
            return make_resp({"records": recs})
        return make_resp({"dataset": ds})

    async def post_side(url: str, **kwargs) -> MagicMock:
        if "runs/create" in url:
            return make_resp({"run": {"info": {"run_id": "run-123"}}})
        if "runs/log-inputs" in url:
            return make_resp({})
        if "runs/log-batch" in url:
            return make_resp({})
        if "runs/update" in url:
            return make_resp({})
        return make_resp({})

    client.get = AsyncMock(side_effect=get_side)
    client.post = AsyncMock(side_effect=post_side)
    return client


class TestRunEvaluation:
    async def test_creates_run_and_returns_finished(self) -> None:
        mlflow = _make_mlflow_mock()

        result = await run_evaluation(
            mlflow=mlflow,
            experiment_id=EXPERIMENT_ID,
            dataset_id=DATASET_ID,
            run_name=None,
            user_sub="bob-id",
        )

        assert result.run_id == "run-123"
        assert result.status == "FINISHED"
        assert result.experiment_id == EXPERIMENT_ID

    async def test_uses_custom_run_name_when_provided(self) -> None:
        mlflow = _make_mlflow_mock()

        with patch(
            "rbac_mlflow.experiments.evaluation.create_run",
            new_callable=AsyncMock,
            return_value={"info": {"run_id": "r1"}},
        ) as mock_create, patch(
            "rbac_mlflow.experiments.evaluation.log_dataset_inputs",
            new_callable=AsyncMock,
        ), patch(
            "rbac_mlflow.experiments.evaluation.log_batch", new_callable=AsyncMock
        ), patch(
            "rbac_mlflow.experiments.evaluation.update_run", new_callable=AsyncMock
        ):
            result = await run_evaluation(
                mlflow=mlflow,
                experiment_id=EXPERIMENT_ID,
                dataset_id=DATASET_ID,
                run_name="my-custom-run",
                user_sub="bob-id",
            )

        assert result.run_name == "my-custom-run"
        assert mock_create.call_args.args[2] == "my-custom-run"

    async def test_raises_404_if_dataset_not_found(self) -> None:
        # Empty experiment_ids list → dataset not found in any experiment
        mlflow = _make_mlflow_mock(experiment_ids=[])

        with pytest.raises(HTTPException) as exc_info:
            await run_evaluation(
                mlflow=mlflow,
                experiment_id=EXPERIMENT_ID,
                dataset_id=DATASET_ID,
                run_name=None,
                user_sub="bob-id",
            )

        assert exc_info.value.status_code == 404

    async def test_raises_403_if_experiment_mismatch(self) -> None:
        # Dataset belongs to a different experiment
        mlflow = _make_mlflow_mock(experiment_ids=[OTHER_EXPERIMENT_ID])

        with pytest.raises(HTTPException) as exc_info:
            await run_evaluation(
                mlflow=mlflow,
                experiment_id=EXPERIMENT_ID,
                dataset_id=DATASET_ID,
                run_name=None,
                user_sub="bob-id",
            )

        assert exc_info.value.status_code == 403

    async def test_marks_run_failed_on_scorer_error(self) -> None:
        mlflow = _make_mlflow_mock()

        with patch(
            "rbac_mlflow.experiments.evaluation.create_run",
            new_callable=AsyncMock,
            return_value={"info": {"run_id": "run-fail"}},
        ), patch(
            "rbac_mlflow.experiments.evaluation.log_dataset_inputs",
            new_callable=AsyncMock,
        ), patch(
            "rbac_mlflow.experiments.evaluation.log_batch",
            new_callable=AsyncMock,
            side_effect=RuntimeError("log failed"),
        ), patch(
            "rbac_mlflow.experiments.evaluation.update_run",
            new_callable=AsyncMock,
        ) as mock_update:
            result = await run_evaluation(
                mlflow=mlflow,
                experiment_id=EXPERIMENT_ID,
                dataset_id=DATASET_ID,
                run_name=None,
                user_sub="bob-id",
            )

        assert result.status == "FAILED"
        mock_update.assert_called_once_with(mlflow, "run-fail", status="FAILED")

    async def test_logs_started_by_tag(self) -> None:
        mlflow = _make_mlflow_mock()

        with patch(
            "rbac_mlflow.experiments.evaluation.create_run",
            new_callable=AsyncMock,
            return_value={"info": {"run_id": "r1"}},
        ) as mock_create, patch(
            "rbac_mlflow.experiments.evaluation.log_dataset_inputs",
            new_callable=AsyncMock,
        ), patch(
            "rbac_mlflow.experiments.evaluation.log_batch", new_callable=AsyncMock
        ), patch(
            "rbac_mlflow.experiments.evaluation.update_run", new_callable=AsyncMock
        ):
            await run_evaluation(
                mlflow=mlflow,
                experiment_id=EXPERIMENT_ID,
                dataset_id=DATASET_ID,
                run_name=None,
                user_sub="carol-id",
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
