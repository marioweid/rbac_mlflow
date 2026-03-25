import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rbac_mlflow.auth.dependencies import get_current_user
from rbac_mlflow.auth.providers.base import TokenClaims
from rbac_mlflow.db import get_db
from rbac_mlflow.models import TeamExperiment
from rbac_mlflow.rbac.constants import Permission
from rbac_mlflow.rbac.schemas import TeamRole
from rbac_mlflow.rbac.service import check_permission, resolve_teams


async def get_team_roles(
    user: TokenClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TeamRole]:
    """Resolve the current user's team memberships from the DB."""
    return await resolve_teams(db, user.groups)


def require_permission(permission: Permission) -> Callable:
    """Factory returning a FastAPI dependency that checks a permission.

    Usage:
        @router.get("/teams/{team_id}/experiments")
        async def list_experiments(
            team_id: uuid.UUID,
            _: None = Depends(require_permission(Permission.EXPERIMENT_READ)),
        ):
            ...
    """

    async def dependency(
        team_id: uuid.UUID,
        team_roles: list[TeamRole] = Depends(get_team_roles),
    ) -> None:
        if not check_permission(team_roles, permission, team_id):
            raise HTTPException(
                status_code=403,
                detail=f"Permission '{permission}' denied for team {team_id}",
            )

    return dependency


def require_team_owner() -> Callable:
    """Dependency that checks the user is an owner of the specified team."""
    return require_permission(Permission.TEAM_MANAGE)


def require_experiment_permission(permission: Permission) -> Callable:
    """Factory returning a dependency that resolves experiment → team, then checks permission.

    Returns the resolved team_id so route handlers can use it.

    Usage:
        @router.get("/experiments/{experiment_id}")
        async def get_exp(
            experiment_id: str,
            team_id: uuid.UUID = Depends(
                require_experiment_permission(Permission.EXPERIMENT_READ)
            ),
        ):
            ...
    """

    async def dependency(
        experiment_id: str,
        team_roles: list[TeamRole] = Depends(get_team_roles),
        db: AsyncSession = Depends(get_db),
    ) -> uuid.UUID:
        stmt = select(TeamExperiment.team_id).where(
            TeamExperiment.mlflow_experiment_id == experiment_id
        )
        result = await db.execute(stmt)
        row = result.first()
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Experiment '{experiment_id}' is not linked to any team",
            )
        team_id = row.team_id
        if not check_permission(team_roles, permission, team_id):
            raise HTTPException(
                status_code=403,
                detail=f"Permission '{permission}' denied for experiment {experiment_id}",
            )
        return team_id

    return dependency
