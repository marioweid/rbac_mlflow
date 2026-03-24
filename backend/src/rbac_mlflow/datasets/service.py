import uuid

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rbac_mlflow.datasets.schemas import (
    DatasetCreate,
    DatasetDetail,
    DatasetResponse,
    DatasetSummary,
    DatasetUpdate,
    DatasetVersionInfo,
)
from rbac_mlflow.models import Dataset, DatasetVersion
from rbac_mlflow.rbac.schemas import TeamRole
from rbac_mlflow.s3_client import S3Client


def _s3_key(team_name: str, dataset_name: str, version: int) -> str:
    return f"datasets/{team_name}/{dataset_name}/v{version}/data.jsonl"


async def list_datasets(db: AsyncSession, team_roles: list[TeamRole]) -> list[DatasetSummary]:
    if not team_roles:
        return []

    team_ids = [tr.team_id for tr in team_roles]
    team_name_by_id = {tr.team_id: tr.team_name for tr in team_roles}

    # Subquery: latest version number per dataset
    latest_ver_subq = (
        select(
            DatasetVersion.dataset_id,
            func.max(DatasetVersion.version).label("latest_version"),
        )
        .group_by(DatasetVersion.dataset_id)
        .subquery()
    )

    # Join back to get row_count and created_at for the latest version
    latest_dv_subq = (
        select(
            DatasetVersion.dataset_id,
            DatasetVersion.version,
            DatasetVersion.row_count,
            DatasetVersion.created_at,
        )
        .join(
            latest_ver_subq,
            (DatasetVersion.dataset_id == latest_ver_subq.c.dataset_id)
            & (DatasetVersion.version == latest_ver_subq.c.latest_version),
        )
        .subquery()
    )

    stmt = (
        select(
            Dataset,
            latest_dv_subq.c.version.label("latest_version"),
            latest_dv_subq.c.row_count,
            latest_dv_subq.c.created_at.label("updated_at"),
        )
        .outerjoin(latest_dv_subq, Dataset.id == latest_dv_subq.c.dataset_id)
        .where(Dataset.team_id.in_(team_ids))
        .where(Dataset.is_active.is_(True))
        .order_by(latest_dv_subq.c.created_at.desc().nullslast())
    )

    result = await db.execute(stmt)
    return [
        DatasetSummary(
            id=row.Dataset.id,
            name=row.Dataset.name,
            team_name=team_name_by_id.get(row.Dataset.team_id, ""),
            description=row.Dataset.description,
            latest_version=row.latest_version or 0,
            row_count=row.row_count or 0,
            updated_at=row.updated_at or row.Dataset.created_at,
            is_active=row.Dataset.is_active,
        )
        for row in result.all()
    ]


async def get_dataset_detail(
    db: AsyncSession, s3: S3Client, dataset_id: uuid.UUID, team_name: str
) -> DatasetDetail:
    ds_result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
    ds = ds_result.scalar_one_or_none()
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    ver_result = await db.execute(
        select(DatasetVersion)
        .where(DatasetVersion.dataset_id == dataset_id)
        .order_by(DatasetVersion.version.asc())
    )
    versions = list(ver_result.scalars().all())

    rows: list[dict] = []
    if versions:
        rows = await s3.download_jsonl(versions[-1].s3_key)

    return DatasetDetail(
        id=ds.id,
        name=ds.name,
        team_name=team_name,
        description=ds.description,
        versions=[
            DatasetVersionInfo(
                version=v.version,
                row_count=v.row_count,
                created_by=v.created_by,
                created_at=v.created_at,
            )
            for v in versions
        ],
        rows=rows,
    )


async def get_dataset_version_rows(
    db: AsyncSession, s3: S3Client, dataset_id: uuid.UUID, version: int
) -> list[dict]:
    result = await db.execute(
        select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset_id,
            DatasetVersion.version == version,
        )
    )
    dv = result.scalar_one_or_none()
    if dv is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version} not found for dataset {dataset_id}",
        )
    return await s3.download_jsonl(dv.s3_key)


async def create_dataset(
    db: AsyncSession,
    s3: S3Client,
    team_id: uuid.UUID,
    team_name: str,
    body: DatasetCreate,
    user_sub: str,
) -> DatasetResponse:
    ds = Dataset(
        id=uuid.uuid4(),
        name=body.name,
        team_id=team_id,
        description=body.description,
        created_by=user_sub,
    )
    db.add(ds)
    await db.flush()

    version = 1
    key = _s3_key(team_name, body.name, version)
    await s3.upload_jsonl(key, body.rows)

    db.add(
        DatasetVersion(
            dataset_id=ds.id,
            version=version,
            s3_key=key,
            row_count=len(body.rows),
            created_by=user_sub,
        )
    )
    await db.commit()

    return DatasetResponse(id=ds.id, name=ds.name, version=version, row_count=len(body.rows))


async def update_dataset(
    db: AsyncSession,
    s3: S3Client,
    dataset_id: uuid.UUID,
    team_name: str,
    body: DatasetUpdate,
    user_sub: str,
) -> DatasetResponse:
    ds_result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
    ds = ds_result.scalar_one_or_none()
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    max_ver_result = await db.execute(
        select(func.max(DatasetVersion.version)).where(
            DatasetVersion.dataset_id == dataset_id
        )
    )
    new_version = (max_ver_result.scalar() or 0) + 1

    key = _s3_key(team_name, ds.name, new_version)
    await s3.upload_jsonl(key, body.rows)

    db.add(
        DatasetVersion(
            dataset_id=dataset_id,
            version=new_version,
            s3_key=key,
            row_count=len(body.rows),
            created_by=user_sub,
        )
    )
    await db.commit()

    return DatasetResponse(
        id=dataset_id, name=ds.name, version=new_version, row_count=len(body.rows)
    )


async def soft_delete_dataset(db: AsyncSession, dataset_id: uuid.UUID) -> None:
    await db.execute(
        update(Dataset).where(Dataset.id == dataset_id).values(is_active=False)
    )
    await db.commit()
