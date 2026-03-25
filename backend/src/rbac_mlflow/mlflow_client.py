import json
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


async def log_dataset_inputs(
    client: httpx.AsyncClient,
    run_id: str,
    dataset_name: str,
    digest: str,
    source: str,
    source_type: str = "mlflow",
) -> None:
    """Log a dataset as an input to an MLflow run via POST /runs/log-inputs."""
    body = {
        "run_id": run_id,
        "datasets": [
            {
                "tags": [],
                "dataset": {
                    "name": dataset_name,
                    "digest": digest,
                    "source_type": source_type,
                    "source": source,
                },
            }
        ],
    }
    try:
        resp = await client.post("/api/2.0/mlflow/runs/log-inputs", json=body)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MLflow unavailable: {exc}") from exc
    if not resp.is_success:
        raise HTTPException(
            status_code=502, detail=f"MLflow log-inputs error: {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# MLflow 3.0 Evaluation Dataset API (/api/3.0/mlflow/datasets/...)
# ---------------------------------------------------------------------------


async def create_mlflow_dataset(
    client: httpx.AsyncClient,
    experiment_id: str,
    name: str,
    description: str = "",
    row_count: int = 0,
) -> str:
    """Create an evaluation dataset in MLflow. Returns the dataset_id."""
    tags = json.dumps({"description": description, "row_count": str(row_count)})
    body = {"name": name, "experiment_ids": [experiment_id], "tags": tags}
    try:
        resp = await client.post("/api/3.0/mlflow/datasets/create", json=body)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MLflow unavailable: {exc}") from exc
    if not resp.is_success:
        raise HTTPException(
            status_code=502, detail=f"MLflow dataset create error: {resp.status_code}"
        )
    return resp.json()["dataset"]["dataset_id"]


async def get_mlflow_dataset(client: httpx.AsyncClient, dataset_id: str) -> dict:
    """Fetch a single evaluation dataset by ID. Returns the dataset dict."""
    try:
        resp = await client.get(f"/api/3.0/mlflow/datasets/{dataset_id}")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MLflow unavailable: {exc}") from exc
    if resp.status_code == 404 or (
        resp.status_code == 400 and "RESOURCE_DOES_NOT_EXIST" in resp.text
    ):
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")
    if not resp.is_success:
        raise HTTPException(status_code=502, detail=f"MLflow error: {resp.status_code}")
    return resp.json()["dataset"]


async def search_mlflow_datasets(
    client: httpx.AsyncClient, experiment_id: str
) -> list[dict]:
    """Search evaluation datasets associated with an experiment."""
    body = {"experiment_ids": [experiment_id]}
    try:
        resp = await client.post("/api/3.0/mlflow/datasets/search", json=body)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MLflow unavailable: {exc}") from exc
    if not resp.is_success:
        raise HTTPException(
            status_code=502, detail=f"MLflow dataset search error: {resp.status_code}"
        )
    return resp.json().get("datasets", [])


async def upsert_mlflow_dataset_records(
    client: httpx.AsyncClient, dataset_id: str, records: list[dict]
) -> None:
    """Insert or update records in an evaluation dataset.

    Records must be dicts with at least an 'inputs' key. Existing records matched
    by dataset_record_id are updated; records without an ID are inserted.
    """
    body = {"records": json.dumps(records)}
    try:
        resp = await client.post(f"/api/3.0/mlflow/datasets/{dataset_id}/records", json=body)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MLflow unavailable: {exc}") from exc
    if not resp.is_success:
        raise HTTPException(
            status_code=502, detail=f"MLflow upsert records error: {resp.status_code}"
        )


async def get_mlflow_dataset_records(
    client: httpx.AsyncClient, dataset_id: str
) -> list[dict]:
    """Fetch all records for an evaluation dataset. Returns parsed list of dicts."""
    try:
        resp = await client.get(f"/api/3.0/mlflow/datasets/{dataset_id}/records")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MLflow unavailable: {exc}") from exc
    if not resp.is_success:
        raise HTTPException(
            status_code=502, detail=f"MLflow get records error: {resp.status_code}"
        )
    records_raw = resp.json().get("records", "[]")
    if isinstance(records_raw, list):
        return records_raw
    return json.loads(records_raw)


async def delete_mlflow_dataset_records(
    client: httpx.AsyncClient, dataset_id: str, record_ids: list[str]
) -> None:
    """Delete specific records from an evaluation dataset by their IDs."""
    body = {"dataset_record_ids": record_ids}
    try:
        resp = await client.request(
            "DELETE", f"/api/3.0/mlflow/datasets/{dataset_id}/records", json=body
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MLflow unavailable: {exc}") from exc
    if not resp.is_success:
        raise HTTPException(
            status_code=502, detail=f"MLflow delete records error: {resp.status_code}"
        )


async def replace_mlflow_dataset_records(
    client: httpx.AsyncClient, dataset_id: str, records: list[dict]
) -> None:
    """Replace all records in an evaluation dataset with the provided list.

    Deletes all existing records, then inserts the new ones.
    """
    existing = await get_mlflow_dataset_records(client, dataset_id)
    if existing:
        record_ids = [r["dataset_record_id"] for r in existing if "dataset_record_id" in r]
        if record_ids:
            await delete_mlflow_dataset_records(client, dataset_id, record_ids)
    if records:
        await upsert_mlflow_dataset_records(client, dataset_id, records)


async def set_mlflow_dataset_tags(
    client: httpx.AsyncClient, dataset_id: str, tags: dict
) -> None:
    """Update tags on an evaluation dataset (PATCH replaces all tags)."""
    body = {"tags": json.dumps(tags)}
    try:
        resp = await client.patch(f"/api/3.0/mlflow/datasets/{dataset_id}/tags", json=body)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MLflow unavailable: {exc}") from exc
    if not resp.is_success:
        raise HTTPException(
            status_code=502, detail=f"MLflow set tags error: {resp.status_code}"
        )


async def delete_mlflow_dataset(client: httpx.AsyncClient, dataset_id: str) -> None:
    """Permanently delete an evaluation dataset by ID."""
    try:
        resp = await client.delete(f"/api/3.0/mlflow/datasets/{dataset_id}")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MLflow unavailable: {exc}") from exc
    if resp.status_code == 404 or (
        resp.status_code == 400 and "RESOURCE_DOES_NOT_EXIST" in resp.text
    ):
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")
    if not resp.is_success:
        raise HTTPException(
            status_code=502, detail=f"MLflow dataset delete error: {resp.status_code}"
        )


async def get_mlflow_dataset_experiment_ids(
    client: httpx.AsyncClient, dataset_id: str
) -> list[str]:
    """Return the list of experiment IDs a dataset is associated with."""
    try:
        resp = await client.get(f"/api/3.0/mlflow/datasets/{dataset_id}/experiment-ids")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MLflow unavailable: {exc}") from exc
    if not resp.is_success:
        raise HTTPException(status_code=502, detail=f"MLflow error: {resp.status_code}")
    return list(resp.json().get("experiment_ids", []))
