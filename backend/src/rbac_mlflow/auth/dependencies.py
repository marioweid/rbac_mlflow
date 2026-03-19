from fastapi import Request
from fastapi.exceptions import HTTPException

from rbac_mlflow.auth.providers.base import TokenClaims


def get_current_user(request: Request) -> TokenClaims:
    """FastAPI dependency: extract the authenticated user's claims.

    Must be used after AuthMiddleware has run.
    """
    claims = getattr(request.state, "claims", None)
    if claims is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return claims
