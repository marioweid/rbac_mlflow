from enum import StrEnum


class Role(StrEnum):
    READER = "reader"
    ENGINEER = "engineer"
    OWNER = "owner"


class Permission(StrEnum):
    EXPERIMENT_READ = "experiment.read"
    RUN_READ = "run.read"
    RUN_START = "run.start"
    DATASET_READ = "dataset.read"
    DATASET_WRITE = "dataset.write"
    TEAM_MANAGE = "team.manage"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.READER: frozenset(
        {
            Permission.EXPERIMENT_READ,
            Permission.RUN_READ,
            Permission.DATASET_READ,
        }
    ),
    Role.ENGINEER: frozenset(
        {
            Permission.EXPERIMENT_READ,
            Permission.RUN_READ,
            Permission.RUN_START,
            Permission.DATASET_READ,
            Permission.DATASET_WRITE,
        }
    ),
    Role.OWNER: frozenset(
        {
            Permission.EXPERIMENT_READ,
            Permission.RUN_READ,
            Permission.RUN_START,
            Permission.DATASET_READ,
            Permission.DATASET_WRITE,
            Permission.TEAM_MANAGE,
        }
    ),
}
