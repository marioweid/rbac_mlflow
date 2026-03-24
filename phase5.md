# Phase 5 — Golden Sample Bootstrap & Regression Tests

## Goal

After `docker compose up` and a single `make seed` command, a logged-in
team-alpha user (e.g. Carol) sees a `GoldenSample` experiment with a finished
baseline run on the dashboard. RBAC isolation is verified: a team-beta user
(dave) sees an empty dashboard.

---

## Task breakdown

### 1. Add team-beta to Keycloak realm

**File:** `keycloak/realm-export.json`

Add:
- Groups: `/team-beta`, `/team-beta/readers`, `/team-beta/engineers`, `/team-beta/owners`
- User: `dave` (password: `test1234`) assigned to `/team-beta/readers`

This ensures the dev Keycloak instance has both teams from first boot.

---

### 2. Seed team-beta in the RBAC database

**File:** `backend/src/rbac_mlflow/bootstrap.py`

The existing bootstrap seeds team-alpha only when `group_role_mappings` is
empty. Extend it to also create `team-beta` with its three group→role
mappings in the same idempotent pass.

Both teams share the same "only act on empty table" guard, so re-running is
safe.

---

### 3. Golden dataset fixture

**File:** `tests/fixtures/golden_sample.jsonl`

Committed JSONL with 8 rows covering:

| Row | Scenario |
|-----|----------|
| 1-3 | Correct factual answers |
| 4   | Appropriate refusal (harmful request) |
| 5   | Multilingual (French) |
| 6   | Short/terse answer |
| 7   | Empty-ish input edge case |
| 8   | Long context answer |

Required fields per row: `inputs.question`, `expectations.expected_response`

---

### 4. Seed script

**File:** `scripts/seed_golden_sample.py`

Standalone Python script (run inside the `mlflow` container or locally with
env vars set). Uses only the MLflow REST API and boto3 — no FastAPI import.

Steps:
1. Check if a `GoldenSample` experiment already has a `FINISHED` baseline run.
   - If yes and `--force` is not set: exit 0 (idempotent).
2. Create (or reuse) the `GoldenSample` MLflow experiment.
3. Upload `tests/fixtures/golden_sample.jsonl` to MinIO at
   `s3://{S3_BUCKET}/datasets/golden_sample/v1/data.jsonl`.
4. Start an MLflow run named `baseline`.
5. Evaluate each row with a **deterministic Python scorer** (no LLM call by
   default):
   - `exact_match`: 1.0 if expected == actual, else 0.0
   - `is_non_empty`: 1.0 if response is non-empty, else 0.0
   - By default the "model" returns the expected answer (perfect baseline).
6. Log aggregate metrics (`exact_match/mean`, `is_non_empty/mean`), the
   dataset path as a param, and finish the run with `FINISHED` status.
7. Insert a `team_experiments` row linking the experiment to `team-alpha`.
   Skip if row already exists (idempotent upsert).

**Flags:**
- `--force`: delete and re-create the baseline run even if one exists.
- `--mlflow-uri`: override `MLFLOW_TRACKING_URI` (default: env var).
- `--db-url`: override `DATABASE_URL` (default: env var).

**Dependencies** (added to `scripts/requirements.txt`):
- `mlflow` (REST calls via `requests`)
- `boto3`
- `psycopg2-binary`

---

### 5. Docker Compose seed service

**File:** `docker-compose.yml`

Add a `seed` service:
- Reuses the `mlflow` custom image (already has boto3 + psycopg2-binary).
- Mounts `./scripts` and `./tests/fixtures` read-only.
- Depends on `api` (service_healthy) and `mlflow` (service_started).
- `restart: no` — runs once and exits.
- Command: `python /scripts/seed_golden_sample.py`

Usage: `docker compose run --rm seed` or `make seed`.

---

### 6. Regression tests

**File:** `backend/tests/test_golden_sample.py`

All tests follow the existing mocked pattern (no live services needed for
`pytest -q`). Integration tests that need live services are marked
`@pytest.mark.integration` and skipped by default.

#### Unit tests (always run)

| Test | What it checks |
|------|---------------|
| `test_fixture_parses` | JSONL loads, has >= 8 rows, all have required fields |
| `test_fixture_field_types` | `inputs.question` and `expectations.expected_response` are non-empty strings |
| `test_team_alpha_sees_golden_experiment` | `GET /experiments` returns `GoldenSample` for alice (team-alpha reader) |
| `test_team_beta_sees_empty_dashboard` | `GET /experiments` returns `[]` for dave (team-beta reader) |
| `test_baseline_run_is_linked_to_team_alpha_only` | Mock DB with GoldenSample→team-beta link: dave gets `[]`, alice gets result |

#### Integration tests (run via `make golden-test`)

| Test | What it checks |
|------|---------------|
| `test_baseline_run_exists_in_mlflow` | Calls live MLflow; baseline run has status `FINISHED` |
| `test_baseline_metrics_present` | `exact_match/mean` and `is_non_empty/mean` present on run |
| `test_baseline_metrics_within_threshold` | `exact_match/mean >= 0.9`, `is_non_empty/mean >= 0.95` |

---

### 7. Makefile targets

**File:** `Makefile`

```
seed          docker compose run --rm seed
golden-test   make seed && pytest backend/tests/test_golden_sample.py -m integration
test          pytest backend/tests/ -q
lint          ruff check backend/src && ruff format --check backend/src
```

---

### 8. CONTRIBUTING.md — re-baselining

**File:** `CONTRIBUTING.md`

Document:
1. How to run `make seed` to populate the dev environment.
2. How to re-baseline after intentional changes:
   ```
   docker compose run --rm seed python /scripts/seed_golden_sample.py --force
   ```
3. How to run regression tests: `make golden-test`.

---

## Task dependency order

```
1. realm-export.json update        (no deps)
2. bootstrap.py update             (no deps, parallel with 1)
3. golden_sample.jsonl             (no deps)
4. seed_golden_sample.py           (needs 3)
5. docker-compose seed service     (needs 4)
6. conftest.py dave fixtures       (no deps)
7. test_golden_sample.py           (needs 3, 6)
8. Makefile                        (needs 4, 7)
9. CONTRIBUTING.md                 (needs all above)
```

## Scorer approach decision

Default scorer is a deterministic Python function (no LLM, no API key). For
the dev seed, the "model under test" simply returns the expected answer, so
`exact_match/mean = 1.0` by design. This makes CI reliable and removes the
external dependency.

To re-baseline with a real model: set `OPENAI_API_KEY` (or equivalent) and
run with `--llm-scorer` (future extension, not implemented in phase 5).
