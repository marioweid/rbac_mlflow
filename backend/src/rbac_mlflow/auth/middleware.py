from fastapi import Request, Response
from jose.exceptions import JWTError
from starlette.middleware.base import BaseHTTPMiddleware

from rbac_mlflow.auth.provider import get_auth_provider

UNPROTECTED_PATHS = frozenset({"/health", "/docs", "/openapi.json"})


class AuthMiddleware(BaseHTTPMiddleware):
    """Extract and validate JWT from every request.

    Attaches TokenClaims to request.state.claims on success.
    Returns 401 for missing/invalid tokens.
    Skips validation for health and docs endpoints.
    """

    async def dispatch(self, request: Request, call_next: object) -> Response:
        if request.url.path in UNPROTECTED_PATHS:
            return await call_next(request)

        token = self._extract_token(request)
        if not token:
            return Response(
                content='{"detail":"Missing authentication token"}',
                status_code=401,
                media_type="application/json",
            )

        provider = get_auth_provider()
        try:
            claims = await provider.validate_token(token)
        except (JWTError, KeyError) as exc:
            return Response(
                content=f'{{"detail":"Invalid token: {exc}"}}',
                status_code=401,
                media_type="application/json",
            )

        request.state.claims = claims
        return await call_next(request)

    def _extract_token(self, request: Request) -> str | None:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header.removeprefix("Bearer ")
        return None
