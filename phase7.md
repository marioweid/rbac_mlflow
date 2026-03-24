# Phase 7 — Trigger Evaluation Runs

## Goal

Engineers and owners can start an evaluation run from the UI by selecting a
dataset version. The run is created in MLflow, linked to the dataset, and
immediately visible on the experiment detail page. Readers cannot start runs.

---

## Current state

**Already exists:**
- `Permission.RUN_START` in the role-permission matrix (engineer + owner)
- `GET /experiments/{id}/runs` and `GET /experiments/{id}/runs/{run_id}` endpoints
- MLflow client helpers: `get_experiment`, `search_runs`, `get_run` in `mlflow_client.py`
- `require_experiment_permission(Permission)` RBAC dependency
- `log_audit_event` for audit logging
- Dataset model with `datasets` and `dataset_versions` tables
- S3 client (`s3_client.py`) with `download_jsonl`
- Frontend experiment detail page with runs table
- `clientApiFetch` helper for client-side API calls with JWT

**Does not exist:**
- No `POST /experiments/{id}/runs` endpoint
- No MLflow client helper for creating runs or logging metrics/params
- No "Run evaluation" button or dataset-selection modal on the frontend
- No run-start Pydantic schemas

---

## Backend tasks

### 1. New MLflow client helpers

**File:** `backend/src/rbac_mlflow/mlflow_client.py`

Add functions for the MLflow REST API calls needed to create and manage a run:

| Function | MLflow endpoint | Purpose |
|----------|----------------|---------|
| `create_run(client, experiment_id, run_name, tags)` | `POST /api/2.0/mlflow/runs/create` | Create a new run in RUNNING state |
| `log_batch(client, run_id, metrics, params, tags)` | `POST /api/2.0/mlflow/runs/log-batch` | Log metrics, params, and tags in one call |
| `update_run(client, run_id, status, end_time)` | `POST /api/2.0/mlflow/runs/update` | Set run status to FINISHED or FAILED |

All functions follow the existing error-handling pattern (catch `httpx.HTTPError`,
raise `HTTPException(502)` on failure).

### 2. Pydantic schemas for run creation

**File:** `backend/src/rbac_mlflow/experiments/schemas.py`

Add:

```python
class StartRunRequest(BaseModel):
    """Body for POST /experiments/{id}/runs."""
    dataset_id: uuid.UUID
    dataset_version: int | None = None  # None = latest version
    run_name: str | None = None         # auto-generated if omitted

class StartRunResponse(BaseModel):
    """Response for POST /experiments/{id}/runs."""
    run_id: str
    experiment_id: str
    run_name: str
    status: str
```

### 3. Evaluation service

**New file:** `backend/src/rbac_mlflow/experiments/evaluation.py`

Single function that orchestrates the evaluation:

```python
async def run_evaluation(
    mlflow: httpx.AsyncClient,
    s3: S3Client,
    db: AsyncSession,
    experiment_id: str,
    dataset_id: uuid.UUID,
    dataset_version: int | None,
    run_name: str,
    user_sub: str,
) -> StartRunResponse:
```

Steps:
1. Load dataset version from DB. If `dataset_version` is None, use the latest.
   Raise 404 if dataset or version not found.
2. Download JSONL rows from S3 using the version's `s3_key`.
3. Create an MLflow run via `create_run()` with tags:
   - `mlflow.runName`: the run name
   - `dataset_id`: str(dataset_id)
   - `dataset_version`: str(version)
   - `dataset_name`: dataset name from DB
   - `started_by`: user_sub
4. Run deterministic scorers against each row (same approach as the seed script):
   - For phase 7, the "model" returns the expected answer (identity function).
   - Scorers: `exact_match`, `is_non_empty` (reuse from seed script logic).
   - A future phase can plug in a real model endpoint.
5. Log aggregate metrics (`exact_match/mean`, `is_non_empty/mean`, `row_count`)
   and params (`dataset_name`, `dataset_version`, `scorer`) via `log_batch()`.
6. Update run status to `FINISHED` via `update_run()`. On any error during
   scoring, update to `FAILED` instead.
7. Return `StartRunResponse`.

**Why synchronous in-process?** Datasets are small (< 10K rows) and scorers are
deterministic Python functions. The entire evaluation completes in < 1 second.
No background worker needed for phase 7. If a real LLM scorer is added later,
this function becomes the entrypoint for a background task (Celery, ARQ, etc.).

### 4. Router endpoint

**File:** `backend/src/rbac_mlflow/experiments/router.py`

Add:

```python
@router.post("/{experiment_id}/runs", response_model=StartRunResponse, status_code=201)
async def start_run(
    experiment_id: str,
    body: StartRunRequest,
    team_id: uuid.UUID = Depends(require_experiment_permission(Permission.RUN_START)),
    db: AsyncSession = Depends(get_db),
    mlflow: httpx.AsyncClient = Depends(get_mlflow_client),
    s3: S3Client = Depends(get_s3_client),
    token_claims: TokenClaims = Depends(get_token_claims),
) -> StartRunResponse:
```

After `run_evaluation` returns, call `log_audit_event(db, user_sub, team_id,
"run.start", f"experiment={experiment_id} run={result.run_id}")`.

Auto-generate `run_name` if not provided: `eval-{dataset_name}-v{version}-{timestamp}`.

### 5. Validate dataset belongs to same team

Before starting the run, verify the dataset's `team_id` matches the
experiment's `team_id`. Raise 403 if they differ — a user cannot use another
team's dataset. This check lives in `run_evaluation`.

---

## Frontend tasks

### 6. TypeScript types

**File:** `frontend/src/lib/types.ts`

Add:

```typescript
export interface StartRunRequest {
  dataset_id: string;
  dataset_version: number | null;
  run_name: string | null;
}

export interface StartRunResponse {
  run_id: string;
  experiment_id: string;
  run_name: string;
  status: string;
}
```

### 7. "Run evaluation" button on experiment detail page

**File:** `frontend/src/app/experiments/[id]/page.tsx`

Add a "Run evaluation" button above the runs table. The button is only visible
if the user's role is `engineer` or `owner` for this experiment's team.

Clicking the button opens a modal (task 8). The button is disabled while a
submission is in flight.

To determine role: the experiment detail page already has `team_name`. Pass
user roles from the session/auth context. If the user has `run.start`
permission for the team, show the button.

### 8. Dataset selection modal

**New file:** `frontend/src/app/experiments/[id]/run-evaluation-modal.tsx`

Client component (`"use client"`). Opens as a dialog/modal.

Contents:
- **Dataset dropdown:** fetches `GET /datasets` filtered to the experiment's
  team. Shows dataset name + latest version + row count.
- **Version selector:** once a dataset is selected, shows available versions
  (fetched from `GET /datasets/{id}` detail). Defaults to latest.
- **Run name (optional):** text input, placeholder shows the auto-generated
  name pattern.
- **Start button:** POSTs to `/experiments/{id}/runs` via `clientApiFetch`.
- **Loading state:** spinner + disabled inputs while request is in flight.
- **Error state:** display error message inline if the request fails.
- **On success:** close modal and redirect to `/experiments/{id}/runs/{run_id}`.

### 9. Navigation after run creation

After a successful `POST`, use Next.js `router.push()` to navigate to the new
run's detail page. The existing run detail page
(`/experiments/[id]/runs/[runId]/page.tsx`) already renders metrics, params,
and tags — no changes needed there.

---

## Tests

### 10. Unit tests — MLflow client helpers

**File:** `backend/tests/test_mlflow_client.py` (new or extend existing)

- `test_create_run_returns_run_id` — mock httpx response, verify payload
- `test_create_run_raises_on_mlflow_error` — mock 500, verify HTTPException(502)
- `test_log_batch_sends_correct_payload` — verify metrics/params structure
- `test_update_run_sets_status` — verify FINISHED/FAILED status sent

### 11. Unit tests — evaluation service

**File:** `backend/tests/test_evaluation.py`

- `test_run_evaluation_creates_run_and_logs_metrics` — mock MLflow + S3 + DB,
  verify create_run called, log_batch called with expected metrics, update_run
  called with FINISHED
- `test_run_evaluation_uses_latest_version_when_none` — omit version, verify
  latest version selected from DB
- `test_run_evaluation_fails_if_dataset_not_found` — non-existent dataset_id → 404
- `test_run_evaluation_fails_if_team_mismatch` — dataset belongs to different
  team → 403
- `test_run_evaluation_marks_failed_on_error` — mock scorer exception, verify
  update_run called with FAILED

### 12. Unit tests — router / RBAC

**File:** `backend/tests/test_run_start.py`

Follow the existing test pattern (mock auth, DB, MLflow, S3):

- `test_reader_cannot_start_run` — alice (reader) POSTs → 403
- `test_engineer_can_start_run` — bob (engineer) POSTs → 201
- `test_owner_can_start_run` — carol (owner) POSTs → 201
- `test_start_run_returns_run_id_and_name` — verify response shape
- `test_start_run_logs_audit_event` — verify audit entry written
- `test_start_run_with_explicit_name` — verify custom run name used
- `test_start_run_with_nonexistent_dataset` — 404

---

## Task dependency order

```
 1. MLflow client helpers (create_run, log_batch, update_run)     ← independent
 2. Pydantic schemas (StartRunRequest, StartRunResponse)          ← independent
 3. Evaluation service (experiments/evaluation.py)                ← needs 1, 2
 4. Router endpoint (POST /experiments/{id}/runs)                 ← needs 2, 3
 5. TypeScript types                                              ← independent
 6. Run evaluation modal (client component)                       ← needs 5
 7. "Run evaluation" button on experiment page                    ← needs 6
 8. Tests — MLflow client helpers                                 ← needs 1
 9. Tests — evaluation service                                    ← needs 3
10. Tests — router / RBAC                                         ← needs 4
```

Parallelization:
- Steps 1, 2, 5 have no mutual dependencies → all in parallel
- Step 3 after 1 + 2
- Step 4 after 2 + 3
- Frontend steps 6-7 can start as soon as types are done (step 5)
- Tests 8-10 after their respective backend code

---

## Key decisions

**Synchronous evaluation (no background worker):** Datasets are small and
scorers are deterministic. The API request blocks for < 1 second. Adding a task
queue adds operational complexity (Redis, worker process, result polling). Not
justified until real LLM scorers are introduced. The evaluation function is
structured so it can be wrapped in a background task later without changing the
interface.

**Identity model (returns expected answer):** Same approach as the seed script.
The "model under test" returns `expectations.expected_response`, making
`exact_match/mean = 1.0` by design. This validates the full pipeline without
requiring API keys or external services. A future phase adds a
`--model-endpoint` flag or config setting.

**Dataset-team validation:** A user with `run.start` on team-alpha should not
be able to run an evaluation using team-beta's dataset. The check compares the
dataset's `team_id` against the experiment's `team_id` (resolved by
`require_experiment_permission`).

**Run naming:** Auto-generated names follow the pattern
`eval-{dataset_name}-v{version}-{YYYYMMDD-HHmmss}` for traceability. Users can
override with a custom name.

**No polling for run status:** Since evaluation is synchronous, the run is
already `FINISHED` (or `FAILED`) when the endpoint returns. The frontend
redirects directly to the run detail page. If async evaluation is added later,
the frontend will need a polling mechanism or WebSocket — out of scope for
phase 7.
