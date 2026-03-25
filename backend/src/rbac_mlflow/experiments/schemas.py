from pydantic import BaseModel


class ExperimentSummary(BaseModel):
    """Dashboard card: experiment with latest run info."""

    experiment_id: str
    name: str
    lifecycle_stage: str
    creation_time: int | None = None
    last_update_time: int | None = None
    team_name: str
    latest_run_status: str | None = None
    latest_run_id: str | None = None
    latest_run_start_time: int | None = None
    key_metric_name: str | None = None
    key_metric_value: float | None = None


class ExperimentDetail(BaseModel):
    """Full experiment metadata."""

    experiment_id: str
    name: str
    artifact_location: str
    lifecycle_stage: str
    creation_time: int | None = None
    last_update_time: int | None = None
    team_name: str


class MetricEntry(BaseModel):
    key: str
    value: float
    timestamp: int | None = None
    step: int | None = None


class ParamEntry(BaseModel):
    key: str
    value: str


class TagEntry(BaseModel):
    key: str
    value: str


class RunSummary(BaseModel):
    """Runs table row."""

    run_id: str
    run_name: str | None = None
    status: str
    start_time: int | None = None
    end_time: int | None = None
    metrics: list[MetricEntry] = []


class RunDetail(BaseModel):
    """Full run detail."""

    run_id: str
    run_name: str | None = None
    experiment_id: str
    status: str
    start_time: int | None = None
    end_time: int | None = None
    artifact_uri: str | None = None
    lifecycle_stage: str | None = None
    metrics: list[MetricEntry] = []
    params: list[ParamEntry] = []
    tags: list[TagEntry] = []


class RunListResponse(BaseModel):
    runs: list[RunSummary]
    next_page_token: str | None = None


class StartRunRequest(BaseModel):
    """Body for POST /experiments/{id}/runs."""

    dataset_id: str  # MLflow dataset_id (e.g. "d-1cafa29844fe4a24a60dc53189b6eccb")
    run_name: str | None = None  # auto-generated if omitted


class StartRunResponse(BaseModel):
    """Response for POST /experiments/{id}/runs."""

    run_id: str
    experiment_id: str
    run_name: str
    status: str
