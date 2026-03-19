from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    auth_provider: str = "keycloak"
    jwt_issuer: str = "http://keycloak:8080/realms/rbac-mlflow"
    jwt_audience: str = "rbac-frontend"
    jwks_uri: str = "http://keycloak:8080/realms/rbac-mlflow/protocol/openid-connect/certs"

    database_url: str = "postgresql+asyncpg://rbac:changeme@postgres:5432/rbac_db"
    mlflow_tracking_uri: str = "http://mlflow:5000"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
