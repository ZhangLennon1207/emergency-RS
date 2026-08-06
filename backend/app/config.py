from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else default.resolve()


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value else default


def _json_object(name: str) -> dict[str, Any]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return value


def _configured_path(value: Any, *, directory: bool = False) -> bool:
    if not value:
        return False
    path = Path(str(value))
    return path.is_dir() if directory else path.is_file()


@dataclass(frozen=True)
class Settings:
    runtime_root: Path
    database_path: Path
    frontend_origins: tuple[str, ...] = ("http://localhost:5173",)
    agent1_config: dict[str, Any] = field(default_factory=dict)
    agent2_config: dict[str, Any] = field(default_factory=dict)
    max_upload_bytes: int = 25 * 1024 * 1024
    max_image_pixels: int = 100_000_000
    queue_poll_seconds: float = 0.5
    contract_version: str = "draft-0.2"
    pipeline_version: str = "agent12-local-adapters-v1"

    @classmethod
    def from_env(cls) -> "Settings":
        runtime_root = _env_path("EMERGENCY_RS_RUNTIME_ROOT", BACKEND_ROOT / "runtime")
        raw_origins = os.environ.get(
            "FRONTEND_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        )
        origins = tuple(item.strip() for item in raw_origins.split(",") if item.strip())

        agent1_config = _json_object("AGENT1_CONFIG_JSON")
        agent1_config.setdefault("device", os.environ.get("AGENT1_DEVICE", "cuda"))
        model_paths = agent1_config.setdefault("model_paths", {})
        if not isinstance(model_paths, dict):
            raise ValueError("AGENT1_CONFIG_JSON.model_paths must be an object")
        for key, env_name in (
            ("building", "AGENT1_BUILDING_MODEL_PATH"),
            ("damage", "AGENT1_DAMAGE_MODEL_PATH"),
            ("road_binary", "AGENT1_ROAD_BINARY_MODEL_PATH"),
            ("road_status", "AGENT1_ROAD_STATUS_MODEL_PATH"),
        ):
            value = os.environ.get(env_name)
            if value and key not in model_paths:
                model_paths[key] = value
        agent2_config = _json_object("AGENT2_CONFIG_JSON")
        for key, env_name in (
            ("base_model_path", "AGENT2_BASE_MODEL_PATH"),
            ("lora_path", "AGENT2_LORA_PATH"),
        ):
            value = os.environ.get(env_name)
            if value and key not in agent2_config:
                agent2_config[key] = value

        return cls(
            runtime_root=runtime_root,
            database_path=runtime_root / "jobs.sqlite3",
            frontend_origins=origins,
            agent1_config=agent1_config,
            agent2_config=agent2_config,
            max_upload_bytes=_env_int("MAX_UPLOAD_BYTES", 25 * 1024 * 1024),
            max_image_pixels=_env_int("MAX_IMAGE_PIXELS", 100_000_000),
            queue_poll_seconds=_env_float("QUEUE_POLL_SECONDS", 0.5),
        )

    def ensure_runtime(self) -> None:
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        (self.runtime_root / "jobs").mkdir(parents=True, exist_ok=True)

    def capability_status(self) -> dict[str, dict[str, Any]]:
        model_paths = self.agent1_config.get("model_paths") or {}
        agent1_ready = isinstance(model_paths, dict) and all(
            _configured_path(model_paths.get(key))
            for key in ("building", "damage", "road_binary", "road_status")
        )
        agent2_ready = _configured_path(
            self.agent2_config.get("base_model_path"), directory=True
        ) and _configured_path(self.agent2_config.get("lora_path"), directory=True)
        return {
            "agent1": {"configured": agent1_ready, "mode": "local_adapter"},
            "agent2": {"configured": agent2_ready, "mode": "local_adapter"},
            "agent3": {"configured": False, "mode": "not_integrated"},
            "agent4": {"configured": False, "mode": "not_integrated"},
        }
