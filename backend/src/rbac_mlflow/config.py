from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    auth_provider: str = "keycloak"
    jwt_issuer: str = "http://keycloak:8080/realms/rbac-mlflow"
    jwt_audience: str = "rbac-frontend"
    jwks_uri: str = "http://keycloak:8080/realms/rbac-mlflow/protocol/openid-connect/certs"

    database_url: str = "postgresql+asyncpg://rbac:changeme@postgres:5432/rbac_db"
    mlflow_tracking_uri: str = "http://mlflow:5000"

    s3_endpoint_url: str | None = None  # None → real AWS S3; set to MinIO URL for local dev
    s3_bucket: str = "mlflow-artifacts"
    s3_region: str = "us-east-1"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"

    bootstrap_admin_group: str = "/team-alpha/owners"
    bootstrap_team_name: str = "team-alpha"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
