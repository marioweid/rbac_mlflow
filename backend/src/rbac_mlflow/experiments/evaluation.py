"""Evaluation orchestration for POST /experiments/{id}/runs.

The "model under test" is an identity function that returns the expected answer,
making exact_match/mean = 1.0 by design. This validates the full pipeline without
requiring external API keys. A future phase can plug in a real model endpoint.
"""

import logging
import time
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException

from rbac_mlflow.experiments.schemas import StartRunResponse
from rbac_mlflow.mlflow_client import (
    create_run,
    get_mlflow_dataset,
    get_mlflow_dataset_experiment_ids,
    get_mlflow_dataset_records,
    log_batch,
    log_dataset_inputs,
    update_run,
)

log = logging.getLogger(__name__)


async def run_evaluation(
    mlflow: httpx.AsyncClient,
    experiment_id: str,
    dataset_id: str,
    run_name: str | None,
    user_sub: str,
) -> StartRunResponse:
    """Create an MLflow run and execute deterministic evaluation against a dataset.

    Args:
        mlflow: Shared MLflow httpx client.
        experiment_id: MLflow experiment ID to run against.
        dataset_id: MLflow dataset ID (e.g. "d-1cafa29844fe4a24a60dc53189b6eccb").
        run_name: Human-readable name for the run, or None to auto-generate.
        user_sub: JWT sub of the user triggering the run (for audit tags).

    Returns:
        StartRunResponse with the created run's ID, name, and final status.
    """
    dataset, rows = await _load_dataset_and_records(mlflow, dataset_id, experiment_id)

    effective_run_name = run_name or _auto_run_name(dataset["name"])

    tags = {
        "mlflow.runName": effective_run_name,
        "dataset_id": dataset_id,
        "dataset_name": dataset["name"],
        "started_by": user_sub,
    }
    mlflow_run = await create_run(mlflow, experiment_id, effective_run_name, tags)
    run_id: str = mlflow_run["info"]["run_id"]

    # Log dataset lineage so it appears as a run input in the MLflow UI
    await log_dataset_inputs(
        mlflow,
        run_id,
        dataset["name"],
        dataset.get("digest", ""),
        source=f"mlflow://datasets/{dataset_id}",
        source_type="mlflow",
    )

    try:
        status = await _score_and_log(mlflow, run_id, rows, dataset["name"])
    except Exception:
        log.exception("Evaluation failed for run %s", run_id)
        await update_run(mlflow, run_id, status="FAILED")
        status = "FAILED"

    return StartRunResponse(
        run_id=run_id,
        experiment_id=experiment_id,
        run_name=effective_run_name,
        status=status,
    )


async def _load_dataset_and_records(
    mlflow: httpx.AsyncClient,
    dataset_id: str,
    experiment_id: str,
) -> tuple[dict, list[dict]]:
    """Load dataset metadata and records from MLflow, verifying experiment ownership."""
    exp_ids = await get_mlflow_dataset_experiment_ids(mlflow, dataset_id)
    if not exp_ids:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")

    if experiment_id not in exp_ids:
        raise HTTPException(
            status_code=403,
            detail="Dataset does not belong to this experiment",
        )

    dataset = await get_mlflow_dataset(mlflow, dataset_id)
    records = await get_mlflow_dataset_records(mlflow, dataset_id)
    return dataset, records


async def _score_and_log(
    mlflow: httpx.AsyncClient,
    run_id: str,
    rows: list[dict],
    dataset_name: str,
) -> str:
    """Run deterministic scorers, log results, and mark the run FINISHED."""
    exact_match_scores, is_non_empty_scores = _score_rows(rows)

    n = len(rows)
    timestamp_ms = int(time.time() * 1000)
    metrics = [
        {
            "key": "exact_match/mean",
            "value": sum(exact_match_scores) / n if n else 0.0,
            "timestamp": timestamp_ms,
            "step": 0,
        },
        {
            "key": "is_non_empty/mean",
            "value": sum(is_non_empty_scores) / n if n else 0.0,
            "timestamp": timestamp_ms,
            "step": 0,
        },
        {
            "key": "row_count",
            "value": float(n),
            "timestamp": timestamp_ms,
            "step": 0,
        },
    ]
    params = [
        {"key": "dataset_name", "value": dataset_name},
        {"key": "scorer", "value": "deterministic_identity"},
    ]
    await log_batch(mlflow, run_id, metrics=metrics, params=params)
    await update_run(mlflow, run_id, status="FINISHED")
    return "FINISHED"


def _score_rows(rows: list[dict]) -> tuple[list[float], list[float]]:
    """Return (exact_match_scores, is_non_empty_scores) for each row.

    The identity model returns `expected_response` as its output, so
    `exact_match` is 1.0 for every row that has a non-empty expected answer.
    """
    exact_match: list[float] = []
    is_non_empty: list[float] = []

    for row in rows:
        expectations = row.get("expectations")
        expected = (
            expectations.get("expected_response", "")
            if isinstance(expectations, dict)
            else ""
        )
        output = expected  # identity model
        exact_match.append(1.0 if expected and output == expected else 0.0)
        is_non_empty.append(1.0 if output else 0.0)

    return exact_match, is_non_empty


def _auto_run_name(dataset_name: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"eval-{dataset_name}-{timestamp}"
