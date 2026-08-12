from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PRIVATE_KEYS = {
    "raw_first_output", "raw_retry_output", "raw_crop_output",
    "raw_second_output", "raw_second_check_output", "raw_model_output",
    "raw_output", "format_retry",
}
_write_lock = threading.Lock()


def public_copy(value: Any) -> Any:
    """Recursively remove private model text from an HTTP-safe copy."""
    if isinstance(value, dict):
        return {key: public_copy(item) for key, item in value.items() if key not in PRIVATE_KEYS}
    if isinstance(value, list):
        return [public_copy(item) for item in value]
    return value


def public_package(value: dict[str, Any]) -> dict[str, Any]:
    """Create the public verified package with audit records reduced to a whitelist."""
    package = public_copy(value)
    summaries = []
    for item in package.get("audit_records", []):
        if not isinstance(item, dict):
            continue
        audit = item.get("audit", {}) if isinstance(item.get("audit"), dict) else {}
        generation = item.get("generation_quality", {})
        summaries.append({
            "scene_uid": item.get("scene_uid"),
            "claim_id": item.get("claim_id"),
            "resolution_state": item.get("resolution_state"),
            "human_review_required": bool(item.get("human_review_required")),
            "failure_category": audit.get("failure_category"),
            "trigger_reasons": audit.get("trigger_reasons", []),
            "recommended_next_step": audit.get("recommended_next_step", ""),
            "crop_region": audit.get("crop_region"),
            "model_version": audit.get("model_version"),
            "retry_used": bool(generation.get("retry_used")) if isinstance(generation, dict) else False,
            "parse_failure": bool(generation.get("parse_failure")) if isinstance(generation, dict) else False,
        })
    package["audit_records"] = summaries
    return package


def _private_fragments(value: Any, path: str = "$") -> list[dict[str, Any]]:
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if key in PRIVATE_KEYS:
                found.append({"path": child, "value": item})
            else:
                found.extend(_private_fragments(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_private_fragments(item, f"{path}[{index}]"))
    return found


def persist_private_outputs(root: Path, *, job_id: str, sample_id: str, payload: Any) -> int:
    fragments = _private_fragments(payload)
    if not fragments:
        return 0
    directory = root / "private_model_audit"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "job_id": job_id,
        "sample_id": sample_id,
        "private_model_outputs": fragments,
    }
    target = directory / "agent3_raw_outputs.jsonl"
    with _write_lock, target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return len(fragments)
