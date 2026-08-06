from __future__ import annotations

import json
from pathlib import Path

from backend.agents.agent1 import adapter


class FakePipeline:
    def __init__(self, **config):
        self.config = config

    def run_one(
        self,
        pre_image_path: Path,
        post_image_path: Path,
        sample_id: str,
        output_root: Path,
        overwrite: bool,
    ) -> dict:
        sample_root = output_root / sample_id
        (sample_root / "fusion").mkdir(parents=True)
        (sample_root / "for_agent3").mkdir()
        (sample_root / "fusion" / "fused_overlay.png").write_bytes(b"png")
        (sample_root / "for_agent3" / "evidence_ledger_core.json").write_text(
            json.dumps(
                {
                    "input": str(pre_image_path.resolve()),
                    "model_metadata": {
                        "checkpoint": "Z:" + "/private/model.pth"
                    },
                }
            ),
            encoding="utf-8",
        )
        (sample_root / "run_manifest.json").write_text(
            json.dumps({"output": str(sample_root.resolve())}),
            encoding="utf-8",
        )
        return {
            "total_buildings": 2,
            "damaged_buildings": 1,
            "building_damage_ratio": 0.5,
            "affected_road_ratio": 0.25,
            "scene_risk_level": "medium",
            "review_required": True,
        }


def test_adapter_returns_json_and_relative_artifacts(tmp_path, monkeypatch) -> None:
    from backend.agents.agent1.src import pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "Agent1Pipeline", FakePipeline)
    pre = tmp_path / "pre.png"
    post = tmp_path / "post.png"
    pre.write_bytes(b"input")
    post.write_bytes(b"input")

    result = adapter.run(
        {"sample_id": "case-001", "pre_image": str(pre), "post_image": str(post)},
        str(tmp_path / "job"),
        {"model_paths": {}},
    )

    assert result["capability"] == "visual_evidence"
    assert result["summary"]["damaged_buildings"] == 1
    assert all(not Path(item["path"]).is_absolute() for item in result["artifacts"])
    json.dumps(result)

    ledger = json.loads(
        (
            tmp_path
            / "job"
            / "agent1"
            / "case-001"
            / "for_agent3"
            / "evidence_ledger_core.json"
        ).read_text(encoding="utf-8")
    )
    assert ledger["model_metadata"]["checkpoint"] == "model.pth"


def test_explicit_model_path_precedes_environment(tmp_path, monkeypatch) -> None:
    explicit = tmp_path / "explicit.pth"
    monkeypatch.setenv("AGENT1_BUILDING_MODEL_PATH", str(tmp_path / "environment.pth"))
    paths = adapter._model_paths({"model_paths": {"building": str(explicit)}})
    assert paths["building"] == explicit


def test_adapter_rejects_path_like_sample_id(tmp_path) -> None:
    pre = tmp_path / "pre.png"
    post = tmp_path / "post.png"
    pre.write_bytes(b"input")
    post.write_bytes(b"input")
    try:
        adapter.run(
            {"sample_id": "../escape", "pre_image": str(pre), "post_image": str(post)},
            str(tmp_path / "job"),
        )
    except ValueError as error:
        assert "sample_id" in str(error)
    else:
        raise AssertionError("path-like sample_id was accepted")
