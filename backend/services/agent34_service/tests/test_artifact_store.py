from pathlib import Path

from PIL import Image

from backend.services.agent34_service.artifact_store import (
    persist_second_check_artifacts, resolve_artifact,
)


def test_second_check_crops_persist_with_safe_manifest(tmp_path):
    work = tmp_path / "request"
    crop_dir = work / "second_pass" / "C1"
    crop_dir.mkdir(parents=True)
    Image.new("RGB", (4, 4), "red").save(crop_dir / "pre_image_crop.png")
    (crop_dir / "not_public.txt").write_text("private", encoding="utf-8")
    root = tmp_path / "artifacts"
    records = persist_second_check_artifacts(work, root, job_id="J1", sample_id="S1")
    assert len(records) == 1
    assert records[0]["claim_id"] == "C1"
    assert records[0]["download_url"].endswith("/second_check/C1/pre_image_crop.png")
    assert "request" not in records[0]["download_url"]
    target = resolve_artifact(root, job_id="J1", sample_id="S1", claim_id="C1", file_name="pre_image_crop.png")
    assert target and target.is_file()


def test_artifact_path_traversal_is_rejected(tmp_path):
    assert resolve_artifact(tmp_path, job_id="J1", sample_id="S1", claim_id="..", file_name="pre_image_crop.png") is None
