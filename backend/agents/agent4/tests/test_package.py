import json
from pathlib import Path


def test_manifest():
    root = Path(__file__).resolve().parents[1]

    manifest = json.loads(
        (
            root
            / "manifest.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert manifest["agent_code"] == "agent4"

    assert (
        manifest["capability"]
        == "report_generation"
    )

    assert manifest["source_version"] == "Agent4-V3"
    assert manifest["owner"] == "weimiao828"
