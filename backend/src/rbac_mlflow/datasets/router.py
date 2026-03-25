import uuid

import httpx
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

import rbac_mlflow.datasets.service as svc
from rbac_mlflow.auth.dependencies import get_current_user
from rbac_mlflow.auth.providers.base import TokenClaims
from rbac_mlflow.datasets.schemas import (
    DatasetCreate,
    DatasetDetail,
    DatasetResponse,
    DatasetSummary,
    DatasetUpdate,
)
from rbac_mlflow.db import get_db
from rbac_mlflow.mlflow_client import get_mlflow_client
from rbac_mlflow.rbac.constants import Permission
from rbac_mlflow.rbac.dependencies import require_experiment_permission
from rbac_mlflow.rbac.service import log_audit_event

# Mounted under /experiments in main.py so final paths are:
#   /experiments/{experiment_id}/datasets/...
router = APIRouter(tags=["datasets"])


@router.get("/{experiment_id}/datasets", response_model=list[DatasetSummary])
async def list_datasets(
    experiment_id: str,
    team_id: uuid.UUID = Depends(require_experiment_permission(Permission.DATASET_READ)),
    mlflow: httpx.AsyncClient = Depends(get_mlflow_client),
) -> list[DatasetSummary]:
    return await svc.list_datasets(mlflow, experiment_id)


@router.get("/{experiment_id}/datasets/{dataset_id}", response_model=DatasetDetail)
async def get_dataset(
    experiment_id: str,
    dataset_id: str,
    team_id: uuid.UUID = Depends(require_experiment_permission(Permission.DATASET_READ)),
    mlflow: httpx.AsyncClient = Depends(get_mlflow_client),
) -> DatasetDetail:
    return await svc.get_dataset_detail(mlflow, dataset_id, experiment_id)


@router.post(
    "/{experiment_id}/datasets",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_dataset(
    experiment_id: str,
    body: DatasetCreate,
    team_id: uuid.UUID = Depends(require_experiment_permission(Permission.DATASET_WRITE)),
    user: TokenClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    mlflow: httpx.AsyncClient = Depends(get_mlflow_client),
) -> DatasetResponse:
    result = await svc.create_dataset(mlflow, experiment_id, body, user.sub)
    await log_audit_event(db, user.sub, team_id, "dataset.create", result.name)
    return result


@router.put("/{experiment_id}/datasets/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(
    experiment_id: str,
    dataset_id: str,
    body: DatasetUpdate,
    team_id: uuid.UUID = Depends(require_experiment_permission(Permission.DATASET_WRITE)),
    user: TokenClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    mlflow: httpx.AsyncClient = Depends(get_mlflow_client),
) -> DatasetResponse:
    result = await svc.update_dataset(mlflow, dataset_id, experiment_id, body, user.sub)
    await log_audit_event(db, user.sub, team_id, "dataset.update", dataset_id)
    return result


@router.delete("/{experiment_id}/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(
    experiment_id: str,
    dataset_id: str,
    team_id: uuid.UUID = Depends(require_experiment_permission(Permission.DATASET_WRITE)),
    user: TokenClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    mlflow: httpx.AsyncClient = Depends(get_mlflow_client),
) -> None:
    await svc.delete_dataset(mlflow, dataset_id, experiment_id)
    await log_audit_event(db, user.sub, team_id, "dataset.delete", dataset_id)
