from __future__ import annotations

import json
from pathlib import Path

from backend.agents.agent2 import adapter


class FakePipeline:
    last_config = None

    def __init__(self, **config):
        type(self).last_config = config

    def run_one(
        self,
        pre_image_path: Path,
        post_image_path: Path,
        sample_id: str,
        output_root: Path,
        max_new_tokens: int,
        overwrite: bool,
    ) -> dict:
        sample_root = output_root / sample_id
        sample_root.mkdir(parents=True)
        (sample_root / "agent2_output.json").write_text(
            json.dumps({"description": "Visible structural and road changes."}),
            encoding="utf-8",
        )
        (sample_root / "raw_response.txt").write_text("raw", encoding="utf-8")
        (sample_root / "prompt_snapshot.txt").write_text("prompt", encoding="utf-8")
        (sample_root / "run_manifest.json").write_text(
            json.dumps({"status": "success"}), encoding="utf-8"
        )
        return {"status": "success", "description": "Visible structural and road changes."}


def _images(tmp_path: Path) -> tuple[Path, Path]:
    pre = tmp_path / "pre.png"
    post = tmp_path / "post.png"
    pre.write_bytes(b"input")
    post.write_bytes(b"input")
    return pre, post


def test_adapter_returns_unverified_json_and_relative_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "_load_pipeline_class", lambda: FakePipeline)
    pre, post = _images(tmp_path)
    result = adapter.run(
        {"sample_id": "case-001", "pre_image": str(pre), "post_image": str(post)},
        str(tmp_path / "job"),
        {"base_model_path": "local/base", "lora_path": "local/lora"},
    )

    assert result["status"] == "succeeded"
    assert result["source_schema_version"] == "1.1"
    assert result["verification_status"] == "unverified"
    assert result["description"] == "Visible structural and road changes."
    assert result["claim_builder_version"] == "sentence-span-v1"
    assert result["claim_list"] == [
        {
            "claim_id": "C001",
            "claim": "Visible structural and road changes.",
            "language": "en",
            "source": "agent2_description_postprocess",
            "source_text_span": {"start": 0, "end": 36},
            "related_evidence_ids": [],
        }
    ]
    assert len(result["artifacts"]) == 4
    assert all(not Path(item["path"]).is_absolute() for item in result["artifacts"])
    json.dumps(result)


def test_explicit_config_precedes_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "_load_pipeline_class", lambda: FakePipeline)
    monkeypatch.setenv("AGENT2_BASE_MODEL_PATH", "environment/base")
    monkeypatch.setenv("AGENT2_LORA_PATH", "environment/lora")
    pre, post = _images(tmp_path)
    adapter.run(
        {"sample_id": "case-002", "pre_image": str(pre), "post_image": str(post)},
        str(tmp_path / "job"),
        {"base_model_path": "explicit/base", "lora_path": "explicit/lora"},
    )

    assert FakePipeline.last_config["base_model_path"] == "explicit/base"
    assert FakePipeline.last_config["lora_path"] == "explicit/lora"


def test_adapter_rejects_path_like_sample_id(tmp_path):
    pre, post = _images(tmp_path)
    try:
        adapter.run(
            {"sample_id": "../escape", "pre_image": str(pre), "post_image": str(post)},
            str(tmp_path / "job"),
            {"base_model_path": "base", "lora_path": "lora"},
        )
    except ValueError as error:
        assert "sample_id" in str(error)
    else:
        raise AssertionError("path-like sample_id was accepted")
