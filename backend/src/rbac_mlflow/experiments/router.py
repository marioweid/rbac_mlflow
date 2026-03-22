import uuid

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rbac_mlflow.db import get_db
from rbac_mlflow.experiments.schemas import (
    ExperimentDetail,
    ExperimentSummary,
    RunDetail,
    RunListResponse,
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
