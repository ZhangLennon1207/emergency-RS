"""Portable path configuration for Agent1 training and evaluation tools."""

from __future__ import annotations

import os
from pathlib import Path


def workspace_root() -> Path:
    """Return the external training workspace containing ``data/``.

    The default is the current working directory. Set ``AGENT1_WORKSPACE`` to
    keep datasets, checkpoints, and outputs outside the Git repository.
    """

    return Path(os.environ.get("AGENT1_WORKSPACE", Path.cwd())).resolve()
