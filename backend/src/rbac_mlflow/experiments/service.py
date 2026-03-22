import asyncio

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rbac_mlflow.experiments.schemas import (
    ExperimentDetail,
    ExperimentSummary,
    MetricEntry,
    ParamEntry,
    RunDetail,
    RunListResponse,
    RunSummary,
    TagEntry,
)
from rbac_mlflow.mlflow_client import get_experiment, search_runs
from rbac_mlflow.mlflow_client import get_run as mlflow_get_run
from rbac_mlflow.models import TeamExperiment
from rbac_mlflow.rbac.schemas import TeamRole


async def list_experiments_for_user(
    db: AsyncSession,
    mlflow: httpx.AsyncClient,
    team_roles: list[TeamRole],
) -> list[ExperimentSummary]:
    """List experiments the user has access to, with latest run info."""
    if not team_roles:
        return []

    team_map = {tr.team_id: tr.team_name for tr in team_roles}
    team_ids = list(team_map.keys())

    stmt = select(TeamExperiment.mlflow_experiment_id, TeamExperiment.team_id).where(
        TeamExperiment.team_id.in_(team_ids)
    )
    result = await db.execute(stmt)
    links = result.all()

    if not links:
        return []

    async def _fetch_summary(exp_id: str, team_id) -> ExperimentSummary | None:
        try:
            exp = await get_experiment(mlflow, exp_id)
        except Exception:
            return None
        if exp.get("lifecycle_stage") == "deleted":
            return None

        summary = ExperimentSummary(
            experiment_id=exp.get("experiment_id", exp_id),
            name=exp.get("name", exp_id),
            lifecycle_stage=exp.get("lifecycle_stage", "active"),
            creation_time=_to_int(exp.get("creation_time")),
            last_update_time=_to_int(exp.get("last_update_time")),
            team_name=team_map.get(team_id, ""),
        )

        try:
            runs_resp = await search_runs(
                mlflow, [exp_id], max_results=1, order_by=["start_time DESC"]
            )
            runs = runs_resp.get("runs", [])
            if runs:
                run = runs[0]
                info = run.get("info", {})
                summary.latest_run_id = info.get("run_id") or info.get("run_uuid")
                summary.latest_run_status = info.get("status")
                summary.latest_run_start_time = _to_int(info.get("start_time"))
                metrics = _extract_metrics(run.get("data", {}))
                if metrics:
                    summary.key_metric_name = metrics[0].key
                    summary.key_metric_value = metrics[0].value
        except Exception:
            pass

        return summary

    results = await asyncio.gather(
        *[_fetch_summary(link.mlflow_experiment_id, link.team_id) for link in links]
    )
    return [r for r in results if r is not None]


async def get_experiment_detail(
    mlflow: httpx.AsyncClient,
    experiment_id: str,
    team_name: str,
) -> ExperimentDetail:
    """Fetch full experiment metadata from MLflow."""
    exp = await get_experiment(mlflow, experiment_id)
    return ExperimentDetail(
        experiment_id=exp.get("experiment_id", experiment_id),
        name=exp.get("name", experiment_id),
        artifact_location=exp.get("artifact_location", ""),
        lifecycle_stage=exp.get("lifecycle_stage", "active"),
        creation_time=_to_int(exp.get("creation_time")),
        last_update_time=_to_int(exp.get("last_update_time")),
        team_name=team_name,
    )


async def list_runs(
    mlflow: httpx.AsyncClient,
    experiment_id: str,
    max_results: int = 25,
    order_by: str = "start_time DESC",
    page_token: str | None = None,
) -> RunListResponse:
    """Search runs for a given experiment."""
    resp = await search_runs(
        mlflow,
        [experiment_id],
        max_results=max_results,
        order_by=[order_by],
        page_token=page_token,
    )
    runs = [_parse_run_summary(r) for r in resp.get("runs", [])]
    return RunListResponse(
        runs=runs,
        next_page_token=resp.get("next_page_token"),
    )


async def get_run_detail(
    mlflow: httpx.AsyncClient,
    run_id: str,
    experiment_id: str,
) -> RunDetail:
    """Fetch full run detail, verifying it belongs to the expected experiment."""
    run = await mlflow_get_run(mlflow, run_id)
    info = run.get("info", {})
    run_exp_id = info.get("experiment_id")
    if run_exp_id != experiment_id:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail=f"Run '{run_id}' does not belong to experiment '{experiment_id}'",
        )
    return _parse_run_detail(run)


def _parse_run_summary(run_data: dict) -> RunSummary:
    info = run_data.get("info", {})
    return RunSummary(
        run_id=info.get("run_id") or info.get("run_uuid", ""),
        run_name=info.get("run_name"),
        status=info.get("status", "UNKNOWN"),
        start_time=_to_int(info.get("start_time")),
        end_time=_to_int(info.get("end_time")),
        metrics=_extract_metrics(run_data.get("data", {})),
    )


def _parse_run_detail(run_data: dict) -> RunDetail:
    info = run_data.get("info", {})
    data = run_data.get("data", {})
    return RunDetail(
        run_id=info.get("run_id") or info.get("run_uuid", ""),
        run_name=info.get("run_name"),
        experiment_id=info.get("experiment_id", ""),
        status=info.get("status", "UNKNOWN"),
        start_time=_to_int(info.get("start_time")),
        end_time=_to_int(info.get("end_time")),
        artifact_uri=info.get("artifact_uri"),
        lifecycle_stage=info.get("lifecycle_stage"),
        metrics=_extract_metrics(data),
        params=_extract_kv(data.get("params"), ParamEntry),
        tags=_extract_kv(data.get("tags"), TagEntry),
    )


def _extract_metrics(data: dict) -> list[MetricEntry]:
    """Extract metrics from MLflow data, handling both list and dict formats."""
    raw = data.get("metrics")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [
            MetricEntry(
                key=m.get("key", ""),
                value=float(m.get("value", 0)),
                timestamp=_to_int(m.get("timestamp")),
                step=_to_int(m.get("step")),
            )
            for m in raw
        ]
    if isinstance(raw, dict):
        return [MetricEntry(key=k, value=float(v)) for k, v in raw.items()]
    return []


def _extract_kv(raw, cls: type):
    """Extract key-value pairs, handling both list and dict formats."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [cls(key=item.get("key", ""), value=str(item.get("value", ""))) for item in raw]
    if isinstance(raw, dict):
        return [cls(key=k, value=str(v)) for k, v in raw.items()]
    return []


def _to_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
