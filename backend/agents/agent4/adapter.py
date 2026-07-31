"""Stable Agent4 entrypoint used by the shared orchestrator."""

from typing import Any


def run(payload: dict[str, Any], work_dir: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run Agent4 and return platform_report_json plus markdown_report."""
    raise NotImplementedError("Agent4成员需要在本文件中接入实际报告代码")
