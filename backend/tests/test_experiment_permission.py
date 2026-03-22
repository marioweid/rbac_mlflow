import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from rbac_mlflow.rbac.constants import Permission
from rbac_mlflow.rbac.dependencies import require_experiment_permission
from rbac_mlflow.rbac.schemas import TeamRole

TEAM_ALPHA_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEAM_BETA_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _mock_db_with_experiment(team_id: uuid.UUID | None):
    """Return a mock AsyncSession that returns the given team_id for experiment lookup."""
    db = AsyncMock()
    mock_result = MagicMock()
    if team_id is not None:
        mock_row = MagicMock()
        mock_row.team_id = team_id
        mock_result.first.return_value = mock_row
    else:
        mock_result.first.return_value = None
    db.execute.return_value = mock_result
    return db


class TestRequireExperimentPermission:
    @pytest.mark.asyncio
    async def test_allows_authorized(self, carol_team_roles: list[TeamRole]) -> None:
        dep = require_experiment_permission(Permission.EXPERIMENT_READ)
        db = _mock_db_with_experiment(TEAM_ALPHA_ID)
        result = await dep(
            experiment_id="exp-1",
            team_roles=carol_team_roles,
            db=db,
        )
        assert result == TEAM_ALPHA_ID

    @pytest.mark.asyncio
    async def test_denies_unauthorized(self, alice_team_roles: list[TeamRole]) -> None:
        dep = require_experiment_permission(Permission.TEAM_MANAGE)
        db = _mock_db_with_experiment(TEAM_ALPHA_ID)
        with pytest.raises(HTTPException) as exc_info:
            await dep(
                experiment_id="exp-1",
                team_roles=alice_team_roles,
                db=db,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_404_for_unlinked(self, carol_team_roles: list[TeamRole]) -> None:
        dep = require_experiment_permission(Permission.EXPERIMENT_READ)
        db = _mock_db_with_experiment(None)
        with pytest.raises(HTTPException) as exc_info:
            await dep(
                experiment_id="unlinked",
                team_roles=carol_team_roles,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_denies_wrong_team(self, alice_team_roles: list[TeamRole]) -> None:
        dep = require_experiment_permission(Permission.EXPERIMENT_READ)
        db = _mock_db_with_experiment(TEAM_BETA_ID)
        with pytest.raises(HTTPException) as exc_info:
            await dep(
                experiment_id="beta-exp",
                team_roles=alice_team_roles,
                db=db,
            )
        assert exc_info.value.status_code == 403
