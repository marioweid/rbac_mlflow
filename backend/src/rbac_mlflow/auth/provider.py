from rbac_mlflow.auth.providers.base import AuthProvider
from rbac_mlflow.auth.providers.iam import IAMProvider
from rbac_mlflow.auth.providers.keycloak import KeycloakProvider
from rbac_mlflow.config import settings

_PROVIDERS: dict[str, type] = {
    "keycloak": KeycloakProvider,
    "iam": IAMProvider,
}

_instance: AuthProvider | None = None


def get_auth_provider() -> AuthProvider:
    """Return the singleton auth provider based on AUTH_PROVIDER env var."""
    global _instance  # noqa: PLW0603
    if _instance is None:
        provider_cls = _PROVIDERS.get(settings.auth_provider)
        if provider_cls is None:
            msg = (
                f"Unknown AUTH_PROVIDER={settings.auth_provider!r}. Valid: {', '.join(_PROVIDERS)}"
            )
            raise ValueError(msg)
        _instance = provider_cls()
    return _instance
