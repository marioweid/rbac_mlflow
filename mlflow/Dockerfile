FROM ghcr.io/mlflow/mlflow:v3.10.1

# psycopg2-binary — PostgreSQL backend store
# boto3 — S3/MinIO artifact store
RUN pip install --no-cache-dir psycopg2-binary boto3

EXPOSE 5000

CMD ["mlflow", "server", \
     "--host", "0.0.0.0", \
     "--port", "5000", \
     "--backend-store-uri", "${MLFLOW_BACKEND_STORE_URI}", \
     "--default-artifact-root", "${MLFLOW_ARTIFACT_ROOT}", \
     "--allowed-hosts", "*"]
