from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TokenClaims:
    sub: str
    email: str
    groups: list[str] = field(default_factory=list)
    raw: dict[str, object] = field(default_factory=dict, repr=False)


class AuthProvider(Protocol):
    async def validate_token(self, token: str) -> TokenClaims:
        """Validate a JWT and return extracted claims.

        Raises jose.JWTError or subclass on invalid/expired tokens.
        """
        ...

    def jwks_uri(self) -> str:
        """Return the JWKS endpoint URL for this provider."""
        ...
