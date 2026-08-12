"""Generate a deterministic SHA-256 manifest for public Agent34 code assets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs" / "agent34-v521-file-manifest.json"
PREFIXES = (
    Path("backend/agents/agent3"),
    Path("backend/agents/agent4"),
    Path("backend/services/agent34_service"),
)
ALLOWED_SUFFIXES = {".py", ".json", ".md", ".txt", ".example"}


def included(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    return any(rel == prefix or prefix in rel.parents for prefix in PREFIXES) and (
        path.suffix in ALLOWED_SUFFIXES or path.name.endswith(".env.example")
    ) and "__pycache__" not in rel.parts


def main() -> None:
    files = []
    for path in sorted(item for item in ROOT.rglob("*") if item.is_file() and included(item)):
        files.append({
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
        })
    payload = {
        "manifest_version": "agent34-public-source-v5.2.1",
        "agent3_version": "Agent3-V5.2.1",
        "agent4_version": "Agent4-V3",
        "weights_included": False,
        "files": files,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
