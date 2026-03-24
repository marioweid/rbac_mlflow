import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
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
from rbac_mlflow.rbac.constants import Permission
from rbac_mlflow.rbac.dependencies import (
    get_team_roles,
    require_dataset_permission,
)
from rbac_mlflow.rbac.schemas import TeamRole
from rbac_mlflow.rbac.service import check_permission, log_audit_event
from rbac_mlflow.s3_client import S3Client, get_s3_client

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=list[DatasetSummary])
async def list_datasets(
    team_roles: list[TeamRole] = Depends(get_team_roles),
    db: AsyncSession = Depends(get_db),
) -> list[DatasetSummary]:
    return await svc.list_datasets(db, team_roles)


@router.get("/{dataset_id}", response_model=DatasetDetail)
async def get_dataset(
    dataset_id: uuid.UUID,
    team_id: uuid.UUID = Depends(require_dataset_permission(Permission.DATASET_READ)),
    team_roles: list[TeamRole] = Depends(get_team_roles),
    db: AsyncSession = Depends(get_db),
    s3: S3Client = Depends(get_s3_client),
) -> DatasetDetail:
    team_name = next((tr.team_name for tr in team_roles if tr.team_id == team_id), "")
    return await svc.get_dataset_detail(db, s3, dataset_id, team_name)


@router.get("/{dataset_id}/versions/{version}", response_model=list[dict[str, Any]])
async def get_dataset_version(
    dataset_id: uuid.UUID,
    version: int,
    team_id: uuid.UUID = Depends(require_dataset_permission(Permission.DATASET_READ)),
    db: AsyncSession = Depends(get_db),
    s3: S3Client = Depends(get_s3_client),
) -> list[dict[str, Any]]:
    return await svc.get_dataset_version_rows(db, s3, dataset_id, version)


@router.post("", response_model=DatasetResponse, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    body: DatasetCreate,
    team_roles: list[TeamRole] = Depends(get_team_roles),
    user: TokenClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    s3: S3Client = Depends(get_s3_client),
) -> DatasetResponse:
    team_role = next((tr for tr in team_roles if tr.team_name == body.team_name), None)
    if team_role is None:
        raise HTTPException(
            status_code=403, detail=f"No access to team '{body.team_name}'"
        )
    if not check_permission(team_roles, Permission.DATASET_WRITE, team_role.team_id):
        raise HTTPException(
            status_code=403,
            detail=f"Permission '{Permission.DATASET_WRITE}' denied for team '{body.team_name}'",
        )
    result = await svc.create_dataset(
        db, s3, team_role.team_id, body.team_name, body, user.sub
    )
    await log_audit_event(db, user.sub, team_role.team_id, "dataset.create", result.name)
    return result


@router.put("/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(
    dataset_id: uuid.UUID,
    body: DatasetUpdate,
    team_id: uuid.UUID = Depends(require_dataset_permission(Permission.DATASET_WRITE)),
    team_roles: list[TeamRole] = Depends(get_team_roles),
    user: TokenClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    s3: S3Client = Depends(get_s3_client),
) -> DatasetResponse:
    team_name = next((tr.team_name for tr in team_roles if tr.team_id == team_id), "")
    result = await svc.update_dataset(db, s3, dataset_id, team_name, body, user.sub)
    await log_audit_event(db, user.sub, team_id, "dataset.update", str(dataset_id))
    return result


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(
    dataset_id: uuid.UUID,
    team_id: uuid.UUID = Depends(require_dataset_permission(Permission.DATASET_WRITE)),
    user: TokenClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await svc.soft_delete_dataset(db, dataset_id)
    await log_audit_event(db, user.sub, team_id, "dataset.delete", str(dataset_id))
