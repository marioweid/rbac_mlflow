"""Evaluation orchestration for POST /experiments/{id}/runs.

Uses mlflow.genai.evaluate() to run evaluation against a dataset, creating
proper MLflow traces and metrics. The predict function is an identity
function (returns expected_response) until a real model endpoint is configured.
"""

import asyncio
import logging
from datetime import UTC, datetime

import mlflow
from mlflow.genai.scorers import Correctness

from rbac_mlflow.experiments.schemas import StartRunResponse

log = logging.getLogger(__name__)


async def run_evaluation(
    tracking_uri: str,
    experiment_id: str,
    dataset_name: str,
    rows: list[dict],
    run_name: str | None,
    user_sub: str,
) -> StartRunResponse:
    """Run mlflow.genai.evaluate() in a thread and return the result.

    Args:
        tracking_uri: MLflow tracking server URL.
        experiment_id: MLflow experiment ID.
        dataset_name: Name of the dataset being evaluated.
        rows: Dataset records (each with 'inputs' and 'expectations').
        run_name: Human-readable name, or None to auto-generate.
        user_sub: JWT sub of the triggering user (for tags).

    Returns:
        StartRunResponse with the created run's ID, name, and status.
    """
    effective_run_name = run_name or _auto_run_name(dataset_name)
    return await asyncio.to_thread(
        _run_evaluate_sync,
        tracking_uri=tracking_uri,
        experiment_id=experiment_id,
        dataset_name=dataset_name,
        rows=rows,
        run_name=effective_run_name,
        user_sub=user_sub,
    )


def _run_evaluate_sync(
    tracking_uri: str,
    experiment_id: str,
    dataset_name: str,
    rows: list[dict],
    run_name: str,
    user_sub: str,
) -> StartRunResponse:
    """Synchronous evaluation using mlflow.genai.evaluate().

    Runs in a thread pool to avoid blocking the async event loop.
    """
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_id=experiment_id)

    eval_data = _prepare_eval_data(rows)

    with mlflow.start_run(run_name=run_name) as run:
        mlflow.set_tags(
            {
                "dataset_name": dataset_name,
                "started_by": user_sub,
            }
        )
        mlflow.log_param("dataset_name", dataset_name)
        mlflow.log_param("scorer", "Correctness")
        mlflow.log_param("row_count", len(eval_data))

        try:
            mlflow.genai.evaluate(
                data=eval_data,
                predict_fn=_identity_predict,
                scorers=[Correctness()],
            )
            status = "FINISHED"
        except Exception:
            log.exception("Evaluation failed for run %s", run.info.run_id)
            status = "FAILED"

    return StartRunResponse(
        run_id=run.info.run_id,
        experiment_id=experiment_id,
        run_name=run_name,
        status=status,
    )


def _prepare_eval_data(rows: list[dict]) -> list[dict]:
    """Normalize dataset records into the format expected by mlflow.genai.evaluate().

    Each record needs 'inputs' (dict) and optionally 'expectations' (dict).
    Strips internal MLflow fields that aren't part of the evaluation schema.
    """
    internal_fields = {
        "dataset_record_id",
        "dataset_id",
        "created_time",
        "last_update_time",
        "outputs",
        "tags",
    }
    cleaned = []
    for row in rows:
        record = {k: v for k, v in row.items() if k not in internal_fields}
        if "inputs" not in record:
            record["inputs"] = {}
        cleaned.append(record)
    return cleaned


def _identity_predict(**kwargs: str) -> str:
    """Identity predict function: returns the expected response.

    This is a placeholder until a real model endpoint is configured.
    The function signature accepts keyword arguments matching the keys
    in each record's 'inputs' dict.
    """
    return kwargs.get("question", "")


def _auto_run_name(dataset_name: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"eval-{dataset_name}-{timestamp}"
