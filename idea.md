# MLflow RBAC Platform

## Problem

Our team uses MLflow to run and evaluate a RAG service. The evaluation results
(experiments, runs, metrics, traces) are useful for end users and stakeholders
who want visibility into quality over time. However, MLflow has no access
control: giving any user access means they can see every other team's
experiments, datasets, and runs.

We need a thin UI layer that:

1. Shows users only the experiments, runs, and datasets that belong to their
   team.
2. Lets our internal team (engineers and owners) manage and edit evaluation
   datasets directly — a feature MLflow does not provide.
3. Allows triggering evaluation runs from the UI.

---

## Scope

### In scope

- Role-based access control scoped per team/experiment group.
- Read-only dashboard for stakeholders (metrics, charts, run comparisons).
- Dataset management for internal roles: view, create, edit, delete evaluation
  datasets stored in the artifact store (MinIO/S3).
- Trigger evaluation runs against a selected dataset.
- Authentication via OIDC/OAuth2. Groups in the JWT token drive team
  membership and role assignment.
- Local development with Keycloak; production with a custom IAM (swappable via
  config).

### Out of scope

- Direct MLflow UI access for end users (we proxy everything through this app).
- Model promotion, approval workflows, or policy engines (future).
- Dataset lineage tracking (future).

---

## Audiences

| Audience | Who | Typical action |
|---|---|---|
| Reader | End users / stakeholders | View experiment metrics and run results for their team |
| Engineer | Internal team member | All reader actions + edit datasets + trigger runs |
| Owner | Team lead / admin | All engineer actions + manage team membership |

---

## RBAC Design

### Roles

| Role | Inherits |
|---|---|
| `reader` | — |
| `engineer` | `reader` |
| `owner` | `engineer` |

### Permissions

| Permission | Description |
|---|---|
| `experiment.read` | View experiments and their metadata |
| `run.read` | View runs, metrics, artifacts, traces |
| `run.start` | Trigger a new evaluation run |
| `dataset.read` | View dataset contents |
| `dataset.write` | Create, edit, or delete datasets |
| `team.manage` | Add or remove users from a team (via group mapping) |

### Role → Permission matrix

| Permission | Reader | Engineer | Owner |
|---|---|---|---|
| `experiment.read` | yes | yes | yes |
| `run.read` | yes | yes | yes |
| `run.start` | no | yes | yes |
| `dataset.read` | yes | yes | yes |
| `dataset.write` | no | yes | yes |
| `team.manage` | no | no | yes |

### Scoping rule

All permissions are scoped to a **team**. A user can have different roles in
different teams. A user with no team assignment sees an empty dashboard.

---

## Auth Strategy

JWT tokens issued by Keycloak (local) or the custom IAM (production) contain a
`groups` claim, for example:

```json
{ "groups": ["rag-service-owner", "vision-model-reader"] }
```

The API maps group names to `(team, role)` pairs using a database table managed
by owners. This avoids coupling the app to group naming conventions in the
upstream IAM.

The auth provider (Keycloak vs. custom IAM) is selected via an environment
variable (`AUTH_PROVIDER=keycloak|iam`) so the same codebase runs in both
environments.

---

## Dataset Editing

MLflow datasets are immutable references with a content hash. To support
editing evaluation datasets in the UI, the app will:

1. Read the dataset file directly from the artifact store (MinIO/S3).
2. Present the content in an editable table (JSONL rows: question, expected
   answer, context, etc.).
3. On save, write a new file to the artifact store and register a new MLflow
   dataset entry pointing to it, incrementing the version.

This is only available to `engineer` and `owner` roles.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js (App Router) |
| API | FastAPI (Python) |
| Auth (local) | Keycloak |
| Auth (prod) | Custom IAM |
| RBAC data | PostgreSQL via SQLModel |
| Reverse proxy | Traefik |
| MLflow tracking | MLflow |
| Artifact store | MinIO (local) / S3 (prod) |
| DB | PostgreSQL |

---

## Future Features

- Dataset lineage (track which dataset version was used in which run).
- Experiment approval workflow.
- Model promotion pipeline.
- Policy engine (OPA) for fine-grained rules.
