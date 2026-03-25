from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DatasetSummary(BaseModel):
    id: str  # MLflow dataset_id (e.g. "d-1cafa29844fe4a24a60dc53189b6eccb")
    name: str
    experiment_id: str
    description: str
    row_count: int
    updated_at: datetime


class DatasetDetail(BaseModel):
    id: str  # MLflow dataset_id
    name: str
    experiment_id: str
    description: str
    rows: list[dict[str, Any]]


class DatasetCreate(BaseModel):
    name: str
    description: str = ""
    rows: list[dict[str, Any]]


class DatasetUpdate(BaseModel):
    rows: list[dict[str, Any]]


class DatasetResponse(BaseModel):
    id: str  # MLflow dataset_id
    name: str
    experiment_id: str
    row_count: int
