import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DatasetVersionInfo(BaseModel):
    version: int
    row_count: int
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetSummary(BaseModel):
    id: uuid.UUID
    name: str
    team_name: str
    description: str
    latest_version: int
    row_count: int
    updated_at: datetime
    is_active: bool


class DatasetDetail(BaseModel):
    id: uuid.UUID
    name: str
    team_name: str
    description: str
    versions: list[DatasetVersionInfo]
    rows: list[dict[str, Any]]


class DatasetCreate(BaseModel):
    name: str
    team_name: str
    description: str = ""
    rows: list[dict[str, Any]]


class DatasetUpdate(BaseModel):
    rows: list[dict[str, Any]]


class DatasetResponse(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    row_count: int
