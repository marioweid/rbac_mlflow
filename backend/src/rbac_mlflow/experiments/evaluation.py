"""Evaluation orchestration for POST /experiments/{id}/runs.

The "model under test" is an identity function that returns the expected answer,
making exact_match/mean = 1.0 by design. This validates the full pipeline without
requiring external API keys. A future phase can plug in a real model endpoint.
"""

import logging
import time
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rbac_mlflow.experiments.schemas import StartRunResponse
from rbac_mlflow.mlflow_client import create_run, log_batch, update_run
from rbac_mlflow.models import Dataset, DatasetVersion
from rbac_mlflow.s3_client import S3Client

log = logging.getLogger(__name__)


async def run_evaluation(
    mlflow: httpx.AsyncClient,
    s3: S3Client,
    db: AsyncSession,
    experiment_id: str,
    dataset_id: uuid.UUID,
    dataset_version: int | None,
    run_name: str | None,
    user_sub: str,
    experiment_team_id: uuid.UUID,
) -> StartRunResponse:
    """Create an MLflow run and execute deterministic evaluation against a dataset.

    Args:
        mlflow: Shared MLflow httpx client.
        s3: S3 client for downloading dataset files.
        db: Async DB session.
        experiment_id: MLflow experiment ID to run against.
        dataset_id: RBAC dataset UUID.
        dataset_version: Specific version to evaluate, or None for latest.
        run_name: Human-readable name for the run, or None to auto-generate.
        user_sub: JWT sub of the user triggering the run (for audit tags).
        experiment_team_id: Team that owns the experiment (for cross-team validation).

    Returns:
        StartRunResponse with the created run's ID, name, and final status.
    """
    dataset, version_row = await _load_dataset_and_version(
        db, dataset_id, dataset_version, experiment_team_id
    )
    rows = await s3.download_jsonl(version_row.s3_key)

    effective_run_name = run_name or _auto_run_name(dataset.name, version_row.version)

    tags = {
        "mlflow.runName": effective_run_name,
        "dataset_id": str(dataset_id),
        "dataset_version": str(version_row.version),
        "dataset_name": dataset.name,
        "started_by": user_sub,
    }
    mlflow_run = await create_run(mlflow, experiment_id, effective_run_name, tags)
    run_id: str = mlflow_run["info"]["run_id"]

    try:
        status = await _score_and_log(mlflow, run_id, rows, dataset.name, version_row.version)
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


async def _load_dataset_and_version(
    db: AsyncSession,
    dataset_id: uuid.UUID,
    dataset_version: int | None,
    experiment_team_id: uuid.UUID,
) -> tuple[Dataset, DatasetVersion]:
    """Load and validate dataset + version from the database."""
    ds_result = await db.execute(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.is_active.is_(True))
    )
    dataset = ds_result.scalar_one_or_none()
    if dataset is None:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")

    if dataset.team_id != experiment_team_id:
        raise HTTPException(
            status_code=403,
            detail="Dataset does not belong to the same team as the experiment",
        )

    if dataset_version is not None:
        v_stmt = select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset_id,
            DatasetVersion.version == dataset_version,
        )
    else:
        v_stmt = (
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version.desc())
            .limit(1)
        )

    v_result = await db.execute(v_stmt)
    version_row = v_result.scalar_one_or_none()
    if version_row is None:
        detail = (
            f"Dataset version {dataset_version} not found"
            if dataset_version is not None
            else "Dataset has no versions"
        )
        raise HTTPException(status_code=404, detail=detail)

    return dataset, version_row


async def _score_and_log(
    mlflow: httpx.AsyncClient,
    run_id: str,
    rows: list[dict],
    dataset_name: str,
    version: int,
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
        {"key": "dataset_version", "value": str(version)},
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


def _auto_run_name(dataset_name: str, version: int) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"eval-{dataset_name}-v{version}-{timestamp}"
