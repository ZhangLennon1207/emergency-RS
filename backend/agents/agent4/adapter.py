"""Stable Agent4-V3 entrypoint used by the shared orchestrator."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from .src.reusable_adapter import Agent4Adapter as ReusableAgent4Adapter


_LOCK = threading.RLock()
_ADAPTER: ReusableAgent4Adapter | None = None
_IDENTITY: tuple[str, str] | None = None


def _paths(config: dict[str, Any] | None) -> tuple[str, str]:
    values = config or {}
    base = str(values.get("base_model_path") or values.get("base_model") or os.getenv("AGENT4_BASE_MODEL", ""))
    adapter = str(values.get("adapter_path") or values.get("lora_path") or os.getenv("AGENT4_ADAPTER", ""))
    if not base or not adapter:
        raise RuntimeError("Agent4 requires base_model_path and adapter_path")
    return base, adapter


def _runtime(config: dict[str, Any] | None) -> ReusableAgent4Adapter:
    global _ADAPTER, _IDENTITY
    identity = _paths(config)
    with _LOCK:
        if _ADAPTER is None or _IDENTITY != identity:
            if _ADAPTER is not None:
                _ADAPTER.close()
            _ADAPTER = ReusableAgent4Adapter(base_model=identity[0], adapter_path=identity[1])
            _IDENTITY = identity
        return _ADAPTER


def run(
    payload: dict[str, Any],
    work_dir: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate schema-valid V3 JSON and bilingual Markdown."""
    from .src.renderers_separate import render_markdown_language
    from .src.validate_report import validate_report
    package = payload.get("verified_evidence_package", payload)
    if not isinstance(package, dict):
        raise TypeError("verified_evidence_package must be an object")
    output = Path(work_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = _runtime(config).generate_report(package)
    schema = Path(__file__).resolve().parent / "src" / "platform_report_schema_v3.json"
    errors = validate_report(report, schema)
    if errors:
        raise RuntimeError("Agent4 report failed schema validation: " + "; ".join(errors))
    zh_path = output / "report_zh.md"
    en_path = output / "report_en.md"
    render_markdown_language(report, [], zh_path, "zh-CN")
    render_markdown_language(report, [], en_path, "en-US")
    markdown_zh = zh_path.read_text(encoding="utf-8")
    markdown_en = en_path.read_text(encoding="utf-8")
    return {
        "platform_report_json": report,
        "markdown_report_zh": markdown_zh,
        "markdown_report_en": markdown_en,
        "markdown_report": markdown_zh,
    }
