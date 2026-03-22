import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TeamRole(BaseModel):
    """A user's resolved role within a specific team."""

    team_id: uuid.UUID
    team_name: str
    role: str


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class TeamResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime


class MappingCreate(BaseModel):
    group_name: str = Field(min_length=1, max_length=255)
    role: str = Field(pattern=r"^(reader|engineer|owner)$")


class MappingResponse(BaseModel):
    id: uuid.UUID
    group_name: str
    team_id: uuid.UUID
    role: str


class ExperimentLinkCreate(BaseModel):
    mlflow_experiment_id: str = Field(min_length=1)


class ExperimentLinkResponse(BaseModel):
    team_id: uuid.UUID
    mlflow_experiment_id: str
