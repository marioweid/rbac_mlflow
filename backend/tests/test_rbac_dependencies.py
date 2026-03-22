import uuid

import pytest
from fastapi import HTTPException

from rbac_mlflow.rbac.constants import Permission
from rbac_mlflow.rbac.dependencies import require_permission
from rbac_mlflow.rbac.schemas import TeamRole

TEAM_ALPHA_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEAM_BETA_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


class TestRequirePermission:
    @pytest.mark.asyncio
    async def test_allows_authorized(self, carol_team_roles: list[TeamRole]) -> None:
        dep = require_permission(Permission.TEAM_MANAGE)
        # Should not raise
        await dep(team_id=TEAM_ALPHA_ID, team_roles=carol_team_roles)

    @pytest.mark.asyncio
    async def test_denies_unauthorized(self, alice_team_roles: list[TeamRole]) -> None:
        dep = require_permission(Permission.TEAM_MANAGE)
        with pytest.raises(HTTPException) as exc_info:
            await dep(team_id=TEAM_ALPHA_ID, team_roles=alice_team_roles)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_denies_wrong_team(self, carol_team_roles: list[TeamRole]) -> None:
        dep = require_permission(Permission.EXPERIMENT_READ)
        with pytest.raises(HTTPException) as exc_info:
            await dep(team_id=TEAM_BETA_ID, team_roles=carol_team_roles)
        assert exc_info.value.status_code == 403
