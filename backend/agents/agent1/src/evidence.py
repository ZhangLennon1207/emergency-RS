"""Helpers for reading Agent1 evidence artifacts without leaking local paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_evidence(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Agent1 evidence JSON must contain an object")
    return payload
