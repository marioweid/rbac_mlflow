.PHONY: seed golden-test test lint

## Seed the GoldenSample experiment and RBAC links into the running stack.
## Requires: docker compose up (all services healthy).
seed:
	docker compose --profile seed run --rm -T seed

## Run the seed script then execute integration regression tests.
golden-test: seed
	cd backend && uv run pytest tests/test_golden_sample.py -m integration -v \
		--override-ini=addopts= \
		--mlflow-uri $${MLFLOW_TRACKING_URI:-http://localhost:5001}

## Run the full unit test suite (no live services required).
test:
	cd backend && uv run pytest -q

## Lint and type-check the backend.
lint:
	cd backend && uv run ruff check src && uv run ruff format --check src && uv run ty check src
