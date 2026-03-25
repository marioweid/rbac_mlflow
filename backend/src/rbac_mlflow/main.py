import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rbac_mlflow.admin.router import router as admin_router
from rbac_mlflow.auth.middleware import AuthMiddleware
from rbac_mlflow.auth.router import router as auth_router
from rbac_mlflow.bootstrap import run_bootstrap
from rbac_mlflow.config import settings
from rbac_mlflow.datasets.router import router as datasets_router
from rbac_mlflow.experiments.router import router as experiments_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    await run_bootstrap()
    _app.state.mlflow_client = httpx.AsyncClient(
        base_url=settings.mlflow_tracking_uri,
        timeout=30.0,
    )
    yield
    await _app.state.mlflow_client.aclose()


app = FastAPI(title="rbac-mlflow API", version="0.1.0", lifespan=lifespan)

_frontend_origins = [
    f"https://{os.getenv('TRAEFIK_DOMAIN', 'rbac.local')}",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(experiments_router)
# Datasets are nested under /experiments — include with /experiments prefix so
# final paths are /experiments/{experiment_id}/datasets/...
app.include_router(datasets_router, prefix="/experiments")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "rbac-mlflow-api"}
