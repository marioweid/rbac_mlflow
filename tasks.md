# Tasks

Each phase delivers a runnable vertical slice. Phases build on each other; do
not start a phase until the previous one is complete and all tests pass.

---

## Phase 1 – Infrastructure & Project Skeleton

Goal: everything runs locally via `docker compose up`.

- [ ] Initialize git repository with `.gitignore` (Python, Node, `.env`)
- [ ] Create `docker-compose.yml` with all services:
      postgres, minio, mlflow, traefik, keycloak, api (stub), frontend (stub)
      - Postgres must serve two separate databases: `rbac` (app) and `mlflow`
        (MLflow backend store) — create both via an init SQL script mounted at
        `/docker-entrypoint-initdb.d/`
- [ ] Configure Traefik with self-signed TLS for local dev
- [ ] Write a minimal `mlflow/Dockerfile` that installs extra deps:
      ```dockerfile
      FROM ghcr.io/mlflow/mlflow:latest
      RUN pip install --no-cache-dir psycopg2-binary boto3
      ```
      Use this image in docker-compose instead of the upstream image directly
- [ ] Configure MLflow to use postgres as backend store and MinIO as artifact store
- [ ] Configure Keycloak realm manually:
      - realm `mlflow-rbac`
      - client `api` (bearer-only / resource server — validates tokens, does not
        request them; no login flow, no redirect URIs needed)
      - client `frontend` (public, OIDC, Authorization Code + PKCE)
      - groups: `rag-service-owner`, `rag-service-engineer`, `rag-service-reader`
      - test users assigned to each group
      - add a **Group Membership protocol mapper** to the `frontend` client scope:
        Client → Client scopes → dedicated scope → Add mapper → Group Membership,
        token claim name: `groups`, full group path: off
- [ ] Export the configured realm to `keycloak/realm-export.json`:
      - use Keycloak Admin UI: Realm settings → Action → Partial export
        (include groups, roles, clients; exclude users and credentials)
      - commit `realm-export.json` to the repository
- [ ] Mount the export in docker-compose so Keycloak imports it on first boot:
      ```yaml
      keycloak:
        command: start-dev --import-realm
        volumes:
          - ./keycloak/realm-export.json:/opt/keycloak/data/import/realm-export.json
      ```
- [ ] Add test users to a separate `keycloak/test-users.json` or document
      them in `CONTRIBUTING.md` (do not commit passwords to the repo)
- [ ] Create FastAPI project skeleton (`uv`, `ruff`, `ty`, `pytest`)
- [ ] Create Next.js project skeleton (App Router, TypeScript strict)
- [ ] Verify: `docker compose up` starts all services without errors
- [ ] Verify: MLflow UI accessible internally, frontend returns 200

---

## Phase 2 – Authentication

Goal: users can log in via Keycloak and the API validates their JWT.

- [ ] Implement OIDC login flow in Next.js (Authorization Code + PKCE)
      using `next-auth` or a minimal custom implementation
- [ ] Store JWT in httpOnly cookie on the frontend
- [ ] Implement `AuthProvider` protocol in API (`auth/providers/base.py`)
- [ ] Implement `KeycloakProvider`: fetch JWKS, validate JWT signature and
      expiry, extract `groups` claim
- [ ] Implement `CustomIAMProvider`: same interface, different JWKS URL/issuer,
      configured via env vars
- [ ] Add auth middleware to FastAPI: validate token on every request, attach
      `TokenClaims` to request state
- [ ] Add `GET /auth/me` endpoint returning resolved claims (for frontend debug)
- [ ] Write unit tests for both auth providers with fixture JWTs
- [ ] Verify: login → JWT → `GET /auth/me` returns correct groups

---

## Phase 3 – RBAC Engine

Goal: permission checks work end-to-end; admins can configure team mappings.

- [ ] Create DB migration: `teams`, `group_role_mappings`, `team_experiments`,
      `audit_events` tables (use Alembic)
- [ ] Implement `resolve_teams(groups: list[str]) -> list[TeamRole]` in
      `rbac/service.py` — queries `group_role_mappings`
- [ ] Implement `require_permission(user, permission, team_id)` — raises 403 if
      not satisfied
- [ ] Create admin endpoints (owner-only):
      - `POST /admin/teams` — create team
      - `POST /admin/teams/{id}/mappings` — add group → role mapping
      - `DELETE /admin/teams/{id}/mappings/{mapping_id}`
      - `POST /admin/teams/{id}/experiments` — link MLflow experiment to team
      - `DELETE /admin/teams/{id}/experiments/{experiment_id}`
- [ ] Seed docker-compose with fixture group mappings matching Keycloak test groups
- [ ] Add bootstrap admin seed: an Alembic seed migration (or startup script)
      that reads `BOOTSTRAP_ADMIN_GROUP` env var and inserts a group → role
      mapping with `owner` for a default team — runs only if `group_role_mappings`
      is empty, so it is safe to leave enabled in dev and harmless after first setup

---

## Phase 4 – Experiment & Run Views

Goal: readers can see their team's experiments and runs via the frontend.

**API:**
- [ ] `GET /experiments` — list experiments linked to user's teams (from
      `team_experiments`, metadata from MLflow)
- [ ] `GET /experiments/{id}` — experiment detail, requires `experiment.read`
- [ ] `GET /experiments/{id}/runs` — run list, requires `run.read`
- [ ] `GET /experiments/{id}/runs/{run_id}` — run detail with metrics,
      params, tags, artifacts, and judge scores; requires `run.read`
- [ ] Filter all MLflow API responses to exclude data not belonging to the
      user's teams

**Frontend:**
- [ ] `/dashboard` page: experiment cards with latest run status and key metric
- [ ] `/experiments/[id]` page: run list table (sortable by metric)
- [ ] `/experiments/[id]/runs/[runId]` page: metric charts, params table,
      judge scores table, artifact links
- [ ] Unauthenticated users redirected to `/login`
- [ ] Users with no team membership see an empty state (not an error)

**Tests:**
- [ ] API integration tests: reader sees only their team's experiments
- [ ] API integration tests: reader cannot see other teams' experiments (403)

---

## Phase 5 – Dataset Management

Goal: engineers and owners can view and edit evaluation datasets.

**API:**
- [ ] `GET /datasets` — list datasets linked to user's teams (from MLflow
      dataset registry), requires `dataset.read`
- [ ] `GET /datasets/{id}` — fetch dataset metadata + download file from
      artifact store, return parsed rows, requires `dataset.read`
- [ ] `POST /datasets` — create new dataset: accept JSONL upload, write to
      artifact store, register in MLflow, requires `dataset.write`
- [ ] `PUT /datasets/{id}` — create new version: accept updated rows, write
      new file, register new MLflow dataset entry, requires `dataset.write`
- [ ] `DELETE /datasets/{id}` — soft-delete (mark inactive in app DB),
      requires `dataset.write`
- [ ] Audit log entry written for every write operation

**Frontend:**
- [ ] `/datasets` page: dataset list with name, version, row count, last
      modified
- [ ] `/datasets/[id]` page: table view of rows (question, expected answer,
      context columns); edit button visible to engineer/owner only
- [ ] Inline row editing (add row, edit row, delete row)
- [ ] Save creates a new version (shown in version history panel)
- [ ] `/datasets/new` page: upload JSONL or create rows manually

**Tests:**
- [ ] Reader can view datasets but cannot call write endpoints (403)
- [ ] Engineer can create and update datasets
- [ ] New version is registered in MLflow after PUT

---

## Phase 6 – Trigger Evaluation Runs

Goal: engineers can start an evaluation run from the UI against a selected
dataset.

- [ ] `POST /experiments/{id}/runs` — start an evaluation run; body includes
      `dataset_id`; requires `run.start`
- [ ] API calls MLflow to create the run, links dataset as input, returns
      `run_id`
- [ ] Frontend: "Run evaluation" button on experiment detail page (visible to
      engineer/owner only)
- [ ] Modal to select dataset version before confirming
- [ ] After submission, redirect to the new run detail page
- [ ] Audit log entry written for run start
- [ ] Tests: reader cannot start runs (403); engineer can start runs

---

## Phase 7 – Polish & Production Readiness

Goal: safe to deploy; observable; easy to hand off.

- [ ] Replace self-signed TLS with Let's Encrypt in Traefik config (prod
      compose override)
- [ ] Add `docker-compose.override.prod.yml` that removes Keycloak and MinIO,
      points to real IAM and S3 via env vars
- [ ] Add structured JSON logging to API (Python `logging` + `python-json-logger`)
- [ ] Add `GET /healthz` (liveness) and `GET /readyz` (readiness) endpoints
- [ ] Verify Traefik health checks route to readiness endpoint
- [ ] Add `CONTRIBUTING.md` with local setup steps (one command: `docker
      compose up`)
- [ ] End-to-end test: login as reader → view experiment → view run (Playwright
      or pytest + httpx)
- [ ] End-to-end test: login as engineer → edit dataset → verify new version
      in MLflow
- [ ] Run `pip-audit` on Python deps; fix or document any findings
- [ ] Run `pnpm audit` on frontend deps; fix or document any findings
