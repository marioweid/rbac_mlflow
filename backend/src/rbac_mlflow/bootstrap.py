import logging

from sqlalchemy import select

from rbac_mlflow.config import settings
from rbac_mlflow.db import async_session_factory
from rbac_mlflow.models import GroupRoleMapping, Team
from rbac_mlflow.rbac.constants import Role

logger = logging.getLogger(__name__)


async def run_bootstrap() -> None:
    """Insert default team + group mappings if group_role_mappings is empty.

    Safe to call on every startup: only acts when the table has zero rows.
    Controlled by BOOTSTRAP_ADMIN_GROUP and BOOTSTRAP_TEAM_NAME env vars.
    """
    async with async_session_factory() as session:
        result = await session.execute(select(GroupRoleMapping.id).limit(1))
        if result.first() is not None:
            return

        team_name = settings.bootstrap_team_name
        team = Team(name=team_name)
        session.add(team)
        await session.flush()

        role_suffix_map = {
            "owners": Role.OWNER,
            "engineers": Role.ENGINEER,
            "readers": Role.READER,
        }
        for suffix, role in role_suffix_map.items():
            mapping = GroupRoleMapping(
                group_name=f"/{team_name}/{suffix}",
                team_id=team.id,
                role=role,
            )
            session.add(mapping)

        await session.commit()
        logger.info(
            "Bootstrapped team '%s' with %d group mappings",
            team_name,
            len(role_suffix_map),
        )
