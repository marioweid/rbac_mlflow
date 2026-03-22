import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rbac_mlflow.auth.dependencies import get_current_user
from rbac_mlflow.auth.providers.base import TokenClaims
from rbac_mlflow.db import get_db
from rbac_mlflow.models import GroupRoleMapping, Team, TeamExperiment
from rbac_mlflow.rbac.dependencies import get_team_roles, require_team_owner
from rbac_mlflow.rbac.schemas import (
    ExperimentLinkCreate,
    ExperimentLinkResponse,
    MappingCreate,
    MappingResponse,
    TeamCreate,
    TeamResponse,
    TeamRole,
)
from rbac_mlflow.rbac.service import log_audit_event

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/teams", response_model=TeamResponse, status_code=201)
async def create_team(
    body: TeamCreate,
    user: TokenClaims = Depends(get_current_user),
    team_roles: list[TeamRole] = Depends(get_team_roles),
    db: AsyncSession = Depends(get_db),
) -> Team:
    """Create a new team. Requires owner role on any existing team."""
    is_any_owner = any(tr.role == "owner" for tr in team_roles)
    if not is_any_owner:
        raise HTTPException(status_code=403, detail="Only owners can create teams")

    team = Team(name=body.name)
    db.add(team)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Team '{body.name}' already exists") from None
    await db.refresh(team)
    await log_audit_event(db, user.sub, team.id, "team.create", team.name)
    return team


@router.post(
    "/teams/{team_id}/mappings",
    response_model=MappingResponse,
    status_code=201,
)
async def create_mapping(
    team_id: uuid.UUID,
    body: MappingCreate,
    user: TokenClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_team_owner()),
) -> GroupRoleMapping:
    """Add a group-to-role mapping for a team."""
    mapping = GroupRoleMapping(
        group_name=body.group_name,
        team_id=team_id,
        role=body.role,
    )
    db.add(mapping)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Mapping for group '{body.group_name}' on this team already exists",
        ) from None
    await db.refresh(mapping)
    await log_audit_event(
        db,
        user.sub,
        team_id,
        "mapping.create",
        f"{body.group_name} -> {body.role}",
    )
    return mapping


@router.delete("/teams/{team_id}/mappings/{mapping_id}", status_code=204)
async def delete_mapping(
    team_id: uuid.UUID,
    mapping_id: uuid.UUID,
    user: TokenClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_team_owner()),
) -> None:
    """Remove a group-to-role mapping."""
    result = await db.execute(
        delete(GroupRoleMapping).where(
            GroupRoleMapping.id == mapping_id,
            GroupRoleMapping.team_id == team_id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Mapping not found")
    await db.commit()
    await log_audit_event(db, user.sub, team_id, "mapping.delete", str(mapping_id))


@router.post(
    "/teams/{team_id}/experiments",
    response_model=ExperimentLinkResponse,
    status_code=201,
)
async def link_experiment(
    team_id: uuid.UUID,
    body: ExperimentLinkCreate,
    user: TokenClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_team_owner()),
) -> TeamExperiment:
    """Link an MLflow experiment to a team."""
    link = TeamExperiment(
        team_id=team_id,
        mlflow_experiment_id=body.mlflow_experiment_id,
    )
    db.add(link)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Experiment already linked to this team",
        ) from None
    return link


@router.delete(
    "/teams/{team_id}/experiments/{experiment_id}",
    status_code=204,
)
async def unlink_experiment(
    team_id: uuid.UUID,
    experiment_id: str,
    user: TokenClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_team_owner()),
) -> None:
    """Unlink an MLflow experiment from a team."""
    result = await db.execute(
        delete(TeamExperiment).where(
            TeamExperiment.team_id == team_id,
            TeamExperiment.mlflow_experiment_id == experiment_id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Experiment link not found")
    await db.commit()
    await log_audit_event(db, user.sub, team_id, "experiment.unlink", experiment_id)
