import uuid

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rbac_mlflow.auth.dependencies import get_current_user
from rbac_mlflow.auth.providers.base import TokenClaims
from rbac_mlflow.db import get_db
from rbac_mlflow.experiments.evaluation import run_evaluation
from rbac_mlflow.experiments.schemas import (
    ExperimentDetail,
    ExperimentSummary,
    RunDetail,
    RunListResponse,
    StartRunRequest,
    StartRunResponse,
)
from rbac_mlflow.experiments.service import (
    get_experiment_detail,
    get_run_detail,
    list_experiments_for_user,
    list_runs,
)
from rbac_mlflow.mlflow_client import get_mlflow_client
from rbac_mlflow.rbac.constants import Permission
from rbac_mlflow.rbac.dependencies import (
    get_team_roles,
    require_experiment_permission,
)
from rbac_mlflow.rbac.schemas import TeamRole
from rbac_mlflow.rbac.service import log_audit_event
from rbac_mlflow.s3_client import S3Client, get_s3_client

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("", response_model=list[ExperimentSummary])
async def list_experiments(
    team_roles: list[TeamRole] = Depends(get_team_roles),
    db: AsyncSession = Depends(get_db),
    mlflow: httpx.AsyncClient = Depends(get_mlflow_client),
) -> list[ExperimentSummary]:
    """List experiments linked to the current user's teams."""
    return await list_experiments_for_user(db, mlflow, team_roles)


@router.get("/{experiment_id}", response_model=ExperimentDetail)
async def get_experiment(
    experiment_id: str,
    team_id: uuid.UUID = Depends(require_experiment_permission(Permission.EXPERIMENT_READ)),
    team_roles: list[TeamRole] = Depends(get_team_roles),
    mlflow: httpx.AsyncClient = Depends(get_mlflow_client),
) -> ExperimentDetail:
    """Get experiment detail by ID."""
    team_name = next((tr.team_name for tr in team_roles if tr.team_id == team_id), "")
    return await get_experiment_detail(mlflow, experiment_id, team_name)


@router.get("/{experiment_id}/runs", response_model=RunListResponse)
async def get_runs(
    experiment_id: str,
    max_results: int = 25,
    order_by: str = "start_time DESC",
    page_token: str | None = None,
    team_id: uuid.UUID = Depends(require_experiment_permission(Permission.RUN_READ)),
    mlflow: httpx.AsyncClient = Depends(get_mlflow_client),
) -> RunListResponse:
    """List runs for an experiment."""
    return await list_runs(mlflow, experiment_id, max_results, order_by, page_token)


@router.get("/{experiment_id}/runs/{run_id}", response_model=RunDetail)
async def get_run(
    experiment_id: str,
    run_id: str,
    team_id: uuid.UUID = Depends(require_experiment_permission(Permission.RUN_READ)),
    mlflow: httpx.AsyncClient = Depends(get_mlflow_client),
) -> RunDetail:
    """Get full run detail."""
    return await get_run_detail(mlflow, run_id, experiment_id)


@router.post("/{experiment_id}/runs", response_model=StartRunResponse, status_code=201)
async def start_run(
    experiment_id: str,
    body: StartRunRequest,
    team_id: uuid.UUID = Depends(require_experiment_permission(Permission.RUN_START)),
    db: AsyncSession = Depends(get_db),
    mlflow: httpx.AsyncClient = Depends(get_mlflow_client),
    s3: S3Client = Depends(get_s3_client),
    user: TokenClaims = Depends(get_current_user),
) -> StartRunResponse:
    """Start an evaluation run against a dataset. Requires engineer or owner role."""
    result = await run_evaluation(
        mlflow=mlflow,
        s3=s3,
        db=db,
        experiment_id=experiment_id,
        dataset_id=body.dataset_id,
        dataset_version=body.dataset_version,
        run_name=body.run_name,
        user_sub=user.sub,
        experiment_team_id=team_id,
    )
    await log_audit_event(
        db,
        user_sub=user.sub,
        team_id=team_id,
        action="run.start",
        resource=f"experiment={experiment_id} run={result.run_id}",
    )
    return result
