# Phase 3: RBAC Engine

Permission checks work end-to-end; admins can configure team mappings.

## What was built

### Database layer
- SQLAlchemy 2.x async ORM with `asyncpg` driver
- Alembic migrations (async runner via `asyncio.run()` + `connection.run_sync()`)
- Migration 001: creates `teams`, `group_role_mappings`, `team_experiments`, `audit_events`
- `get_db()` FastAPI dependency yields `AsyncSession`

### RBAC engine
- **Role hierarchy**: reader < engineer < owner (pre-expanded `ROLE_PERMISSIONS` dict)
- **`resolve_teams(db, groups)`**: maps JWT `groups` claim to `list[TeamRole]` via single JOIN query
- **`check_permission(team_roles, permission, team_id)`**: pure function, no DB access
- **`require_permission(permission)`**: FastAPI dependency factory, reads `team_id` from path, raises 403

### Permission matrix

| Permission | reader | engineer | owner |
|---|---|---|---|
| experiment.read | yes | yes | yes |
| run.read | yes | yes | yes |
| run.start | - | yes | yes |
| dataset.read | yes | yes | yes |
| dataset.write | - | yes | yes |
| team.manage | - | - | yes |

### Admin endpoints (owner-only)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/admin/teams` | Create team (requires owner on any team) |
| POST | `/admin/teams/{team_id}/mappings` | Add group->role mapping |
| DELETE | `/admin/teams/{team_id}/mappings/{mapping_id}` | Remove mapping |
| POST | `/admin/teams/{team_id}/experiments` | Link MLflow experiment |
| DELETE | `/admin/teams/{team_id}/experiments/{experiment_id}` | Unlink experiment |

### Bootstrap
- Runs on startup via FastAPI `lifespan`
- If `group_role_mappings` is empty, creates `team-alpha` with 3 Keycloak group mappings:
  - `/team-alpha/owners` -> owner
  - `/team-alpha/engineers` -> engineer
  - `/team-alpha/readers` -> reader
- Controlled by `BOOTSTRAP_ADMIN_GROUP` and `BOOTSTRAP_TEAM_NAME` env vars

## New files

```
backend/
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/001_create_rbac_tables.py
└── src/rbac_mlflow/
    ├── db.py
    ├── models.py
    ├── bootstrap.py
    ├── rbac/
    │   ├── __init__.py
    │   ├── constants.py
    │   ├── schemas.py
    │   ├── service.py
    │   └── dependencies.py
    └── admin/
        ├── __init__.py
        └── router.py
```

## Modified files

- `backend/pyproject.toml` — added sqlalchemy, asyncpg, alembic; added B008 to ruff ignore
- `backend/src/rbac_mlflow/config.py` — added `bootstrap_admin_group`, `bootstrap_team_name`
- `backend/src/rbac_mlflow/main.py` — added lifespan handler, included admin router
- `backend/Dockerfile` — copies alembic files, runs `alembic upgrade head` before uvicorn
- `.env.example` — added `BOOTSTRAP_ADMIN_GROUP`, `BOOTSTRAP_TEAM_NAME`

## Tests

34 tests passing:
- `test_rbac_service.py` — 13 tests for `check_permission` (all role/permission combos) + `resolve_teams`
- `test_rbac_dependencies.py` — 3 tests for `require_permission` dependency (allow, deny, wrong team)
- `test_admin_router.py` — 10 tests for all 5 endpoints (auth, 403, 404, 409 cases)
- Existing auth/health tests unchanged (8 tests)

## Verification

```bash
cd backend
uv run pytest -q            # 34 passed
uv run ruff check src/ tests/  # All checks passed
```

Docker:
```bash
docker compose up -d
# Wait for healthy, then:
# 1. Login as carol -> GET /auth/me -> groups include /team-alpha/owners
# 2. Verify bootstrap seeded team-alpha + 3 mappings
# 3. POST /admin/teams as carol -> 201
# 4. POST /admin/teams as alice -> 403
```
