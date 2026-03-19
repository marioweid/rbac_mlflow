import time
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt as jose_jwt

from rbac_mlflow.auth.providers.keycloak import KeycloakProvider

# Generate a test RSA key pair (done once at module level)
_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()
_public_pem = _public_key.public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()
_private_pem = _private_key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()

TEST_KID = "test-key-1"
TEST_ISSUER = "http://keycloak:8080/realms/rbac-mlflow"
TEST_AUDIENCE = "rbac-frontend"


def _make_token(
    sub: str = "user-123",
    email: str = "alice@example.com",
    groups: list[str] | None = None,
    exp_offset: int = 300,
) -> str:
    """Create a signed JWT for testing."""
    payload = {
        "sub": sub,
        "email": email,
        "groups": groups or ["/team-alpha/readers"],
        "iss": TEST_ISSUER,
        "aud": TEST_AUDIENCE,
        "exp": int(time.time()) + exp_offset,
        "iat": int(time.time()),
    }
    return jose_jwt.encode(payload, _private_pem, algorithm="RS256", headers={"kid": TEST_KID})


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    monkeypatch.setenv("JWT_ISSUER", TEST_ISSUER)
    monkeypatch.setenv("JWT_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setenv("JWKS_URI", "http://keycloak:8080/fake")


def _get_jwks_response() -> dict:
    """Build a JWKS response from the test public key."""
    from jose.backends import RSAKey as JoseRSAKey

    key = JoseRSAKey(_public_pem, "RS256")
    jwk_dict = key.to_dict()
    jwk_dict["kid"] = TEST_KID
    return {"keys": [jwk_dict]}


def _seed_cache(provider: KeycloakProvider) -> None:
    jwks = _get_jwks_response()
    provider._cache._keys = {k["kid"]: k for k in jwks["keys"]}
    provider._cache._fetched_at = time.monotonic()


@pytest.mark.asyncio
async def test_keycloak_provider_valid_token():
    provider = KeycloakProvider()

    with patch.object(provider._cache, "_refresh", new_callable=AsyncMock):
        _seed_cache(provider)

        token = _make_token(
            sub="alice-id",
            email="alice@example.com",
            groups=["/team-alpha/readers"],
        )
        claims = await provider.validate_token(token)

        assert claims.sub == "alice-id"
        assert claims.email == "alice@example.com"
        assert claims.groups == ["/team-alpha/readers"]


@pytest.mark.asyncio
async def test_keycloak_provider_expired_token():
    provider = KeycloakProvider()

    with patch.object(provider._cache, "_refresh", new_callable=AsyncMock):
        _seed_cache(provider)

        token = _make_token(exp_offset=-60)  # expired 60s ago

        with pytest.raises(Exception, match="expired"):
            await provider.validate_token(token)


@pytest.mark.asyncio
async def test_keycloak_provider_wrong_audience():
    provider = KeycloakProvider()

    with patch.object(provider._cache, "_refresh", new_callable=AsyncMock):
        _seed_cache(provider)

        payload = {
            "sub": "user-123",
            "email": "user@example.com",
            "groups": [],
            "iss": TEST_ISSUER,
            "aud": "wrong-audience",
            "exp": int(time.time()) + 300,
            "iat": int(time.time()),
        }
        token = jose_jwt.encode(
            payload,
            _private_pem,
            algorithm="RS256",
            headers={"kid": TEST_KID},
        )

        with pytest.raises(Exception, match="audience"):
            await provider.validate_token(token)
