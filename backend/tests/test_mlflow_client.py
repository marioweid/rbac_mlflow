from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException

from rbac_mlflow.mlflow_client import get_experiment, get_run, search_runs


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
