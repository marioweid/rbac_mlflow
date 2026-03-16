FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /bin/uv

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Install the project itself
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# ── Runtime image ─────────────────────────────────────────────────────────────
FROM python:3.13-slim

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src   /app/src

ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

EXPOSE 8000

CMD ["uvicorn", "rbac_mlflow.main:app", "--host", "0.0.0.0", "--port", "8000"]
