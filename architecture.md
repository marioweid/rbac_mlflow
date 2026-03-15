# Architecture

## Overview

A thin RBAC proxy layer in front of MLflow. The frontend never talks to MLflow
directly — all requests go through the API, which validates the JWT, checks
permissions, and forwards allowed operations to MLflow or the artifact store.

```
Browser
  └─► Traefik (reverse proxy / TLS)
        ├─► Frontend (Next.js)          :3000
        ├─► API (FastAPI)               :8000
        ├─► MLflow Tracking Server      :5000  (internal only)
        └─► Keycloak (local auth)       :8080  (local only)

API
  ├─► PostgreSQL  (app DB: RBAC, group mappings)
  ├─► MLflow      (experiments, runs, metrics, traces)
  └─► MinIO / S3  (dataset files)

MLflow
  └─► PostgreSQL  (MLflow backend store)
  └─► MinIO / S3  (artifact store)
```

---

## Services (docker-compose)

| Service | Image | Purpose |
|---|---|---|
| `traefik` | traefik:v3 | Reverse proxy, TLS termination, routing |
| `frontend` | custom | Next.js UI |
| `api` | custom | FastAPI backend, RBAC enforcement |
| `mlflow` | custom (ghcr.io/mlflow/mlflow + psycopg2-binary + boto3) | MLflow tracking server |
| `keycloak` | quay.io/keycloak/keycloak | OIDC provider (local dev only) |
| `postgres` | postgres:16 | Shared DB (app schema + MLflow backend) |
| `minio` | minio/minio | S3-compatible artifact store (local dev) |

In production, Keycloak and MinIO are replaced by the company IAM and S3.
Everything else remains identical.

---

## Authentication Flow

```
1. User visits frontend → no session → redirect to Keycloak/IAM login
2. Keycloak/IAM performs OAuth2 Authorization Code flow
3. JWT (access token) returned to frontend
4. Frontend stores JWT in memory (not localStorage, not cookie)
5. Every API request includes the JWT as: Authorization: Bearer <token>
6. Silent token refresh runs in the background before expiry
7. API middleware:
   a. Validates JWT signature and expiry
   b. Extracts `groups` claim
   c. Resolves groups → (team_id, role) from DB
   d. Attaches resolved context to request
8. Route handler calls permission check before executing operation
```

### Auth Provider Abstraction

The auth provider is an interface with two implementations, selected by
`AUTH_PROVIDER` env var:

```
AuthProvider (Protocol)
  ├── KeycloakProvider   (AUTH_PROVIDER=keycloak)
  └── CustomIAMProvider  (AUTH_PROVIDER=iam)

Both expose:
  - validate_token(token) → TokenClaims
  - get_jwks_url() → str
```

JWKS URL and issuer are configured per provider via environment variables. No
code changes needed to switch environments.

---

## RBAC Enforcement Flow

```
Request → JWT middleware (validate + extract groups)
        → resolve_teams(groups) → [(team_id, role), ...]
        → route handler calls require_permission(user, action, resource_team_id)
        → if role for that team satisfies permission → proceed
        → else → 403 Forbidden
```

Permission evaluation is additive: a user with `owner` in team A and `reader`
in team B has full access to team A's resources and read-only access to team
B's.

---

## Database Schema

All RBAC state lives in the app's PostgreSQL schema (separate from MLflow's
schema, but same Postgres instance is fine for local dev).

### Key tables

```sql
-- A team maps to one or more MLflow experiments
teams (
  id          UUID PRIMARY KEY,
  name        TEXT UNIQUE NOT NULL,
  created_at  TIMESTAMPTZ
)

-- Map Keycloak/IAM group names to (team, role)
group_role_mappings (
  id          UUID PRIMARY KEY,
  group_name  TEXT NOT NULL,          -- e.g. "rag-service-owner"
  team_id     UUID REFERENCES teams,
  role        TEXT NOT NULL,          -- reader | engineer | owner
  UNIQUE (group_name, team_id)
)

-- Which MLflow experiments belong to which team
team_experiments (
  team_id             UUID REFERENCES teams,
  mlflow_experiment_id TEXT NOT NULL,
  PRIMARY KEY (team_id, mlflow_experiment_id)
)

-- Audit log for sensitive operations
audit_events (
  id          UUID PRIMARY KEY,
  user_sub    TEXT NOT NULL,          -- JWT `sub` claim
  team_id     UUID REFERENCES teams,
  action      TEXT NOT NULL,
  resource    TEXT,
  created_at  TIMESTAMPTZ
)
```

No user table is needed. Users are identified by their JWT `sub` claim; group
membership is resolved at request time from the `groups` claim.

---

## API Module Structure

```
api/
  main.py                 # FastAPI app, middleware registration
  config.py               # Settings (pydantic-settings)
  auth/
    middleware.py          # JWT validation, group resolution
    providers/
      base.py              # AuthProvider Protocol
      keycloak.py
      iam.py
  rbac/
    models.py              # SQLModel: Team, GroupRoleMapping, TeamExperiment
    service.py             # resolve_teams(), require_permission()
  experiments/
    router.py              # GET /experiments, GET /experiments/{id}
    service.py             # proxy to MLflow, filter by team
  runs/
    router.py              # GET /runs, POST /runs (start eval run)
    service.py
  datasets/
    router.py              # GET/POST/PUT/DELETE /datasets
    service.py             # read/write files via MinIO/S3
  admin/
    router.py              # team and group mapping management (owner only)
    service.py
```

---

## Frontend Page Structure

```
/                        → redirect to /dashboard
/login                   → OIDC redirect
/dashboard               → experiment list (scoped to user's teams)
/experiments/[id]        → experiment detail: run list, metric overview
/experiments/[id]/runs/[runId]
                         → run detail: metrics, artifacts, traces, judge scores
/datasets                → dataset list (all teams user has access to)
/datasets/[id]           → dataset viewer + editor (engineer/owner only)
/datasets/new            → create dataset (engineer/owner only)
/admin/teams             → team list, group mappings (owner only)
/admin/teams/[id]        → edit group → role mappings for a team
```

---

## Traefik Routing (local)

```
traefik.yml rules:
  frontend.*  → http://frontend:3000
  api.*        → http://api:8000
  mlflow.*     → http://mlflow:5000   (internal network only, no public rule)
  keycloak.*   → http://keycloak:8080
```

MLflow itself is not exposed publicly. All data access goes through the API.

---

## Environment Configuration

```
# Auth
AUTH_PROVIDER=keycloak           # or: iam
KEYCLOAK_URL=http://keycloak:8080
KEYCLOAK_REALM=mlflow-rbac
KEYCLOAK_CLIENT_ID=api
IAM_JWKS_URL=https://iam.company.com/.well-known/jwks.json
IAM_ISSUER=https://iam.company.com

# Database
# Two separate databases on the same Postgres instance
DATABASE_URL=postgresql://user:pass@postgres:5432/rbac
MLFLOW_BACKEND_STORE_URI=postgresql://user:pass@postgres:5432/mlflow

# MLflow
MLFLOW_TRACKING_URI=http://mlflow:5000

# Artifact store
S3_ENDPOINT_URL=http://minio:9000  # omit for AWS S3 in prod
S3_BUCKET=mlflow-artifacts
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```
