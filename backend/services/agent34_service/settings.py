from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    runtime_mode: str
    shared_token: str
    request_root: Path
    agent3_base_model: str
    agent3_adapter: str
    agent4_base_model: str
    agent4_adapter: str

    @classmethod
    def from_env(cls) -> "Settings":
        mode = os.getenv("AGENT34_RUNTIME_MODE", "mock").strip().lower()
        if mode not in {"mock", "real"}:
            raise RuntimeError("AGENT34_RUNTIME_MODE must be mock or real")
        return cls(
            runtime_mode=mode,
            shared_token=os.getenv("AGENT34_SHARED_TOKEN", ""),
            request_root=Path(os.getenv("AGENT34_WORK_ROOT", os.getenv("AGENT34_REQUEST_ROOT", "/tmp/agent34_service"))),
            agent3_base_model=os.getenv("AGENT3_BASE_MODEL", ""),
            agent3_adapter=os.getenv("AGENT3_ADAPTER", ""),
            agent4_base_model=os.getenv("AGENT4_BASE_MODEL", ""),
            agent4_adapter=os.getenv("AGENT4_ADAPTER", ""),
        )
