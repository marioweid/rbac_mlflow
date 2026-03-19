from jose import jwt as jose_jwt
from jose.exceptions import JWTError

from rbac_mlflow.auth.jwks import JWKSCache
from rbac_mlflow.auth.providers.base import TokenClaims
from rbac_mlflow.config import settings


class KeycloakProvider:
    """Validates JWTs issued by Keycloak."""

    def __init__(self) -> None:
        self._cache = JWKSCache(self.jwks_uri())

    def jwks_uri(self) -> str:
        return settings.jwks_uri

    async def validate_token(self, token: str) -> TokenClaims:
        # Decode header to get kid without verifying signature yet
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
            groups=payload.get("groups", []),
            raw=payload,
        )
