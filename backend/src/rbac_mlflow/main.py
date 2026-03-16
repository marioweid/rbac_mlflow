import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="rbac-mlflow API", version="0.1.0")

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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "rbac-mlflow-api"}
