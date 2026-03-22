import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rbac_mlflow.models import AuditEvent, GroupRoleMapping, Team
from rbac_mlflow.rbac.constants import ROLE_PERMISSIONS, Permission, Role
from rbac_mlflow.rbac.schemas import TeamRole


async def resolve_teams(
    db: AsyncSession,
    groups: list[str],
) -> list[TeamRole]:
    """Map JWT group claims to (team, role) pairs.

    Queries group_role_mappings for all groups the user belongs to.
    Returns one TeamRole per (team, role) match.
    """
    if not groups:
        return []

    stmt = (
        select(GroupRoleMapping.team_id, Team.name, GroupRoleMapping.role)
        .join(Team, GroupRoleMapping.team_id == Team.id)
        .where(GroupRoleMapping.group_name.in_(groups))
    )
    result = await db.execute(stmt)
    return [
        TeamRole(team_id=row.team_id, team_name=row.name, role=row.role) for row in result.all()
    ]


def check_permission(
    team_roles: list[TeamRole],
    permission: Permission,
    team_id: uuid.UUID,
) -> bool:
    """Check whether the user has a specific permission on a team.

    Looks up the user's role for the given team in the pre-resolved
    team_roles list and checks against the role-permission matrix.
    """
    for tr in team_roles:
        if tr.team_id == team_id:
            role_perms = ROLE_PERMISSIONS.get(Role(tr.role), frozenset())
            if permission in role_perms:
                return True
    return False


async def log_audit_event(
    db: AsyncSession,
    user_sub: str,
    team_id: uuid.UUID | None,
    action: str,
    resource: str | None = None,
) -> None:
    """Write an entry to the audit_events table."""
    event = AuditEvent(
        user_sub=user_sub,
        team_id=team_id,
        action=action,
        resource=resource,
    )
    db.add(event)
    await db.commit()
