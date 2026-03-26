#!/usr/bin/env python3
"""Seed a GoldenSample experiment with a deterministic baseline run.

Usage:
    python seed_golden_sample.py [--force] [--mlflow-uri URI] [--db-url URL]

Flags:
    --force       Re-create the baseline run even if one already exists.
    --mlflow-uri  MLflow tracking URI (default: $MLFLOW_TRACKING_URI).
    --db-url      PostgreSQL URL for the RBAC database (default: $DATABASE_URL).

The script is idempotent by default: if a FINISHED baseline run already exists
in the GoldenSample experiment it exits 0 without making any changes.

Scorer: deterministic Python function (no LLM, no API key required). The
"model under test" returns the expected answer verbatim, so exact_match/mean
is 1.0 by design, giving a stable regression baseline.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import boto3  # type: ignore[import-untyped]
import psycopg2  # type: ignore[import-untyped]
import psycopg2.extras  # type: ignore[import-untyped]

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

EXPERIMENT_NAME = "GoldenSample"
RUN_NAME = "baseline"
DATASET_S3_KEY = "datasets/golden_sample/v1/data.jsonl"
FIXTURE_PATH = Path(__file__).parent.parent / "tests" / "fixtures" / "golden_sample.jsonl"

# Metric thresholds used to detect regressions (also referenced in tests).
METRIC_THRESHOLDS: dict[str, float] = {
    "exact_match/mean": 0.9,
    "is_non_empty/mean": 0.95,
    "facts_covered/mean": 0.9,
}


# ── MLflow REST helpers ───────────────────────────────────────────────────────


def _mlflow_request(
    method: str,
    base_uri: str,
    path: str,
    body: dict | None = None,
    *,
    timeout: int = 30,
) -> dict:
    url = f"{base_uri.rstrip('/')}/api/2.0/mlflow/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"MLflow {method} {path} failed {exc.code}: {exc.read().decode()}") from exc


def _get_or_create_experiment(mlflow_uri: str) -> str:
    """Return the experiment_id for GoldenSample, creating it if needed."""
    try:
        result = _mlflow_request(
            "GET", mlflow_uri, f"experiments/get-by-name?experiment_name={EXPERIMENT_NAME}"
        )
        exp_id: str = result["experiment"]["experiment_id"]
        log.info("Found existing experiment '%s' (id=%s)", EXPERIMENT_NAME, exp_id)
        return exp_id
    except RuntimeError as exc:
        if "RESOURCE_DOES_NOT_EXIST" not in str(exc):
            raise
    result = _mlflow_request(
        "POST", mlflow_uri, "experiments/create", {"name": EXPERIMENT_NAME}
    )
    exp_id = result["experiment_id"]
    log.info("Created experiment '%s' (id=%s)", EXPERIMENT_NAME, exp_id)
    return exp_id


def _find_finished_baseline(mlflow_uri: str, experiment_id: str) -> str | None:
    """Return run_id of the latest FINISHED baseline run, or None."""
    result = _mlflow_request(
        "POST",
        mlflow_uri,
        "runs/search",
        {
            "experiment_ids": [experiment_id],
            "filter": f"tags.mlflow.runName = '{RUN_NAME}' AND attributes.status = 'FINISHED'",
            "max_results": 1,
        },
    )
    runs = result.get("runs", [])
    if runs:
        run_id: str = runs[0]["info"]["run_id"]
        return run_id
    return None


def _delete_run(mlflow_uri: str, run_id: str) -> None:
    _mlflow_request("POST", mlflow_uri, "runs/delete", {"run_id": run_id})
    log.info("Deleted run %s", run_id)


def _create_run(mlflow_uri: str, experiment_id: str) -> str:
    result = _mlflow_request(
        "POST",
        mlflow_uri,
        "runs/create",
        {
            "experiment_id": experiment_id,
            "run_name": RUN_NAME,
            "start_time": int(time.time() * 1000),
            "tags": [{"key": "mlflow.runName", "value": RUN_NAME}],
        },
    )
    run_id: str = result["run"]["info"]["run_id"]
    log.info("Created run %s", run_id)
    return run_id


def _log_params(mlflow_uri: str, run_id: str, params: dict[str, str]) -> None:
    _mlflow_request(
        "POST",
        mlflow_uri,
        "runs/log-batch",
        {
            "run_id": run_id,
            "params": [{"key": k, "value": v} for k, v in params.items()],
        },
    )


def _log_metrics(mlflow_uri: str, run_id: str, metrics: dict[str, float]) -> None:
    ts = int(time.time() * 1000)
    _mlflow_request(
        "POST",
        mlflow_uri,
        "runs/log-batch",
        {
            "run_id": run_id,
            "metrics": [
                {"key": k, "value": v, "timestamp": ts, "step": 0}
                for k, v in metrics.items()
            ],
        },
    )


def _finish_run(mlflow_uri: str, run_id: str) -> None:
    _mlflow_request(
        "POST",
        mlflow_uri,
        "runs/update",
        {
            "run_id": run_id,
            "status": "FINISHED",
            "end_time": int(time.time() * 1000),
        },
    )
    log.info("Run %s finished", run_id)


def _fail_run(mlflow_uri: str, run_id: str) -> None:
    try:
        _mlflow_request(
            "POST",
            mlflow_uri,
            "runs/update",
            {"run_id": run_id, "status": "FAILED", "end_time": int(time.time() * 1000)},
        )
    except Exception:
        pass


# ── Dataset upload ────────────────────────────────────────────────────────────


def _upload_dataset(bucket: str, s3_endpoint: str | None) -> None:
    """Upload the fixture JSONL to MinIO/S3 if not already present."""
    kwargs: dict = {"region_name": "us-east-1"}
    if s3_endpoint:
        kwargs["endpoint_url"] = s3_endpoint
    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin"),
        **kwargs,
    )
    try:
        s3.head_object(Bucket=bucket, Key=DATASET_S3_KEY)
        log.info("Dataset already exists at s3://%s/%s", bucket, DATASET_S3_KEY)
        return
    except s3.exceptions.ClientError as exc:
        if exc.response["Error"]["Code"] != "404":
            raise
    # Ensure bucket exists (local MinIO)
    try:
        s3.create_bucket(Bucket=bucket)
    except Exception:
        pass
    s3.upload_file(str(FIXTURE_PATH), bucket, DATASET_S3_KEY)
    log.info("Uploaded dataset to s3://%s/%s", bucket, DATASET_S3_KEY)


# ── Scoring (deterministic, no LLM) ──────────────────────────────────────────


def _exact_match(expected: str, actual: str) -> float:
    return 1.0 if expected.strip() == actual.strip() else 0.0


def _is_non_empty(actual: str) -> float:
    return 1.0 if actual.strip() else 0.0


def _facts_covered(expected_facts: list[str], actual: str) -> float:
    """Fraction of expected facts whose text appears in the actual response (case-insensitive)."""
    if not expected_facts:
        return 1.0
    hits = sum(1 for f in expected_facts if f.strip().lower() in actual.lower())
    return hits / len(expected_facts)


def _get_ground_truth(expectations: dict) -> str:
    """Return the primary ground-truth string from an expectations dict.

    Prefers expected_response; falls back to joining expected_facts.
    """
    if "expected_response" in expectations:
        return str(expectations["expected_response"])
    facts: list = expectations.get("expected_facts", [])
    return " ".join(str(f) for f in facts)


def _evaluate_dataset(fixture_path: Path) -> dict[str, float]:
    """Score each row; model echoes the ground truth (perfect deterministic baseline)."""
    rows = [json.loads(line) for line in fixture_path.read_text().splitlines() if line.strip()]
    exact_scores: list[float] = []
    non_empty_scores: list[float] = []
    facts_scores: list[float] = []
    for row in rows:
        expectations: dict = row["expectations"]
        ground_truth = _get_ground_truth(expectations)
        # Deterministic "model": echo the ground truth.
        actual = ground_truth
        exact_scores.append(_exact_match(ground_truth, actual))
        non_empty_scores.append(_is_non_empty(actual))
        facts_scores.append(_facts_covered(expectations.get("expected_facts", []), actual))
    return {
        "exact_match/mean": sum(exact_scores) / len(exact_scores),
        "is_non_empty/mean": sum(non_empty_scores) / len(non_empty_scores),
        "facts_covered/mean": sum(facts_scores) / len(facts_scores),
        "row_count": float(len(rows)),
    }


# ── RBAC database ─────────────────────────────────────────────────────────────


def _link_experiment_to_team(db_url: str, experiment_id: str, team_name: str) -> None:
    """Insert a team_experiments row for the given team, skipping if exists."""
    # Convert asyncpg URL to psycopg2 format.
    url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(url)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id FROM teams WHERE name = %s", (team_name,))
            row = cur.fetchone()
            if row is None:
                log.warning("Team '%s' not found in RBAC DB — skipping link", team_name)
                return
            team_id = row["id"]
            cur.execute(
                """
                INSERT INTO team_experiments (team_id, mlflow_experiment_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (str(team_id), experiment_id),
            )
            if cur.rowcount:
                log.info("Linked experiment %s → team '%s'", experiment_id, team_name)
            else:
                log.info("Experiment %s already linked to team '%s'", experiment_id, team_name)
        conn.commit()
    finally:
        conn.close()


# ── Entry point ───────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Re-create baseline run if exists")
    parser.add_argument("--mlflow-uri", default=os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
    parser.add_argument("--db-url", default=os.environ.get("DATABASE_URL", "postgresql+asyncpg://rbac:changeme@postgres:5432/rbac_db"))
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    mlflow_uri: str = args.mlflow_uri
    db_url: str = args.db_url
    s3_bucket = os.environ.get("S3_BUCKET", "mlflow-artifacts")
    s3_endpoint = os.environ.get("MLFLOW_S3_ENDPOINT_URL")

    log.info("MLflow URI: %s", mlflow_uri)

    exp_id = _get_or_create_experiment(mlflow_uri)

    existing_run = _find_finished_baseline(mlflow_uri, exp_id)
    if existing_run and not args.force:
        log.info("Baseline run %s already exists — nothing to do (use --force to re-create)", existing_run)
        _link_experiment_to_team(db_url, exp_id, "team-alpha")
        sys.exit(0)

    if existing_run and args.force:
        _delete_run(mlflow_uri, existing_run)

    _upload_dataset(s3_bucket, s3_endpoint)

    run_id = _create_run(mlflow_uri, exp_id)
    try:
        metrics = _evaluate_dataset(FIXTURE_PATH)
        _log_params(mlflow_uri, run_id, {"dataset_path": f"s3://{s3_bucket}/{DATASET_S3_KEY}", "scorer": "deterministic"})
        _log_metrics(mlflow_uri, run_id, metrics)
        _finish_run(mlflow_uri, run_id)
        log.info("Metrics: %s", {k: round(v, 4) for k, v in metrics.items()})
    except Exception:
        log.exception("Evaluation failed — marking run as FAILED")
        _fail_run(mlflow_uri, run_id)
        sys.exit(1)

    _link_experiment_to_team(db_url, exp_id, "team-alpha")
    log.info("Done. GoldenSample experiment seeded successfully.")


if __name__ == "__main__":
    main()
