import time

import httpx


class JWKSCache:
    """Fetches and caches a JWKS key set with a TTL."""

    def __init__(self, uri: str, ttl_seconds: int = 300) -> None:
        self._uri = uri
        self._ttl = ttl_seconds
        self._keys: dict[str, object] = {}
        self._fetched_at: float = 0

    async def get_key(self, kid: str) -> object:
        if not self._keys or self._is_stale():
            await self._refresh()

        key = self._keys.get(kid)
        if key is None:
            # Key might have rotated -- force one refresh and retry
            await self._refresh()
            key = self._keys.get(kid)

        if key is None:
            msg = f"No key found for kid={kid}"
            raise KeyError(msg)
        return key

    def _is_stale(self) -> bool:
        return (time.monotonic() - self._fetched_at) > self._ttl

    async def _refresh(self) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(self._uri, timeout=10)
            resp.raise_for_status()
        data = resp.json()
        self._keys = {k["kid"]: k for k in data.get("keys", [])}
        self._fetched_at = time.monotonic()
