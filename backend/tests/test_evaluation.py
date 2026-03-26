"""Unit tests for the evaluation service (experiments/evaluation.py)."""

from unittest.mock import MagicMock, patch

from rbac_mlflow.experiments.evaluation import (
    _identity_predict,
    _prepare_eval_data,
    run_evaluation,
)

EXPERIMENT_ID = "1"
TRACKING_URI = "http://mlflow:5000"

SAMPLE_ROWS = [
    {
        "dataset_record_id": "dr-1",
        "dataset_id": "d-abc",
        "inputs": {"question": "Q1"},
        "expectations": {"expected_response": "A1"},
        "outputs": {},
        "tags": {},
        "created_time": 1000,
        "last_update_time": 1000,
    },
    {
        "dataset_record_id": "dr-2",
        "dataset_id": "d-abc",
        "inputs": {"question": "Q2"},
        "expectations": {"expected_response": "A2"},
        "outputs": {},
        "tags": {},
        "created_time": 1000,
        "last_update_time": 1000,
    },
]


class TestPrepareEvalData:
    def test_strips_internal_fields(self) -> None:
        cleaned = _prepare_eval_data(SAMPLE_ROWS)
        for record in cleaned:
            assert "dataset_record_id" not in record
            assert "dataset_id" not in record
            assert "created_time" not in record
            assert "last_update_time" not in record
            assert "outputs" not in record
            assert "tags" not in record

    def test_preserves_inputs_and_expectations(self) -> None:
        cleaned = _prepare_eval_data(SAMPLE_ROWS)
        assert cleaned[0]["inputs"] == {"question": "Q1"}
        assert cleaned[0]["expectations"] == {"expected_response": "A1"}

    def test_adds_empty_inputs_if_missing(self) -> None:
        rows = [{"expectations": {"expected_response": "A1"}}]
        cleaned = _prepare_eval_data(rows)
        assert cleaned[0]["inputs"] == {}

    def test_empty_rows(self) -> None:
        assert _prepare_eval_data([]) == []


class TestIdentityPredict:
    def test_returns_question(self) -> None:
        assert _identity_predict(question="hello") == "hello"

    def test_returns_empty_for_missing_question(self) -> None:
        assert _identity_predict(other="value") == ""


class TestRunEvaluation:
    async def test_calls_evaluate_and_returns_response(self) -> None:
        mock_run = MagicMock()
        mock_run.info.run_id = "run-123"

        with (
            patch("rbac_mlflow.experiments.evaluation.mlflow") as mock_mlflow,
        ):
            mock_mlflow.start_run.return_value.__enter__ = MagicMock(
                return_value=mock_run
            )
            mock_mlflow.start_run.return_value.__exit__ = MagicMock(
                return_value=False
            )

            result = await run_evaluation(
                tracking_uri=TRACKING_URI,
                experiment_id=EXPERIMENT_ID,
                dataset_name="test-dataset",
                rows=SAMPLE_ROWS,
                run_name="my-run",
                user_sub="bob-id",
            )

        assert result.run_id == "run-123"
        assert result.experiment_id == EXPERIMENT_ID
        assert result.run_name == "my-run"
        assert result.status == "FINISHED"

    async def test_auto_generates_run_name_when_none(self) -> None:
        mock_run = MagicMock()
        mock_run.info.run_id = "run-456"

        with (
            patch("rbac_mlflow.experiments.evaluation.mlflow") as mock_mlflow,
        ):
            mock_mlflow.start_run.return_value.__enter__ = MagicMock(
                return_value=mock_run
            )
            mock_mlflow.start_run.return_value.__exit__ = MagicMock(
                return_value=False
            )

            result = await run_evaluation(
                tracking_uri=TRACKING_URI,
                experiment_id=EXPERIMENT_ID,
                dataset_name="my-ds",
                rows=SAMPLE_ROWS,
                run_name=None,
                user_sub="bob-id",
            )

        assert result.run_name.startswith("eval-my-ds-")

    async def test_returns_failed_on_evaluate_error(self) -> None:
        mock_run = MagicMock()
        mock_run.info.run_id = "run-fail"

        with (
            patch("rbac_mlflow.experiments.evaluation.mlflow") as mock_mlflow,
        ):
            mock_mlflow.start_run.return_value.__enter__ = MagicMock(
                return_value=mock_run
            )
            mock_mlflow.start_run.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_mlflow.genai.evaluate.side_effect = RuntimeError("boom")

            result = await run_evaluation(
                tracking_uri=TRACKING_URI,
                experiment_id=EXPERIMENT_ID,
                dataset_name="test-ds",
                rows=SAMPLE_ROWS,
                run_name="fail-run",
                user_sub="bob-id",
            )

        assert result.status == "FAILED"
        assert result.run_id == "run-fail"
