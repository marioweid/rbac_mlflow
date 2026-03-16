#!/usr/bin/env bash
# Creates the three databases needed by the stack.
# Runs automatically on first postgres container start via /docker-entrypoint-initdb.d.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE rbac_db;
    CREATE DATABASE mlflow_db;
    CREATE DATABASE keycloak;
EOSQL
