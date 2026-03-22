import uuid

import pytest

from rbac_mlflow.auth.providers.base import TokenClaims
from rbac_mlflow.rbac.schemas import TeamRole

TEAM_ALPHA_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEAM_BETA_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture
def alice_claims() -> TokenClaims:
    """Alice: reader in team-alpha."""
    return TokenClaims(
        sub="alice-id",
        email="alice@example.com",
        groups=["/team-alpha/readers"],
    )


@pytest.fixture
def bob_claims() -> TokenClaims:
    """Bob: engineer in team-alpha."""
    return TokenClaims(
        sub="bob-id",
        email="bob@example.com",
        groups=["/team-alpha/engineers"],
    )


@pytest.fixture
def carol_claims() -> TokenClaims:
    """Carol: owner in team-alpha."""
    return TokenClaims(
        sub="carol-id",
        email="carol@example.com",
        groups=["/team-alpha/owners"],
    )


@pytest.fixture
def alice_team_roles() -> list[TeamRole]:
    return [TeamRole(team_id=TEAM_ALPHA_ID, team_name="team-alpha", role="reader")]


@pytest.fixture
def bob_team_roles() -> list[TeamRole]:
    return [TeamRole(team_id=TEAM_ALPHA_ID, team_name="team-alpha", role="engineer")]


@pytest.fixture
def carol_team_roles() -> list[TeamRole]:
    return [TeamRole(team_id=TEAM_ALPHA_ID, team_name="team-alpha", role="owner")]
