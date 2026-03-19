from fastapi import APIRouter, Depends

from rbac_mlflow.auth.dependencies import get_current_user
from rbac_mlflow.auth.providers.base import TokenClaims

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
async def me(
    user: TokenClaims = Depends(get_current_user),  # noqa: B008
) -> dict[str, object]:
    """Return the current user's resolved JWT claims.

    Useful for frontend debugging and verifying token contents.
    """
    return {
        "sub": user.sub,
        "email": user.email,
        "groups": user.groups,
    }
