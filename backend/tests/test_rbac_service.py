import uuid

import pytest

from rbac_mlflow.rbac.constants import Permission
from rbac_mlflow.rbac.schemas import TeamRole
from rbac_mlflow.rbac.service import check_permission, resolve_teams

TEAM_ALPHA_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEAM_BETA_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


class TestCheckPermission:
    def test_reader_can_read_experiments(self, alice_team_roles: list[TeamRole]) -> None:
        assert check_permission(alice_team_roles, Permission.EXPERIMENT_READ, TEAM_ALPHA_ID)

    def test_reader_can_read_runs(self, alice_team_roles: list[TeamRole]) -> None:
        assert check_permission(alice_team_roles, Permission.RUN_READ, TEAM_ALPHA_ID)

    def test_reader_can_read_datasets(self, alice_team_roles: list[TeamRole]) -> None:
        assert check_permission(alice_team_roles, Permission.DATASET_READ, TEAM_ALPHA_ID)

    def test_reader_cannot_start_run(self, alice_team_roles: list[TeamRole]) -> None:
        assert not check_permission(alice_team_roles, Permission.RUN_START, TEAM_ALPHA_ID)

    def test_reader_cannot_write_dataset(self, alice_team_roles: list[TeamRole]) -> None:
        assert not check_permission(alice_team_roles, Permission.DATASET_WRITE, TEAM_ALPHA_ID)

    def test_reader_cannot_manage_team(self, alice_team_roles: list[TeamRole]) -> None:
        assert not check_permission(alice_team_roles, Permission.TEAM_MANAGE, TEAM_ALPHA_ID)

    def test_engineer_can_start_run(self, bob_team_roles: list[TeamRole]) -> None:
        assert check_permission(bob_team_roles, Permission.RUN_START, TEAM_ALPHA_ID)

    def test_engineer_can_write_dataset(self, bob_team_roles: list[TeamRole]) -> None:
        assert check_permission(bob_team_roles, Permission.DATASET_WRITE, TEAM_ALPHA_ID)

    def test_engineer_cannot_manage_team(self, bob_team_roles: list[TeamRole]) -> None:
        assert not check_permission(bob_team_roles, Permission.TEAM_MANAGE, TEAM_ALPHA_ID)

    def test_owner_has_all_permissions(self, carol_team_roles: list[TeamRole]) -> None:
        for perm in Permission:
            assert check_permission(carol_team_roles, perm, TEAM_ALPHA_ID)

    def test_wrong_team_denied(self, carol_team_roles: list[TeamRole]) -> None:
        assert not check_permission(carol_team_roles, Permission.EXPERIMENT_READ, TEAM_BETA_ID)

    def test_empty_roles_denied(self) -> None:
        assert not check_permission([], Permission.EXPERIMENT_READ, TEAM_ALPHA_ID)


class TestResolveTeams:
    @pytest.mark.asyncio
    async def test_empty_groups_returns_empty(self) -> None:
        result = await resolve_teams(None, [])  # type: ignore[arg-type]
        assert result == []
