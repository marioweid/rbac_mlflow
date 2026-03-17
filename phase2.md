# Phase 2 -- Authentication Implementation Guide

Phase 1 delivered a running docker-compose stack with all services healthy.
Phase 2 adds OIDC login, JWT validation, and an auth provider abstraction so
that the same codebase works with Keycloak (local) and a custom IAM (prod).

---

## 0. Design Decisions (Resolved Discrepancies)

Before writing code, these conflicts between `tasks.md` and `architecture.md`
must be resolved. Each decision is final -- no further discussion needed.

| # | Issue | Resolution |
|---|-------|------------|
| 1 | **JWT storage**: tasks.md says httpOnly cookie; architecture.md says in-memory Bearer header | **httpOnly cookie.** Auth.js v5 handles this natively. Next.js server components and route handlers read the cookie and forward it to the API. The API reads `Authorization: Bearer <token>` (Auth.js sets this via the Next.js rewrite proxy) or falls back to reading the cookie directly. No XSS exposure, no client-side JS ever sees the token. |
| 2 | **Realm name**: tasks.md says `mlflow-rbac`; realm-export.json says `rbac-mlflow` | **Keep `rbac-mlflow`** (what the code and Keycloak use). Update tasks.md and architecture.md to match. |
| 3 | **Group names**: tasks.md says flat (`rag-service-owner`); Keycloak uses hierarchical (`/team-alpha/owners`) | **Keep hierarchical.** The path format `/team-name/role` is parsed by the RBAC engine in Phase 3. No flat group names needed. |
| 4 | **`full.path` mapper**: tasks.md says off; realm-export has `true` | **Keep `true`.** The RBAC engine will parse paths like `/team-alpha/readers` to extract team and role. |
| 5 | **Keycloak clients**: tasks.md says two (`api` bearer-only + `frontend` public); we only have `rbac-frontend` | **Skip the `api` client.** The API validates tokens issued to the `rbac-frontend` client. A bearer-only client adds nothing. |
| 6 | **JWKS URL for API container**: `.env.example` uses `https://keycloak.rbac.local/...` (goes through Traefik + self-signed TLS) | **Use Docker-internal URL** `http://keycloak:8080/realms/rbac-mlflow/protocol/openid-connect/certs`. Rename env var from `JWKS_URL` to `JWKS_URI` and set the internal URL as the default for local dev. |

---

## 1. Keycloak Realm Export Changes

The `rbac-frontend` client is currently `publicClient: true`. Auth.js v5 works
best with a **confidential** client (it runs server-side and can keep a secret).
Change the client to confidential so Auth.js can use the client secret for token
exchange.

### File: `keycloak/realm-export.json`

Replace the existing `clients` array entry for `rbac-frontend` with:

```json
{
  "clientId": "rbac-frontend",
  "name": "RBAC MLflow Frontend",
  "enabled": true,
  "publicClient": false,
  "clientAuthenticatorType": "client-secret",
  "secret": "dev-secret-change-in-prod",
  "standardFlowEnabled": true,
  "implicitFlowEnabled": false,
  "directAccessGrantsEnabled": false,
  "serviceAccountsEnabled": false,
  "attributes": {
    "pkce.code.challenge.method": "S256"
  },
  "redirectUris": [
    "https://rbac.local/*",
    "http://localhost:3000/*"
  ],
  "webOrigins": [
    "https://rbac.local",
    "http://localhost:3000"
  ],
  "protocolMappers": [
    {
      "name": "groups",
      "protocol": "openid-connect",
      "protocolMapper": "oidc-group-membership-mapper",
      "consentRequired": false,
      "config": {
        "full.path": "true",
        "id.token.claim": "true",
        "access.token.claim": "true",
        "claim.name": "groups",
        "userinfo.token.claim": "true"
      }
    }
  ]
}
```

Key changes:
- `publicClient` → `false`
- Added `clientAuthenticatorType` and `secret`
- PKCE is still enforced (defense in depth, not the sole auth mechanism)

After editing, **delete the Keycloak Docker volume** so it re-imports:

```bash
docker compose down
docker volume rm rbac_mlflow_postgres_data
docker compose up -d
```

> Note: this also wipes the Postgres databases. In local dev this is fine since
> all state is seeded from migrations/exports.

---

## 2. Backend: New Dependencies

### File: `backend/pyproject.toml` -- add to `dependencies`

```toml
dependencies = [
    "fastapi==0.135.1",
    "uvicorn[standard]==0.42.0",
    "python-jose[cryptography]==3.5.0",
    "httpx==0.28.1",
    "pydantic-settings==2.9.1",
]
```

- **httpx** (already a dev dep, promote to runtime): fetches JWKS from Keycloak
  at startup and on cache refresh.
- **pydantic-settings**: typed environment variable loading for `config.py`.

After editing, regenerate the lockfile:

```bash
cd backend && uv lock && uv sync
```

---

## 3. Backend: Config

### New file: `backend/src/rbac_mlflow/config.py`

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    auth_provider: str = "keycloak"
    jwt_issuer: str = "http://keycloak:8080/realms/rbac-mlflow"
    jwt_audience: str = "rbac-frontend"
    jwks_uri: str = (
        "http://keycloak:8080/realms/rbac-mlflow"
        "/protocol/openid-connect/certs"
    )

    database_url: str = (
        "postgresql+asyncpg://rbac:changeme@postgres:5432/rbac_db"
    )
    mlflow_tracking_uri: str = "http://mlflow:5000"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
```

The `Settings` class reads all env vars at import time. Every field has a
sensible local-dev default so the app starts with zero config in docker-compose.

---

## 4. Backend: Auth Provider Protocol

### New file: `backend/src/rbac_mlflow/auth/__init__.py`

Empty file. Makes `auth` a package.

### New file: `backend/src/rbac_mlflow/auth/providers/__init__.py`

Empty file.

### New file: `backend/src/rbac_mlflow/auth/providers/base.py`

```python
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
```

`TokenClaims` is a frozen dataclass (not Pydantic) because it is an internal
domain object, not an API schema. The `raw` field preserves the full decoded
payload for debugging.

---

## 5. Backend: JWKS Cache

Both providers need to fetch and cache the JWKS key set. Extract this into a
shared module so both providers reuse it.

### New file: `backend/src/rbac_mlflow/auth/jwks.py`

```python
import time

import httpx
from jose import jwk
from jose.utils import base64url_decode


class JWKSCache:
    """Fetches and caches a JWKS key set with a TTL."""

    def __init__(self, uri: str, ttl_seconds: int = 300) -> None:
        self._uri = uri
        self._ttl = ttl_seconds
        self._keys: dict[str, object] = {}
        self._fetched_at: float = 0

    async def get_key(self, kid: str) -> object:
        if not self._keys or self._is_stale():
            await self._refresh()

        key = self._keys.get(kid)
        if key is None:
            # Key might have rotated -- force one refresh and retry
            await self._refresh()
            key = self._keys.get(kid)

        if key is None:
            msg = f"No key found for kid={kid}"
            raise KeyError(msg)
        return key

    def _is_stale(self) -> bool:
        return (time.monotonic() - self._fetched_at) > self._ttl

    async def _refresh(self) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(self._uri, timeout=10)
            resp.raise_for_status()
        data = resp.json()
        self._keys = {k["kid"]: k for k in data.get("keys", [])}
        self._fetched_at = time.monotonic()
```

The cache lives for the lifetime of the provider instance (which lives for the
lifetime of the app). On first request it fetches the JWKS; subsequent requests
use the cache until `ttl_seconds` elapses. If a `kid` isn't found, it forces
one re-fetch in case keys rotated.

---

## 6. Backend: Keycloak Provider

### New file: `backend/src/rbac_mlflow/auth/providers/keycloak.py`

```python
from jose import jwt as jose_jwt
from jose.exceptions import JWTError

from rbac_mlflow.auth.jwks import JWKSCache
from rbac_mlflow.auth.providers.base import AuthProvider, TokenClaims
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
```

`python-jose` handles signature verification, expiry checking, audience and
issuer validation. The provider only needs to supply the right key.

---

## 7. Backend: Custom IAM Provider

### New file: `backend/src/rbac_mlflow/auth/providers/iam.py`

```python
from jose import jwt as jose_jwt
from jose.exceptions import JWTError

from rbac_mlflow.auth.jwks import JWKSCache
from rbac_mlflow.auth.providers.base import AuthProvider, TokenClaims
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
```

Both providers share the same structure. The IAM provider has an
`_extract_groups` override point for when the production IAM uses a different
claim format.

---

## 8. Backend: Provider Factory

### New file: `backend/src/rbac_mlflow/auth/provider.py`

```python
from rbac_mlflow.auth.providers.base import AuthProvider
from rbac_mlflow.auth.providers.iam import IAMProvider
from rbac_mlflow.auth.providers.keycloak import KeycloakProvider
from rbac_mlflow.config import settings

_PROVIDERS: dict[str, type[AuthProvider]] = {
    "keycloak": KeycloakProvider,
    "iam": IAMProvider,
}

_instance: AuthProvider | None = None


def get_auth_provider() -> AuthProvider:
    """Return the singleton auth provider based on AUTH_PROVIDER env var."""
    global _instance  # noqa: PLW0603
    if _instance is None:
        provider_cls = _PROVIDERS.get(settings.auth_provider)
        if provider_cls is None:
            msg = (
                f"Unknown AUTH_PROVIDER={settings.auth_provider!r}. "
                f"Valid: {', '.join(_PROVIDERS)}"
            )
            raise ValueError(msg)
        _instance = provider_cls()
    return _instance
```

The provider is created lazily on first use and cached for the app lifetime.

---

## 9. Backend: Auth Middleware

### New file: `backend/src/rbac_mlflow/auth/middleware.py`

```python
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

    async def dispatch(
        self, request: Request, call_next: object
    ) -> Response:
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
```

The middleware:
1. Skips `/health`, `/docs`, `/openapi.json`
2. Extracts the Bearer token from the `Authorization` header
3. Validates via the configured auth provider
4. Attaches `TokenClaims` to `request.state.claims`
5. Returns 401 with a JSON body on failure

---

## 10. Backend: FastAPI Dependency for Route Handlers

### New file: `backend/src/rbac_mlflow/auth/dependencies.py`

```python
from fastapi import Depends, Request
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
```

Route handlers use `Depends(get_current_user)` to get the validated claims:

```python
@router.get("/auth/me")
async def me(user: TokenClaims = Depends(get_current_user)) -> dict:
    return {"sub": user.sub, "email": user.email, "groups": user.groups}
```

---

## 11. Backend: Auth Router

### New file: `backend/src/rbac_mlflow/auth/router.py`

```python
from fastapi import APIRouter, Depends

from rbac_mlflow.auth.dependencies import get_current_user
from rbac_mlflow.auth.providers.base import TokenClaims

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
async def me(
    user: TokenClaims = Depends(get_current_user),
) -> dict[str, object]:
    """Return the current user's resolved JWT claims.

    Useful for frontend debugging and verifying token contents.
    """
    return {
        "sub": user.sub,
        "email": user.email,
        "groups": user.groups,
    }
```

---

## 12. Backend: Update `main.py`

### File: `backend/src/rbac_mlflow/main.py` (replace entirely)

```python
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rbac_mlflow.auth.middleware import AuthMiddleware
from rbac_mlflow.auth.router import router as auth_router

app = FastAPI(title="rbac-mlflow API", version="0.1.0")

_frontend_origins = [
    f"https://{os.getenv('TRAEFIK_DOMAIN', 'rbac.local')}",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)

app.include_router(auth_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "rbac-mlflow-api"}
```

Changes from Phase 1:
- Import and register `AuthMiddleware`
- Import and include `auth_router`
- Everything else stays the same

Note: `CORSMiddleware` must be added **after** `AuthMiddleware` in the code
(Starlette processes middleware in reverse registration order, so CORS runs
first and auth runs second).

---

## 13. Frontend: Install Auth.js v5

```bash
cd frontend
pnpm add next-auth@5.0.0-beta.25
```

Auth.js v5 (beta) is the current version for Next.js App Router. It provides:
- Server-side OIDC flow (Authorization Code + PKCE)
- httpOnly cookie session with encrypted JWT
- Middleware for route protection
- `auth()` helper for server components

> Pin to a specific beta tag. Check https://www.npmjs.com/package/next-auth for
> the latest 5.x beta at implementation time.

---

## 14. Frontend: Auth.js Configuration

### New file: `frontend/src/auth.ts`

```typescript
import NextAuth from "next-auth";
import Keycloak from "next-auth/providers/keycloak";

declare module "next-auth" {
  interface Session {
    accessToken?: string;
    groups?: string[];
  }
}

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    Keycloak({
      clientId: process.env["KEYCLOAK_CLIENT_ID"] ?? "rbac-frontend",
      clientSecret: process.env["KEYCLOAK_CLIENT_SECRET"] ?? "",
      issuer: process.env["KEYCLOAK_ISSUER"] ?? "",
    }),
  ],
  callbacks: {
    async jwt({ token, account }) {
      // On initial sign-in, persist the access token
      if (account) {
        token["accessToken"] = account.access_token;
        token["groups"] = account.id_token
          ? (JSON.parse(
              Buffer.from(
                account.id_token.split(".")[1] ?? "",
                "base64"
              ).toString()
            ) as Record<string, unknown>)["groups"]
          : [];
      }
      return token;
    },
    async session({ session, token }) {
      session.accessToken = token["accessToken"] as string | undefined;
      session.groups = (token["groups"] as string[] | undefined) ?? [];
      return session;
    },
  },
});
```

This configuration:
- Uses the Keycloak OIDC provider built into Auth.js
- Extracts `groups` from the id_token on sign-in
- Persists the access token in the encrypted session cookie
- Exposes `accessToken` and `groups` on the session object

---

## 15. Frontend: Auth.js Route Handler

### New file: `frontend/src/app/api/auth/[...nextauth]/route.ts`

```typescript
import { handlers } from "@/auth";

export const { GET, POST } = handlers;
```

This mounts the Auth.js callback/signin/signout endpoints at `/api/auth/*`.

---

## 16. Frontend: Middleware (Route Protection)

### New file: `frontend/src/middleware.ts`

```typescript
export { auth as middleware } from "@/auth";

export const config = {
  matcher: [
    // Protect all routes except static files, images, and auth API
    "/((?!_next/static|_next/image|favicon.ico|api/auth).*)",
  ],
};
```

Auth.js middleware redirects unauthenticated users to the Keycloak login page.
The matcher excludes Next.js static assets and the auth callback routes.

---

## 17. Frontend: Auth Helper for API Calls

### New file: `frontend/src/lib/api.ts`

```typescript
import { auth } from "@/auth";

export async function apiFetch(
  path: string,
  init?: RequestInit
): Promise<Response> {
  const session = await auth();
  const headers = new Headers(init?.headers);

  if (session?.accessToken) {
    headers.set("Authorization", `Bearer ${session.accessToken}`);
  }

  const baseUrl = process.env["API_URL"] ?? "http://api:8000";
  return fetch(`${baseUrl}${path}`, { ...init, headers });
}
```

Server components and server actions use `apiFetch("/auth/me")` to call the
backend API with the user's access token attached. This replaces the Next.js
rewrite proxy for authenticated API calls (the rewrite in `next.config.ts` can
remain for unauthenticated endpoints like `/health`).

---

## 18. Frontend: Session Provider for Client Components

### New file: `frontend/src/app/providers.tsx`

```tsx
"use client";

import { SessionProvider } from "next-auth/react";
import type { ReactNode } from "react";

export function Providers({ children }: { children: ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}
```

### Update: `frontend/src/app/layout.tsx`

Wrap children in `<Providers>`:

```tsx
import type { Metadata } from "next";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "RBAC MLflow",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
```

---

## 19. Environment Variable Changes

### Update: `.env.example`

Add these new variables (keep all existing ones):

```bash
# ── Auth (updated for Phase 2) ──────────────────────────────────────────────
AUTH_PROVIDER=keycloak
JWT_ISSUER=http://keycloak:8080/realms/rbac-mlflow
JWT_AUDIENCE=rbac-frontend
JWKS_URI=http://keycloak:8080/realms/rbac-mlflow/protocol/openid-connect/certs

# ── Frontend Auth.js ─────────────────────────────────────────────────────────
NEXTAUTH_URL=https://rbac.local
NEXTAUTH_SECRET=generate-a-random-32-byte-secret-here
KEYCLOAK_CLIENT_ID=rbac-frontend
KEYCLOAK_CLIENT_SECRET=dev-secret-change-in-prod
KEYCLOAK_ISSUER=https://keycloak.rbac.local/realms/rbac-mlflow
```

Remove the old `JWKS_URL` variable (renamed to `JWKS_URI`).

Note the two different Keycloak URLs:
- `JWT_ISSUER` / `JWKS_URI` -- used by the **API container** (Docker-internal,
  no TLS, `http://keycloak:8080`)
- `KEYCLOAK_ISSUER` -- used by the **frontend container** via Auth.js, which
  redirects the **browser** (must be the external Traefik URL,
  `https://keycloak.rbac.local`)

---

## 20. Docker Compose Changes

### Update: `docker-compose.yml` -- `api` service

Add `JWKS_URI` to the environment block (replace `JWKS_URL`):

```yaml
api:
  build: ./backend
  env_file: .env
  environment:
    DATABASE_URL: ${DATABASE_URL}
    MLFLOW_TRACKING_URI: ${MLFLOW_TRACKING_URI}
    AUTH_PROVIDER: ${AUTH_PROVIDER}
    JWT_ISSUER: ${JWT_ISSUER}
    JWT_AUDIENCE: ${JWT_AUDIENCE}
    JWKS_URI: ${JWKS_URI}
  depends_on:
    postgres:
      condition: service_healthy
    keycloak:
      condition: service_started
```

Add `depends_on: keycloak` so the API waits for Keycloak to be available
(JWKS fetch at first request needs Keycloak running).

### Update: `docker-compose.yml` -- `frontend` service

Add Auth.js env vars:

```yaml
frontend:
  build: ./frontend
  environment:
    NEXT_PUBLIC_API_URL: https://api.${TRAEFIK_DOMAIN}
    API_URL: http://api:8000
    NEXTAUTH_URL: https://${TRAEFIK_DOMAIN}
    NEXTAUTH_SECRET: ${NEXTAUTH_SECRET}
    KEYCLOAK_CLIENT_ID: ${KEYCLOAK_CLIENT_ID}
    KEYCLOAK_CLIENT_SECRET: ${KEYCLOAK_CLIENT_SECRET}
    KEYCLOAK_ISSUER: https://keycloak.${TRAEFIK_DOMAIN}/realms/rbac-mlflow
    NODE_ENV: production
```

---

## 21. Backend File Tree After Phase 2

```
backend/src/rbac_mlflow/
  __init__.py           (exists, empty)
  main.py               (MODIFIED -- add middleware + auth router)
  config.py             (NEW)
  auth/
    __init__.py          (NEW, empty)
    middleware.py        (NEW)
    dependencies.py      (NEW)
    router.py            (NEW)
    jwks.py              (NEW)
    provider.py          (NEW)
    providers/
      __init__.py        (NEW, empty)
      base.py            (NEW)
      keycloak.py        (NEW)
      iam.py             (NEW)
```

Total: 8 new files + 1 modified file.

---

## 22. Frontend File Tree After Phase 2

```
frontend/src/
  auth.ts                        (NEW)
  middleware.ts                   (NEW)
  lib/
    api.ts                       (NEW)
  app/
    layout.tsx                   (MODIFIED -- add Providers wrapper)
    page.tsx                     (exists, unchanged)
    providers.tsx                (NEW)
    api/
      auth/
        [...nextauth]/
          route.ts               (NEW)
```

Total: 5 new files + 1 modified file.

---

## 23. Tests

### Test file: `backend/tests/test_auth_providers.py`

Tests both providers with a self-signed RSA key and fixture JWT.

```python
import time
from unittest.mock import AsyncMock, patch

import pytest
from jose import jwt as jose_jwt

from rbac_mlflow.auth.providers.base import TokenClaims
from rbac_mlflow.auth.providers.keycloak import KeycloakProvider

# Generate a test RSA key pair (done once at module level)
from jose.backends import RSAKey
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

_private_key = rsa.generate_private_key(
    public_exponent=65537, key_size=2048
)
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
    return jose_jwt.encode(
        payload, _private_pem, algorithm="RS256", headers={"kid": TEST_KID}
    )


@pytest.fixture
def mock_settings(monkeypatch):
    monkeypatch.setenv("JWT_ISSUER", TEST_ISSUER)
    monkeypatch.setenv("JWT_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setenv("JWKS_URI", "http://keycloak:8080/fake")


# Fake JWKS response matching our test key
_fake_jwk = {
    "kid": TEST_KID,
    "kty": "RSA",
    "alg": "RS256",
    "use": "sig",
    "n": "",  # filled dynamically
    "e": "AQAB",
}


def _get_jwks_response():
    """Build a JWKS response from the test public key."""
    from jose.backends import RSAKey as JoseRSAKey
    key = JoseRSAKey(_public_pem, "RS256")
    jwk_dict = key.to_dict()
    jwk_dict["kid"] = TEST_KID
    return {"keys": [jwk_dict]}


@pytest.mark.asyncio
async def test_keycloak_provider_valid_token(mock_settings):
    provider = KeycloakProvider()

    # Mock the JWKS fetch
    with patch.object(
        provider._cache,
        "_refresh",
        new_callable=AsyncMock,
    ) as mock_refresh:
        jwks = _get_jwks_response()
        provider._cache._keys = {
            k["kid"]: k for k in jwks["keys"]
        }
        provider._cache._fetched_at = time.monotonic()

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
async def test_keycloak_provider_expired_token(mock_settings):
    provider = KeycloakProvider()

    with patch.object(
        provider._cache, "_refresh", new_callable=AsyncMock
    ):
        jwks = _get_jwks_response()
        provider._cache._keys = {
            k["kid"]: k for k in jwks["keys"]
        }
        provider._cache._fetched_at = time.monotonic()

        token = _make_token(exp_offset=-60)  # expired 60s ago

        with pytest.raises(Exception, match="expired"):
            await provider.validate_token(token)


@pytest.mark.asyncio
async def test_keycloak_provider_wrong_audience(mock_settings):
    provider = KeycloakProvider()

    with patch.object(
        provider._cache, "_refresh", new_callable=AsyncMock
    ):
        jwks = _get_jwks_response()
        provider._cache._keys = {
            k["kid"]: k for k in jwks["keys"]
        }
        provider._cache._fetched_at = time.monotonic()

        # Create token with wrong audience
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
            payload, _private_pem, algorithm="RS256",
            headers={"kid": TEST_KID},
        )

        with pytest.raises(Exception, match="audience"):
            await provider.validate_token(token)
```

### Test file: `backend/tests/test_auth_middleware.py`

Tests the middleware returns 401 for missing/invalid tokens and passes through
for valid ones.

```python
import time
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from rbac_mlflow.main import app


@pytest.mark.asyncio
async def test_health_no_auth_required():
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_me_requires_token():
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/auth/me")
    assert resp.status_code == 401
    assert "Missing authentication token" in resp.text


@pytest.mark.asyncio
async def test_auth_me_invalid_token():
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
    assert resp.status_code == 401
```

### Test file: `backend/tests/test_auth_me.py`

End-to-end test that mocks the auth provider and verifies `/auth/me` returns
the correct claims.

```python
import pytest
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from rbac_mlflow.auth.providers.base import TokenClaims
from rbac_mlflow.main import app


@pytest.mark.asyncio
async def test_auth_me_with_valid_token():
    fake_claims = TokenClaims(
        sub="alice-id",
        email="alice@example.com",
        groups=["/team-alpha/readers"],
    )

    with patch(
        "rbac_mlflow.auth.middleware.get_auth_provider"
    ) as mock_get:
        mock_provider = AsyncMock()
        mock_provider.validate_token.return_value = fake_claims
        mock_get.return_value = mock_provider

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get(
                "/auth/me",
                headers={"Authorization": "Bearer fake-valid-token"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["sub"] == "alice-id"
    assert data["email"] == "alice@example.com"
    assert data["groups"] == ["/team-alpha/readers"]
```

---

## 24. Verification Checklist

Run these commands after implementing all changes:

```bash
# 1. Backend linting + types
cd backend
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# 2. Backend tests
uv run pytest -q

# 3. Frontend linting + types
cd ../frontend
pnpm typecheck
pnpm lint

# 4. Rebuild and start the stack
cd ..
docker compose down
docker volume rm rbac_mlflow_postgres_data  # fresh Keycloak import
docker compose up --build -d

# 5. Health check still works (no auth required)
curl -k https://api.rbac.local/health
# Expected: {"status":"ok","service":"rbac-mlflow-api"}

# 6. Auth endpoint rejects unauthenticated request
curl -k https://api.rbac.local/auth/me
# Expected: 401 {"detail":"Missing authentication token"}

# 7. Login via browser
# Visit https://rbac.local -- should redirect to Keycloak login
# Log in as alice / test1234
# After redirect, the session cookie is set
# Visit https://rbac.local/api/auth/session to verify session

# 8. Call /auth/me with a valid token
# Get the access token from the session, then:
# curl -k -H "Authorization: Bearer <token>" https://api.rbac.local/auth/me
# Expected: {"sub":"...","email":"alice@example.com","groups":["/team-alpha/readers"]}
```

---

## 25. Order of Implementation

Execute in this order to minimize broken intermediate states:

1. Update `keycloak/realm-export.json` (section 1)
2. Update `backend/pyproject.toml` + `uv lock` (section 2)
3. Create `backend/src/rbac_mlflow/config.py` (section 3)
4. Create all `auth/` package files (sections 4-11)
5. Update `backend/src/rbac_mlflow/main.py` (section 12)
6. Write and run backend tests (section 23)
7. Install `next-auth` in frontend (section 13)
8. Create all frontend auth files (sections 14-18)
9. Update `.env.example` (section 19)
10. Update `docker-compose.yml` (section 20)
11. Rebuild and run verification checklist (section 24)
