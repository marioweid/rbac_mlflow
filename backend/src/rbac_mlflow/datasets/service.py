import json
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException

from rbac_mlflow.datasets.schemas import (
    DatasetCreate,
    DatasetDetail,
    DatasetResponse,
    DatasetSummary,
    DatasetUpdate,
)
from rbac_mlflow.mlflow_client import (
    create_mlflow_dataset,
    delete_mlflow_dataset,
    get_mlflow_dataset,
    get_mlflow_dataset_experiment_ids,
    get_mlflow_dataset_records,
    replace_mlflow_dataset_records,
    search_mlflow_datasets,
    set_mlflow_dataset_tags,
    upsert_mlflow_dataset_records,
)


_MLFLOW_RECORD_INTERNAL_FIELDS = {
    "dataset_record_id",
    "dataset_id",
    "created_time",
    "last_update_time",
    "outputs",
    "tags",
}


def _clean_record(record: dict) -> dict:
    return {k: v for k, v in record.items() if k not in _MLFLOW_RECORD_INTERNAL_FIELDS}


def _parse_tags(tags_str: str) -> dict:
    try:
        return json.loads(tags_str) if tags_str else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _ms_to_datetime(ms: int | None) -> datetime:
    if ms is None:
        return datetime.now(UTC)
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


async def _assert_dataset_in_experiment(
    mlflow: httpx.AsyncClient, dataset_id: str, experiment_id: str
) -> None:
    """Raise 403 if the dataset is not associated with the given experiment."""
    exp_ids = await get_mlflow_dataset_experiment_ids(mlflow, dataset_id)
    if experiment_id not in exp_ids:
        raise HTTPException(
            status_code=403, detail="Dataset does not belong to this experiment"
        )


async def list_datasets(
    mlflow: httpx.AsyncClient, experiment_id: str
) -> list[DatasetSummary]:
    datasets = await search_mlflow_datasets(mlflow, experiment_id)
    result = []
    for ds in datasets:
        tags = _parse_tags(ds.get("tags", "{}"))
        result.append(
            DatasetSummary(
                id=ds["dataset_id"],
                name=ds["name"],
                experiment_id=experiment_id,
                description=tags.get("description", ""),
                row_count=int(tags.get("row_count", 0)),
                updated_at=_ms_to_datetime(ds.get("last_update_time")),
            )
        )
    return result


async def get_dataset_detail(
    mlflow: httpx.AsyncClient, dataset_id: str, experiment_id: str
) -> DatasetDetail:
    await _assert_dataset_in_experiment(mlflow, dataset_id, experiment_id)
    ds = await get_mlflow_dataset(mlflow, dataset_id)
    records = await get_mlflow_dataset_records(mlflow, dataset_id)
    tags = _parse_tags(ds.get("tags", "{}"))
    return DatasetDetail(
        id=ds["dataset_id"],
        name=ds["name"],
        experiment_id=experiment_id,
        description=tags.get("description", ""),
        rows=[_clean_record(r) for r in records],
    )


async def create_dataset(
    mlflow: httpx.AsyncClient,
    experiment_id: str,
    body: DatasetCreate,
    user_sub: str,
) -> DatasetResponse:
    dataset_id = await create_mlflow_dataset(
        mlflow,
        experiment_id=experiment_id,
        name=body.name,
        description=body.description,
        row_count=len(body.rows),
    )
    if body.rows:
        await upsert_mlflow_dataset_records(mlflow, dataset_id, body.rows)
    return DatasetResponse(
        id=dataset_id,
        name=body.name,
        experiment_id=experiment_id,
        row_count=len(body.rows),
    )


async def update_dataset(
    mlflow: httpx.AsyncClient,
    dataset_id: str,
    experiment_id: str,
    body: DatasetUpdate,
    user_sub: str,
) -> DatasetResponse:
    await _assert_dataset_in_experiment(mlflow, dataset_id, experiment_id)
    ds = await get_mlflow_dataset(mlflow, dataset_id)
    await replace_mlflow_dataset_records(mlflow, dataset_id, body.rows)
    tags = _parse_tags(ds.get("tags", "{}"))
    tags["row_count"] = str(len(body.rows))
    await set_mlflow_dataset_tags(mlflow, dataset_id, tags)
    return DatasetResponse(
        id=dataset_id,
        name=ds["name"],
        experiment_id=experiment_id,
        row_count=len(body.rows),
    )


async def delete_dataset(mlflow: httpx.AsyncClient, dataset_id: str, experiment_id: str) -> None:
    await _assert_dataset_in_experiment(mlflow, dataset_id, experiment_id)
    await delete_mlflow_dataset(mlflow, dataset_id)
