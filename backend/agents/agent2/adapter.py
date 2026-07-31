"""Stable Agent2 entrypoint used by the shared orchestrator."""

from typing import Any


def run(payload: dict[str, Any], work_dir: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run Agent2 and return a JSON-serializable change description."""
    raise NotImplementedError("Agent2成员需要在本文件中接入实际推理代码")
