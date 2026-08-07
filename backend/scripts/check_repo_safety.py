"""Reject tracked secrets, local paths, model assets, and oversized files."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MAX_TRACKED_BYTES = 20 * 1024 * 1024
FORBIDDEN_SUFFIXES = {
    ".bin",
    ".ckpt",
    ".gguf",
    ".h5",
    ".hdf5",
    ".joblib",
    ".npy",
    ".npz",
    ".onnx",
    ".pb",
    ".pkl",
    ".pt",
    ".pth",
    ".safetensors",
    ".tif",
    ".tiff",
}
FORBIDDEN_PARTS = {
    ".cache",
    ".venv",
    "checkpoints",
    "datasets",
    "model_offload",
    "models",
    "outputs",
    "runtime",
    "runs",
    "venv",
    "wandb",
}
GLOBAL_FORBIDDEN_BACKEND_PARTS = {
    ".cache",
    ".venv",
    "checkpoints",
    "model_offload",
    "outputs",
    "runtime",
    "runs",
    "venv",
    "wandb",
}
TEXT_SUFFIXES = {".env", ".json", ".ps1", ".py", ".toml", ".yaml", ".yml"}
WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)(?:^|[\"'])\s*[a-z]:[\\/]")
UNIX_HOME_PATH = re.compile(r"(?:^|[\"'])\s*/(?:home|Users)/[^/\s]+/")
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*[\"'](?!"
    r"(?:change-me|example|placeholder|your-|\$\{|<))[^\"']{8,}[\"']"
)


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return sorted({
        REPO_ROOT / item.decode("utf-8")
        for item in result.stdout.split(b"\0")
        if item
    })


def main() -> int:
    violations: list[str] = []
    for path in tracked_files():
        relative = path.relative_to(REPO_ROOT)
        # ``git ls-files --cached`` still reports tracked files deleted in the
        # working tree. Deletions contain no content to scan and must not make
        # the pre-commit safety check crash.
        if not path.is_file():
            continue
        lowered_parts = {part.lower() for part in relative.parts}

        if path.stat().st_size > MAX_TRACKED_BYTES:
            violations.append(f"oversized tracked file: {relative}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            violations.append(f"forbidden tracked extension: {relative}")
        is_agent_path = "backend" in lowered_parts and "agents" in lowered_parts
        matched_parts = lowered_parts & (
            FORBIDDEN_PARTS if is_agent_path else GLOBAL_FORBIDDEN_BACKEND_PARTS
        )
        if path.suffix.lower() == ".py" and "src" in lowered_parts:
            matched_parts.discard("models")
        forbidden_directory = bool(matched_parts)
        if "backend" in lowered_parts and forbidden_directory:
            violations.append(f"forbidden backend asset directory: {relative}")

        should_scan = path.suffix.lower() in TEXT_SUFFIXES or path.name.startswith(".env")
        if not should_scan:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            violations.append(f"non-UTF-8 configuration/source file: {relative}")
            continue
        if WINDOWS_ABSOLUTE_PATH.search(text) or UNIX_HOME_PATH.search(text):
            violations.append(f"personal absolute path in source/config: {relative}")
        if SECRET_ASSIGNMENT.search(text):
            violations.append(f"possible embedded secret: {relative}")

    if violations:
        print("Repository safety check failed:", file=sys.stderr)
        for violation in sorted(set(violations)):
            print(f"- {violation}", file=sys.stderr)
        return 1

    print("Repository safety check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
