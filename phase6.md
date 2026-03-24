# Phase 6 — Dataset Management

## Goal

Engineers and owners can view and edit evaluation datasets through the UI.
Readers can view datasets but cannot modify them. Each edit creates a new
immutable version. Files live in MinIO/S3; metadata lives in the RBAC database.

---

## Current state

**Already exists:**
- `Permission.DATASET_READ` and `Permission.DATASET_WRITE` in the role-permission matrix
- S3/MinIO infrastructure (minio service, env vars, boto3 in mlflow image)
- Audit logging (`log_audit_event` in `rbac/service.py`)
- RBAC dependency factories (`require_permission`, `require_experiment_permission`)
- Frontend `apiFetch` helper with JWT auth
- Alembic migration framework (one migration so far: `001_create_rbac_tables`)
- Golden sample fixture at `tests/fixtures/golden_sample.jsonl` (already in S3)

**Does not exist:**
- No `datasets/` module in the backend
- No dataset tables in the DB
- No S3 client abstraction in the API (seed script has its own boto3 code)
- No `/datasets` pages in the frontend
- No dataset TypeScript types

---

## Data model

### New tables (Alembic migration `002_create_dataset_tables`)

```sql
-- Dataset metadata. One row per logical dataset.
datasets (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  team_id     UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  description TEXT DEFAULT '',
  is_active   BOOLEAN NOT NULL DEFAULT TRUE,  -- soft-delete flag
  created_by  TEXT NOT NULL,                   -- JWT sub
  created_at  TIMESTAMPTZ DEFAULT now(),
  UNIQUE (name, team_id)
)

-- Immutable version snapshot. Each edit/upload creates a new row.
dataset_versions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_id  UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  version     INTEGER NOT NULL,
  s3_key      TEXT NOT NULL,            -- s3://{bucket}/{key}
  row_count   INTEGER NOT NULL,
  created_by  TEXT NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT now(),
  UNIQUE (dataset_id, version)
)
```

### Why not use MLflow's dataset registry?

MLflow datasets are content-addressed (digest-based), don't support team
scoping, and have no edit/version semantics our UI needs. We store dataset
metadata in the RBAC DB and reference the file in S3 directly. A future phase
can register datasets in MLflow for lineage tracking when linking to runs.

---

## S3 key convention

```
datasets/{team_name}/{dataset_name}/v{version}/data.jsonl
```

Example: `datasets/team-alpha/rag-eval/v3/data.jsonl`

---

## Backend tasks

### 1. S3 client abstraction

**New file:** `backend/src/rbac_mlflow/s3_client.py`

Thin async wrapper around `boto3` (sync client, called via `asyncio.to_thread`
since boto3 has no native async support).

Functions:
- `upload_jsonl(key: str, rows: list[dict]) -> None` — serialize and upload
- `download_jsonl(key: str) -> list[dict]` — download and parse
- `get_s3_client()` — FastAPI dependency (configured from settings)

Add `boto3` to `pyproject.toml` `[project.dependencies]`.

### 2. Settings additions

**File:** `backend/src/rbac_mlflow/config.py`

Add:
```python
s3_endpoint_url: str | None = None  # None → real AWS S3
s3_bucket: str = "mlflow-artifacts"
aws_access_key_id: str = "minioadmin"
aws_secret_access_key: str = "minioadmin"
s3_region: str = "us-east-1"
```

### 3. Alembic migration

**New file:** `backend/alembic/versions/002_create_dataset_tables.py`

Creates `datasets` and `dataset_versions` tables as described above.

### 4. SQLAlchemy models

**File:** `backend/src/rbac_mlflow/models.py`

Add `Dataset` and `DatasetVersion` models matching the migration.

### 5. Pydantic schemas

**New file:** `backend/src/rbac_mlflow/datasets/schemas.py`

| Schema | Used in | Fields |
|--------|---------|--------|
| `DatasetSummary` | `GET /datasets` response | id, name, team_name, latest_version, row_count, updated_at, is_active |
| `DatasetDetail` | `GET /datasets/{id}` response | id, name, team_name, description, versions[], rows[] |
| `DatasetVersionInfo` | nested in detail | version, row_count, created_by, created_at |
| `DatasetRow` | nested in detail / PUT body | dict with `inputs.question`, `expectations.expected_response`, etc. |
| `DatasetCreate` | `POST /datasets` body | name, description, rows (list of DatasetRow) |
| `DatasetUpdate` | `PUT /datasets/{id}` body | rows (list of DatasetRow) |
| `DatasetResponse` | `POST` / `PUT` response | id, name, version, row_count |

### 6. Service layer

**New file:** `backend/src/rbac_mlflow/datasets/service.py`

| Function | What it does |
|----------|-------------|
| `list_datasets(db, team_roles)` | SELECT active datasets for user's teams, join latest version |
| `get_dataset_detail(db, s3, dataset_id)` | Fetch metadata + download JSONL from S3, parse rows |
| `create_dataset(db, s3, team_id, body, user_sub)` | Insert dataset + v1, upload to S3 |
| `update_dataset(db, s3, dataset_id, body, user_sub)` | Insert new version row, upload new file to S3 |
| `soft_delete_dataset(db, dataset_id, user_sub)` | Set `is_active = False` |

### 7. RBAC dependency for datasets

**File:** `backend/src/rbac_mlflow/rbac/dependencies.py`

Add `require_dataset_permission(permission)` — similar to
`require_experiment_permission` but resolves `dataset_id → team_id` from the
`datasets` table instead of `team_experiments`.

### 8. Router

**New file:** `backend/src/rbac_mlflow/datasets/router.py`

| Endpoint | Permission | Description |
|----------|-----------|-------------|
| `GET /datasets` | `dataset.read` (filtered by team) | List active datasets for user's teams |
| `GET /datasets/{dataset_id}` | `dataset.read` | Metadata + parsed rows from latest version |
| `GET /datasets/{dataset_id}/versions/{version}` | `dataset.read` | Rows from a specific version |
| `POST /datasets` | `dataset.write` | Create new dataset (body: name, team_id, rows) |
| `PUT /datasets/{dataset_id}` | `dataset.write` | New version with updated rows |
| `DELETE /datasets/{dataset_id}` | `dataset.write` | Soft-delete (set is_active=false) |

Every write endpoint calls `log_audit_event`.

### 9. Register router

**File:** `backend/src/rbac_mlflow/main.py`

Add:
```python
from rbac_mlflow.datasets.router import router as datasets_router
app.include_router(datasets_router)
```

### 10. Add boto3 dependency

**File:** `backend/pyproject.toml`

Add `boto3` (look up current stable version) to `[project.dependencies]`.

---

## Frontend tasks

### 11. TypeScript types

**File:** `frontend/src/lib/types.ts`

Add interfaces: `DatasetSummary`, `DatasetDetail`, `DatasetVersionInfo`,
`DatasetRow`.

### 12. Dataset list page

**New file:** `frontend/src/app/datasets/page.tsx`

Server component that calls `GET /datasets`. Renders a table:

| Column | Source |
|--------|--------|
| Name | `name` (link to `/datasets/{id}`) |
| Team | `team_name` |
| Version | `latest_version` |
| Rows | `row_count` |
| Updated | `updated_at` (formatted) |

Show "New dataset" button only if user has `dataset.write` on any team (pass
role info from session).

### 13. Dataset detail page

**New file:** `frontend/src/app/datasets/[id]/page.tsx`

Two panels:
- **Left/Main:** table of rows (question, expected_response columns). Each cell
  is editable if the user is engineer/owner.
- **Right sidebar / top:** version history (list of `DatasetVersionInfo`),
  click to load that version's rows.

Actions (engineer/owner only):
- "Add row" — appends an empty row to the table
- "Delete row" — removes a row (with confirmation)
- "Save" — POST all rows as a new version → redirects to the new version

### 14. New dataset page

**New file:** `frontend/src/app/datasets/new/page.tsx`

Form with:
- Name (text input)
- Team (dropdown, filtered to teams where user has `dataset.write`)
- Description (optional textarea)
- Rows: either upload a `.jsonl` file OR add rows manually via inline table

Submit → `POST /datasets` → redirect to `/datasets/{id}`.

### 15. Navigation

**File:** `frontend/src/app/layout.tsx`

Add "Datasets" link to the navigation bar, alongside the existing
"Experiments" link.

---

## Tests

### 16. Unit tests — service layer

**New file:** `backend/tests/test_dataset_service.py`

- `test_list_datasets_returns_user_teams_only` — mock DB with datasets in
  both teams, verify filtering by team_roles
- `test_create_dataset_uploads_to_s3` — mock S3, verify `upload_jsonl` called
  with correct key
- `test_update_dataset_creates_new_version` — mock DB + S3, verify new
  version row inserted and version number incremented
- `test_soft_delete_sets_inactive` — verify `is_active` flipped to False

### 17. Unit tests — router / RBAC

**New file:** `backend/tests/test_datasets.py`

Follow the existing `test_experiments.py` pattern (mock auth, DB, S3):

- `test_reader_can_list_datasets` — alice (reader) gets 200 with datasets
- `test_reader_cannot_create_dataset` — alice POSTs → 403
- `test_engineer_can_create_dataset` — bob POSTs → 201
- `test_engineer_can_update_dataset` — bob PUTs → 200
- `test_reader_cannot_delete_dataset` — alice DELETEs → 403
- `test_team_beta_cannot_see_team_alpha_datasets` — dave gets empty list
- `test_audit_logged_on_create` — verify audit entry written
- `test_deleted_dataset_not_in_list` — soft-deleted dataset excluded from
  `GET /datasets`

---

## Task dependency order

```
 1.  Config settings (s3_endpoint_url, s3_bucket, etc.)
 2.  S3 client (s3_client.py)                               ← needs 1
 3.  Alembic migration (002_create_dataset_tables)           ← independent
 4.  SQLAlchemy models (Dataset, DatasetVersion)             ← needs 3
 5.  Pydantic schemas (datasets/schemas.py)                  ← independent
 6.  RBAC dependency (require_dataset_permission)            ← needs 4
 7.  Service layer (datasets/service.py)                     ← needs 2, 4, 5
 8.  Router (datasets/router.py)                             ← needs 5, 6, 7
 9.  Register router in main.py                              ← needs 8
10.  Add boto3 to pyproject.toml                             ← needs 2
11.  TypeScript types                                        ← independent
12.  Dataset list page                                       ← needs 11
13.  Dataset detail page                                     ← needs 11
14.  New dataset page                                        ← needs 11
15.  Navigation update                                       ← needs 12
16.  Unit tests — service                                    ← needs 7
17.  Unit tests — router / RBAC                              ← needs 8
```

Parallelization:
- Steps 1-5 have no mutual dependencies → all in parallel
- Steps 6-7 after 2+4+5
- Step 8 after 5+6+7
- Frontend steps 11-15 can start as soon as schemas are finalized (step 5)
- Tests 16-17 after their respective backend code

---

## Key decisions

**boto3 in the API container:** The backend Dockerfile currently installs
`--no-dev` deps. Adding boto3 to `[project.dependencies]` means it's included
in the production image. This is correct — the API needs S3 access at runtime.

**Sync boto3 in async code:** boto3 has no async client. Use
`asyncio.to_thread(sync_fn)` for S3 calls to avoid blocking the event loop.
Acceptable latency for dataset CRUD (not a hot path).

**No file size limit in phase 6:** Datasets are small (< 10K rows of JSONL).
A 10MB upload limit on the API is sufficient. Phase 8 can add streaming for
larger files if needed.

**Soft-delete vs. hard-delete:** Soft-delete preserves audit trail and allows
recovery. The `is_active` flag filters datasets from list queries. A future
cleanup job can hard-delete old inactive datasets.

**Version immutability:** Once uploaded, a version's S3 file is never
overwritten. This makes rollback trivial (select an older version) and
supports future lineage tracking.
