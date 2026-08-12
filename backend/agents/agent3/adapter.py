"""Stable Agent3-V5.2.1 entrypoint used by the shared orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .src.claim_verifier import Agent3Verifier
from .src.config import Agent3Config
from .src.build_verified_package import build_verified_package


def _config(overrides: dict[str, Any] | None) -> Agent3Config:
    if not overrides:
        return Agent3Config.from_env()
    values = dict(overrides)
    aliases = {
        "base_model": "base_model_path",
        "lora_path": "adapter_path",
        "adapter": "adapter_path",
    }
    for source, target in aliases.items():
        if source in values and target not in values:
            values[target] = values.pop(source)
    return Agent3Config(**values)


class Agent3Adapter:
    """Lazy, reusable Agent3 verifier for the HTTP service."""

    def __init__(self, config: Agent3Config | None = None) -> None:
        self.config = config or Agent3Config.from_env()
        self._verifier: Agent3Verifier | None = None

    def _get_verifier(self) -> Agent3Verifier:
        if self._verifier is None:
            self._verifier = Agent3Verifier(self.config)
        return self._verifier

    def health(self) -> dict[str, Any]:
        return {
            "agent_code": "agent3",
            "capability": "evidence_verification",
            "source_version": "Agent3-V5.2.1",
            "runtime_schema_version": "3.1-runtime",
            "loaded": self._verifier is not None,
        }

    def verify_claim(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._get_verifier().verify(request)

    def verify_batch(self, requests: list[dict[str, Any]]) -> dict[str, Any]:
        return build_verified_package([self.verify_claim(item) for item in requests])

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "requests" in payload:
            return self.verify_batch(payload["requests"])
        return self.verify_claim(payload)


def run(
    payload: dict[str, Any],
    work_dir: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one native request or a batch without returning local paths."""
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    return Agent3Adapter(_config(config)).handle(payload)
