"""Click CLI assembled from per-domain command modules."""

from zer0factor.cli import (  # noqa: F401  (imports register commands on the group)
    compute_cmds,
    daily_cmds,
    evaluate_cmds,
    freshness_cmds,
    preprocess_cmds,
    registry_cmds,
    web_cmds,
)
from zer0factor.cli.root import cli

__all__ = ["cli"]
