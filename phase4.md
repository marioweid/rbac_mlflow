# Phase 4: Experiment & Run Read Views

Readers can see their team's experiments and runs via the frontend.

## What was built

### Backend: MLflow proxy with RBAC filtering

- **MLflow HTTP client** (`mlflow_client.py`): reusable `httpx.AsyncClient` managed in FastAPI lifespan, with helper functions for `get_experiment`, `search_runs`, `get_run`
- **`require_experiment_permission()`**: new dependency factory that resolves `experiment_id` -> `team_id` via `team_experiments` table, then checks RBAC permission. Returns the resolved `team_id`.
- **4 GET endpoints** on `/experiments` router:

| Method | Path | Permission | Response |
|--------|------|-----------|----------|
| GET | `/experiments` | scoped by team_roles | `list[ExperimentSummary]` |
| GET | `/experiments/{id}` | experiment.read | `ExperimentDetail` |
| GET | `/experiments/{id}/runs` | run.read | `RunListResponse` |
| GET | `/experiments/{id}/runs/{run_id}` | run.read | `RunDetail` |

- **Service layer** with `asyncio.gather` for parallel MLflow calls on the dashboard
- Run detail verifies `experiment_id` matches to prevent cross-experiment URL manipulation

### Frontend: 3 pages with Tailwind CSS

- **`/dashboard`**: experiment cards grid with team badge, latest run status, key metric
- **`/experiments/[id]`**: experiment header + runs table with server-side sorting
- **`/experiments/[id]/runs/[runId]`**: full run detail (metrics, params, tags, judge scores, artifact URI)
- **Root `/` redirects to `/dashboard`**
- Empty state for users with no team membership (not an error)
- Tailwind CSS v4 set up via PostCSS plugin

## New files

### Backend (6 files)

- `backend/src/rbac_mlflow/mlflow_client.py` — MLflow HTTP client + dependency
- `backend/src/rbac_mlflow/experiments/__init__.py`
- `backend/src/rbac_mlflow/experiments/schemas.py` — ExperimentSummary, ExperimentDetail, RunSummary, RunDetail, etc.
- `backend/src/rbac_mlflow/experiments/service.py` — business logic combining DB + MLflow
- `backend/src/rbac_mlflow/experiments/router.py` — 4 GET endpoints
- `backend/tests/test_mlflow_client.py` — 6 unit tests for MLflow client helpers
- `backend/tests/test_experiment_permission.py` — 4 tests for require_experiment_permission
- `backend/tests/test_experiments.py` — 8 integration tests for endpoints

### Frontend (7 files)

- `frontend/postcss.config.mjs` — Tailwind PostCSS plugin
- `frontend/src/app/globals.css` — Tailwind import
- `frontend/src/lib/types.ts` — TypeScript interfaces
- `frontend/src/lib/format.ts` — timestamp/duration/status formatting
- `frontend/src/app/dashboard/page.tsx` — experiment cards
- `frontend/src/app/experiments/[id]/page.tsx` — run list table
- `frontend/src/app/experiments/[id]/runs/[runId]/page.tsx` — run detail

## Modified files

- `backend/src/rbac_mlflow/main.py` — httpx client in lifespan, experiments router
- `backend/src/rbac_mlflow/rbac/dependencies.py` — added `require_experiment_permission`
- `frontend/src/app/layout.tsx` — imports globals.css
- `frontend/src/app/page.tsx` — redirects to /dashboard
- `frontend/package.json` — added tailwindcss, @tailwindcss/postcss, postcss

## Tests

53 tests passing (19 new):

- `test_mlflow_client.py` — get_experiment, search_runs, get_run (success, 404, 502)
- `test_experiment_permission.py` — allows, denies, 404 for unlinked, wrong team
- `test_experiments.py` — list (own team, empty), detail (ok, 404, 403), runs list, run detail (ok, wrong experiment)

## Verification

```bash
# Backend
cd backend
uv run pytest -q           # 53 passed
uv run ruff check src/ tests/  # All checks passed

# Frontend
cd frontend
pnpm typecheck             # 0 errors
pnpm lint                  # 0 warnings, 0 errors
```
