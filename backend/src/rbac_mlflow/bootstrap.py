import logging

from sqlalchemy import select

from rbac_mlflow.config import settings
from rbac_mlflow.db import async_session_factory
from rbac_mlflow.models import GroupRoleMapping, Team
from rbac_mlflow.rbac.constants import Role

logger = logging.getLogger(__name__)

_ROLE_SUFFIXES: dict[str, Role] = {
    "owners": Role.OWNER,
    "engineers": Role.ENGINEER,
    "readers": Role.READER,
}

# Teams seeded on first boot. Each entry is (team_name, group_prefix).
# The group prefix follows the pattern /{group_prefix}/{suffix}.
_BOOTSTRAP_TEAMS: list[tuple[str, str]] = [
    (settings.bootstrap_team_name, settings.bootstrap_team_name),
    ("team-beta", "team-beta"),
]


async def run_bootstrap() -> None:
    """Insert default teams + group mappings if group_role_mappings is empty.

    Safe to call on every startup: only acts when the table has zero rows.
    Primary team is controlled by BOOTSTRAP_TEAM_NAME env var.
    """
    async with async_session_factory() as session:
        result = await session.execute(select(GroupRoleMapping.id).limit(1))
        if result.first() is not None:
            return

        total_mappings = 0
        for team_name, group_prefix in _BOOTSTRAP_TEAMS:
            team = Team(name=team_name)
            session.add(team)
            await session.flush()

            for suffix, role in _ROLE_SUFFIXES.items():
                mapping = GroupRoleMapping(
                    group_name=f"/{group_prefix}/{suffix}",
                    team_id=team.id,
                    role=role,
                )
                session.add(mapping)
            total_mappings += len(_ROLE_SUFFIXES)

        await session.commit()
        logger.info(
            "Bootstrapped %d teams with %d group mappings total",
            len(_BOOTSTRAP_TEAMS),
            total_mappings,
        )
