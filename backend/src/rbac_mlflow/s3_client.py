"""Async-friendly S3/MinIO client for dataset file storage.

boto3 is synchronous. All calls are wrapped in asyncio.to_thread so they do
not block the event loop.
"""

import asyncio
import json
import logging

import boto3
from fastapi import HTTPException

from rbac_mlflow.config import settings

log = logging.getLogger(__name__)


class S3Client:
    """Thin async wrapper around the boto3 S3 client."""

    def __init__(self) -> None:
        kwargs: dict = {
            "region_name": settings.s3_region,
            "aws_access_key_id": settings.aws_access_key_id,
            "aws_secret_access_key": settings.aws_secret_access_key,
        }
        if settings.s3_endpoint_url:
            kwargs["endpoint_url"] = settings.s3_endpoint_url
        self._boto = boto3.client("s3", **kwargs)
        self.bucket = settings.s3_bucket

    # ── internal sync helpers (run inside asyncio.to_thread) ─────────────────

    def _upload_sync(self, key: str, rows: list[dict]) -> None:
        body = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows).encode()
        self._boto.put_object(Bucket=self.bucket, Key=key, Body=body)
        log.info("Uploaded %d rows to s3://%s/%s", len(rows), self.bucket, key)

    def _download_sync(self, key: str) -> list[dict]:
        try:
            resp = self._boto.get_object(Bucket=self.bucket, Key=key)
        except self._boto.exceptions.NoSuchKey:
            raise FileNotFoundError(f"s3://{self.bucket}/{key} not found") from None
        body = resp["Body"].read().decode()
        return [json.loads(line) for line in body.splitlines() if line.strip()]

    # ── public async API ──────────────────────────────────────────────────────

    async def upload_jsonl(self, key: str, rows: list[dict]) -> None:
        """Upload rows as JSONL to the given S3 key."""
        try:
            await asyncio.to_thread(self._upload_sync, key, rows)
        except Exception as exc:
            log.exception("S3 upload failed: %s", key)
            raise HTTPException(status_code=502, detail=f"S3 upload failed: {exc}") from exc

    async def download_jsonl(self, key: str) -> list[dict]:
        """Download and parse a JSONL file from S3."""
        try:
            return await asyncio.to_thread(self._download_sync, key)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404, detail=f"Dataset file not found in S3: {key}"
            ) from None
        except Exception as exc:
            log.exception("S3 download failed: %s", key)
            raise HTTPException(status_code=502, detail=f"S3 download failed: {exc}") from exc


# ── FastAPI dependency ────────────────────────────────────────────────────────

_s3_singleton: S3Client | None = None


def get_s3_client() -> S3Client:
    """Return the shared S3Client singleton (lazily constructed)."""
    global _s3_singleton
    if _s3_singleton is None:
        _s3_singleton = S3Client()
    return _s3_singleton
