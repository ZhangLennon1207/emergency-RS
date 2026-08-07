"""Verify local Agent1 checkpoint identities and strict architecture loading."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from backend.agents.agent1.src.pipeline import Agent1Pipeline


EXPECTED = {
    "building": (
        "building_unet_medium_best.pth",
        "221f33b2b52a8d3bdcfebf5423aaadfca459ee032a12f8ad734e08a0d8b157b3",
    ),
    "damage": (
        "damage_unet_7ch_best.pth",
        "1347d4d423f474b3b3bc1a05f5be8c01724fab0c7b67055c26e5735560203f8d",
    ),
    "road_binary": (
        "road_unet_best.pth",
        "cca01756d695086bbaba8ff14431ddeb106b5b7ff80bc6fbd2e2e54eba6bfa45",
    ),
    "road_status": (
        "road_status_attresunet7ch_best.pth",
        "69f79447ee7afd68c022c3c635dd6252672f12544df696f5188991d344cb92f3",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint_dir", type=Path)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    paths: dict[str, Path] = {}
    for key, (name, expected_hash) in EXPECTED.items():
        path = args.checkpoint_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"missing {key} checkpoint: {name}")
        actual_hash = sha256(path)
        if actual_hash != expected_hash:
            raise RuntimeError(f"SHA-256 mismatch for {name}: {actual_hash}")
        paths[key] = path

    Agent1Pipeline(device=args.device, model_paths=paths)
    print("Agent1 checkpoint hashes and strict model loading passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
