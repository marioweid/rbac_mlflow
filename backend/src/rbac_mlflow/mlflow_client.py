import time

import httpx
from fastapi import HTTPException, Request


def get_mlflow_client(request: Request) -> httpx.AsyncClient:
    """FastAPI dependency: return the shared MLflow httpx client."""
    return request.app.state.mlflow_client


async def get_experiment(client: httpx.AsyncClient, experiment_id: str) -> dict:
    """Fetch a single experiment from MLflow by ID."""
    try:
        resp = await client.get(
            "/api/2.0/mlflow/experiments/get",
            params={"experiment_id": experiment_id},
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MLflow unavailable: {exc}") from exc
    if resp.status_code == 404 or (
        resp.status_code == 400 and "RESOURCE_DOES_NOT_EXIST" in resp.text
    ):
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")
    if not resp.is_success:
        raise HTTPException(status_code=502, detail=f"MLflow error: {resp.status_code}")
    return resp.json()["experiment"]


async def search_runs(
    client: httpx.AsyncClient,
    experiment_ids: list[str],
    max_results: int = 25,
    order_by: list[str] | None = None,
    page_token: str | None = None,
) -> dict:
    """Search runs in MLflow for given experiment IDs."""
    body: dict = {
        "experiment_ids": experiment_ids,
        "max_results": max_results,
        "run_view_type": "ACTIVE_ONLY",
    }
    if order_by:
        body["order_by"] = order_by
    if page_token:
        body["page_token"] = page_token
    try:
        resp = await client.post("/api/2.0/mlflow/runs/search", json=body)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MLflow unavailable: {exc}") from exc
    if not resp.is_success:
        raise HTTPException(status_code=502, detail=f"MLflow error: {resp.status_code}")
    return resp.json()


async def get_run(client: httpx.AsyncClient, run_id: str) -> dict:
    """Fetch a single run from MLflow by run ID."""
    try:
        resp = await client.get(
            "/api/2.0/mlflow/runs/get",
            params={"run_id": run_id},
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MLflow unavailable: {exc}") from exc
    if resp.status_code == 404 or (
        resp.status_code == 400 and "RESOURCE_DOES_NOT_EXIST" in resp.text
    ):
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if not resp.is_success:
        raise HTTPException(status_code=502, detail=f"MLflow error: {resp.status_code}")
    return resp.json()["run"]


async def create_run(
    client: httpx.AsyncClient,
    experiment_id: str,
    run_name: str,
    tags: dict[str, str] | None = None,
) -> dict:
    """Create a new MLflow run in RUNNING state. Returns the full run dict."""
    body: dict = {
        "experiment_id": experiment_id,
        "start_time": int(time.time() * 1000),
        "tags": [{"key": k, "value": v} for k, v in (tags or {}).items()],
        "run_name": run_name,
    }
    try:
        resp = await client.post("/api/2.0/mlflow/runs/create", json=body)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MLflow unavailable: {exc}") from exc
    if not resp.is_success:
        raise HTTPException(status_code=502, detail=f"MLflow error: {resp.status_code}")
    return resp.json()["run"]


async def log_batch(
    client: httpx.AsyncClient,
    run_id: str,
    metrics: list[dict] | None = None,
    params: list[dict] | None = None,
    tags: list[dict] | None = None,
) -> None:
    """Log metrics, params, and tags for a run in a single batch call."""
    body: dict = {
        "run_id": run_id,
        "metrics": metrics or [],
        "params": params or [],
        "tags": tags or [],
    }
    try:
        resp = await client.post("/api/2.0/mlflow/runs/log-batch", json=body)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MLflow unavailable: {exc}") from exc
    if not resp.is_success:
        raise HTTPException(status_code=502, detail=f"MLflow error: {resp.status_code}")


async def update_run(
    client: httpx.AsyncClient,
    run_id: str,
    status: str,
    end_time: int | None = None,
) -> None:
    """Set the status (and end_time) of an MLflow run."""
    body: dict = {
        "run_id": run_id,
        "status": status,
        "end_time": end_time if end_time is not None else int(time.time() * 1000),
    }
    try:
        resp = await client.post("/api/2.0/mlflow/runs/update", json=body)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MLflow unavailable: {exc}") from exc
    if not resp.is_success:
        raise HTTPException(status_code=502, detail=f"MLflow error: {resp.status_code}")
