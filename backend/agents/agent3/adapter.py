"""Stable Agent3 entrypoint used by the shared orchestrator."""

from typing import Any


def run(payload: dict[str, Any], work_dir: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run Agent3 and return check_result plus verified_evidence_package."""
    raise NotImplementedError("Agent3成员需要在本文件中接入实际校验代码")
