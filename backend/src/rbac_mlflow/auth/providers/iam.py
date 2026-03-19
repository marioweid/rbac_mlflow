from jose import jwt as jose_jwt
from jose.exceptions import JWTError

from rbac_mlflow.auth.jwks import JWKSCache
from rbac_mlflow.auth.providers.base import TokenClaims
from rbac_mlflow.config import settings


class IAMProvider:
    """Validates JWTs issued by the production IAM.

    Same logic as KeycloakProvider but reads a separate JWKS URI and
    issuer. In practice, the IAM may use a different groups claim name
    or nesting -- adjust the `_extract_groups` method if needed.
    """

    def __init__(self) -> None:
        self._cache = JWKSCache(self.jwks_uri())

    def jwks_uri(self) -> str:
        return settings.jwks_uri

    async def validate_token(self, token: str) -> TokenClaims:
        unverified = jose_jwt.get_unverified_header(token)
        kid = unverified.get("kid")
        if not kid:
            msg = "Token header missing 'kid'"
            raise JWTError(msg)

        key = await self._cache.get_key(kid)

        payload = jose_jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )

        return TokenClaims(
            sub=payload.get("sub", ""),
            email=payload.get("email", ""),
            groups=self._extract_groups(payload),
            raw=payload,
        )

    def _extract_groups(self, payload: dict[str, object]) -> list[str]:
        """Override-point for IAM-specific group claim extraction."""
        groups = payload.get("groups", [])
        if isinstance(groups, list):
            return [str(g) for g in groups]
        return []
