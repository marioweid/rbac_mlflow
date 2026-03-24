from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException

from rbac_mlflow.mlflow_client import (
    create_run,
    get_experiment,
    get_run,
    log_batch,
    search_runs,
    update_run,
)


def _mock_response(status_code: int = 200, json_data: dict | None = None, text: str = ""):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


class TestGetExperiment:
    @pytest.mark.asyncio
    async def test_returns_experiment_dict(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = _mock_response(
            json_data={"experiment": {"experiment_id": "1", "name": "test-exp"}}
        )
        result = await get_experiment(client, "1")
        assert result["experiment_id"] == "1"
        assert result["name"] == "test-exp"

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = _mock_response(status_code=400, text="RESOURCE_DOES_NOT_EXIST")
        with pytest.raises(HTTPException) as exc_info:
            await get_experiment(client, "999")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raises_502_on_connection_error(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.side_effect = httpx.ConnectError("connection refused")
        with pytest.raises(HTTPException) as exc_info:
            await get_experiment(client, "1")
        assert exc_info.value.status_code == 502


class TestSearchRuns:
    @pytest.mark.asyncio
    async def test_returns_response_dict(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _mock_response(
            json_data={
                "runs": [{"info": {"run_id": "r1"}}],
                "next_page_token": "tok",
            }
        )
        result = await search_runs(client, ["1"], max_results=10)
        assert len(result["runs"]) == 1
        assert result["next_page_token"] == "tok"

    @pytest.mark.asyncio
    async def test_raises_502_on_mlflow_error(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _mock_response(status_code=500)
        with pytest.raises(HTTPException) as exc_info:
            await search_runs(client, ["1"])
        assert exc_info.value.status_code == 502


class TestGetRun:
    @pytest.mark.asyncio
    async def test_returns_run_dict(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = _mock_response(
            json_data={"run": {"info": {"run_id": "r1"}, "data": {}}}
        )
        result = await get_run(client, "r1")
        assert result["info"]["run_id"] == "r1"

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get.return_value = _mock_response(status_code=400, text="RESOURCE_DOES_NOT_EXIST")
        with pytest.raises(HTTPException) as exc_info:
            await get_run(client, "missing")
        assert exc_info.value.status_code == 404


class TestCreateRun:
    @pytest.mark.asyncio
    async def test_returns_run_dict_on_success(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        run_payload = {"info": {"run_id": "abc123", "experiment_id": "1"}, "data": {}}
        client.post.return_value = _mock_response(json_data={"run": run_payload})

        result = await create_run(client, "1", "my-run", {"key": "val"})

        assert result["info"]["run_id"] == "abc123"

    @pytest.mark.asyncio
    async def test_sends_tags_in_payload(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        run_payload = {"info": {"run_id": "r1"}, "data": {}}
        client.post.return_value = _mock_response(json_data={"run": run_payload})

        await create_run(client, "1", "run", {"started_by": "bob-id"})

        _, kwargs = client.post.call_args
        tags = kwargs["json"]["tags"]
        assert {"key": "started_by", "value": "bob-id"} in tags

    @pytest.mark.asyncio
    async def test_raises_502_on_mlflow_error(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _mock_response(status_code=500)

        with pytest.raises(HTTPException) as exc_info:
            await create_run(client, "1", "run")

        assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_raises_502_on_connection_error(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.side_effect = httpx.ConnectError("refused")

        with pytest.raises(HTTPException) as exc_info:
            await create_run(client, "1", "run")

        assert exc_info.value.status_code == 502


class TestLogBatch:
    @pytest.mark.asyncio
    async def test_sends_metrics_and_params(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _mock_response()
        metrics = [{"key": "exact_match/mean", "value": 1.0, "timestamp": 0, "step": 0}]
        params = [{"key": "scorer", "value": "deterministic_identity"}]

        await log_batch(client, "run1", metrics=metrics, params=params)

        _, kwargs = client.post.call_args
        body = kwargs["json"]
        assert body["run_id"] == "run1"
        assert body["metrics"][0]["key"] == "exact_match/mean"
        assert body["params"][0]["key"] == "scorer"

    @pytest.mark.asyncio
    async def test_empty_lists_are_valid(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _mock_response()

        await log_batch(client, "run1")  # no error expected

    @pytest.mark.asyncio
    async def test_raises_502_on_mlflow_error(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _mock_response(status_code=400)

        with pytest.raises(HTTPException) as exc_info:
            await log_batch(client, "run1")

        assert exc_info.value.status_code == 502


class TestUpdateRun:
    @pytest.mark.asyncio
    async def test_sends_finished_status(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _mock_response(json_data={"run_info": {}})

        await update_run(client, "run1", "FINISHED")

        _, kwargs = client.post.call_args
        assert kwargs["json"]["run_id"] == "run1"
        assert kwargs["json"]["status"] == "FINISHED"

    @pytest.mark.asyncio
    async def test_sends_failed_status(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _mock_response(json_data={"run_info": {}})

        await update_run(client, "run1", "FAILED")

        _, kwargs = client.post.call_args
        assert kwargs["json"]["status"] == "FAILED"

    @pytest.mark.asyncio
    async def test_uses_provided_end_time(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _mock_response(json_data={"run_info": {}})

        await update_run(client, "run1", "FINISHED", end_time=12345)

        _, kwargs = client.post.call_args
        assert kwargs["json"]["end_time"] == 12345

    @pytest.mark.asyncio
    async def test_raises_502_on_mlflow_error(self) -> None:
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _mock_response(status_code=500)

        with pytest.raises(HTTPException) as exc_info:
            await update_run(client, "run1", "FINISHED")

        assert exc_info.value.status_code == 502
