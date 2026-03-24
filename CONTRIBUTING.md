# Contributing

## Local setup

Start the full stack with one command:

```bash
docker compose up
```

This starts Traefik, PostgreSQL, MinIO, Keycloak, MLflow, the FastAPI backend,
and the Next.js frontend. All services run with TLS via self-signed certs.

Generate certs before first boot (requires `mkcert` or `openssl`):

```bash
bash scripts/gen-certs.sh
```

Add the domain to `/etc/hosts` (the script prints the exact line to add).

Test users (all passwords: `test1234`):

| Username | Team      | Role     |
|----------|-----------|----------|
| alice    | team-alpha | reader  |
| bob      | team-alpha | engineer |
| carol    | team-alpha | owner   |
| dave     | team-beta  | reader  |

## Seed the golden sample

After the stack is healthy, seed the `GoldenSample` experiment:

```bash
make seed
```

This runs the seed service once and exits. Carol (owner) and Alice (reader) will
immediately see `GoldenSample` on their dashboard. Dave (team-beta) will see an
empty dashboard — verifying RBAC isolation.

The seed script is idempotent: re-running is safe and does nothing if the
baseline already exists.

## Run tests

Unit tests (no live services needed):

```bash
make test
```

Regression + integration tests (requires running stack and seeded data):

```bash
make golden-test
```

## Re-baselining

After intentional changes to scorers or the evaluation dataset, regenerate the
baseline run:

```bash
docker compose --profile seed run --rm seed python /scripts/seed_golden_sample.py --force
```

The `--force` flag deletes the old baseline run and creates a new one. Commit
the updated fixture (`tests/fixtures/golden_sample.jsonl`) if the dataset
changed. After re-baselining, verify thresholds in
`backend/tests/test_golden_sample.py` (`METRIC_THRESHOLDS`) still reflect the
new acceptable ranges.

## Lint

```bash
make lint
```
