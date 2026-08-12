import io
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from backend.services.agent34_service.main import create_app
from backend.services.agent34_service.settings import Settings
from backend.services.agent34_service.request_builder import build_requests
from backend.services.agent34_service.schemas import VerifyPayload
from backend.services.agent34_service.settings import Settings


def client(tmp_path):
    settings = Settings("mock", "secret", tmp_path, "", "", "", "")
    return TestClient(create_app(settings))


def png_bytes():
    stream = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(stream, format="PNG")
    return stream.getvalue()


def test_health(tmp_path):
    response = client(tmp_path).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["contract_version"] == "agent34-http-1.0"
    body = response.json()
    assert body["agent3_configured"] is True
    assert body["agent3_loaded"] is False
    assert body["agent3_inference_verified"] is False
    assert "agent3_ready" not in body
    assert body["agent3_display_name"] == "证据约束核验智能体"
    assert body["agent4_display_name"] == "报告生成智能体"


def test_artifact_download_requires_token_and_returns_png(tmp_path):
    target = tmp_path / "artifacts" / "J1" / "S1" / "second_check" / "C1"
    target.mkdir(parents=True)
    target.joinpath("pre_image_crop.png").write_bytes(png_bytes())
    c = client(tmp_path)
    url = "/api/v1/artifacts/J1/S1/second_check/C1/pre_image_crop.png"
    assert c.get(url).status_code == 401
    response = c.get(url, headers={"Authorization": "Bearer secret"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")


def test_health_distinguishes_configured_loaded_and_verified(tmp_path):
    base3 = tmp_path / "base3"; adapter3 = tmp_path / "adapter3"
    base4 = tmp_path / "base4"; adapter4 = tmp_path / "adapter4"
    for path in (base3, adapter3, base4, adapter4):
        path.mkdir()
    settings = Settings("real", "secret", tmp_path / "work",
                        str(base3), str(adapter3), str(base4), str(adapter4))
    body = TestClient(create_app(settings)).get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["agent3_configured"] is True
    assert body["agent3_loaded"] is False
    assert body["agent3_inference_verified"] is False


def test_health_reports_missing_model_paths_as_degraded(tmp_path):
    settings = Settings("real", "secret", tmp_path / "work",
                        str(tmp_path / "missing3"), str(tmp_path / "missing3a"),
                        str(tmp_path / "missing4"), str(tmp_path / "missing4a"))
    body = TestClient(create_app(settings)).get("/api/v1/health").json()
    assert body["status"] == "degraded"
    assert body["agent3_configured"] is False


def test_default_work_root_is_native_absolute(monkeypatch):
    monkeypatch.delenv("AGENT34_WORK_ROOT", raising=False)
    monkeypatch.delenv("AGENT34_REQUEST_ROOT", raising=False)
    settings = Settings.from_env()
    assert settings.request_root.is_absolute()
    if os.name == "nt":
        assert settings.request_root.drive


def test_relative_work_root_is_rejected(monkeypatch):
    monkeypatch.setenv("AGENT34_WORK_ROOT", "relative/agent34")
    try:
        Settings.from_env()
    except RuntimeError as exc:
        assert "absolute path" in str(exc)
    else:
        raise AssertionError("relative AGENT34_WORK_ROOT must be rejected")


def test_auth(tmp_path):
    response = client(tmp_path).post("/api/v1/agent4/report", json={})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_verify_and_report(tmp_path):
    c = client(tmp_path)
    payload = {"job_id": "J1", "sample_id": "S1", "claim_list": [{"claim_id": "C1",
               "claim": "A road is blocked.", "claim_type": "road_impact", "related_evidence_ids": ["R1"]}],
               "evidence_list": [{"evidence_id": "R1", "evidence_type": "road_impact", "bbox": [0, 0, 1, 1]}]}
    image = png_bytes()
    files = {
        "payload": ("payload.json", json.dumps(payload).encode(), "application/json"),
        "pre_image": ("pre.png", io.BytesIO(image), "image/png"),
        "post_image": ("post.png", io.BytesIO(image), "image/png"),
    }
    response = c.post("/api/v1/agent3/verify", headers={"Authorization": "Bearer secret"},
                      files=files)
    assert response.status_code == 200, response.text
    package = response.json()["verified_evidence_package"]
    assert package["schema_version"] == "agent3_verified_package_v1.1"
    assert package["task_info"]["scene_uid"] == "S1"
    assert package["accepted_claims"][0]["atomic_claim"] == "A road is blocked."
    report = c.post("/api/v1/agent4/report", headers={"Authorization": "Bearer secret"}, json={
        "job_id": "J1", "sample_id": "S1", "verified_evidence_package": package})
    assert report.status_code == 200, report.text
    assert "sections" in report.json()["platform_report_json"]
    assert report.json()["source_version"] == "Agent4-V3"
    assert report.json()["markdown_report"] == report.json()["markdown_report_zh"]


def test_verify_rejects_unknown_evidence(tmp_path):
    c = client(tmp_path)
    payload = {
        "job_id": "J1", "sample_id": "S1",
        "claim_list": [{"claim_id": "C1", "claim": "A road is blocked.",
                        "claim_type": "road_impact", "related_evidence_ids": ["missing"]}],
        "evidence_list": [{"evidence_id": "R1"}],
    }
    image = png_bytes()
    response = c.post(
        "/api/v1/agent3/verify",
        headers={"Authorization": "Bearer secret"},
        files={
            "payload": ("payload.json", json.dumps(payload).encode(), "application/json"),
            "pre_image": ("pre.png", image, "image/png"),
            "post_image": ("post.png", image, "image/png"),
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNKNOWN_EVIDENCE_ID"


def test_empty_claim_list_has_specific_error(tmp_path):
    image = png_bytes()
    payload = {"job_id": "J1", "sample_id": "S1", "claim_list": [], "evidence_list": []}
    response = client(tmp_path).post(
        "/api/v1/agent3/verify", headers={"Authorization": "Bearer secret"},
        files={"payload": ("payload.json", json.dumps(payload).encode(), "application/json"),
               "pre_image": ("pre.png", image, "image/png"),
               "post_image": ("post.png", image, "image/png")},
    )
    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "EMPTY_CLAIM_LIST",
        "message": "claim_list must contain at least one claim",
        "retryable": False,
    }


def test_model_not_ready_is_normalized(tmp_path, monkeypatch):
    c = client(tmp_path)
    monkeypatch.setattr(c.app.state.runtime, "agent4", lambda: (_ for _ in ()).throw(FileNotFoundError("private path")))
    response = c.post("/api/v1/agent4/report", headers={"Authorization": "Bearer secret"}, json={
        "job_id": "J1", "sample_id": "S1", "verified_evidence_package": {},
    })
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_NOT_READY"
    assert "private path" not in response.text


def test_model_timeout_is_normalized(tmp_path, monkeypatch):
    c = client(tmp_path)
    class TimeoutRuntime:
        def generate_report(self, _package):
            raise TimeoutError("private prompt text")
    monkeypatch.setattr(c.app.state.runtime, "agent4", lambda: TimeoutRuntime())
    response = c.post("/api/v1/agent4/report", headers={"Authorization": "Bearer secret"}, json={
        "job_id": "J1", "sample_id": "S1", "verified_evidence_package": {},
    })
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "MODEL_TIMEOUT"
    assert response.json()["error"]["retryable"] is True
    assert "private prompt text" not in response.text


def test_internal_error_is_normalized(tmp_path, monkeypatch):
    c = client(tmp_path)
    class BrokenRuntime:
        def generate_report(self, _package):
            raise ValueError("private implementation detail")
    monkeypatch.setattr(c.app.state.runtime, "agent4", lambda: BrokenRuntime())
    response = c.post("/api/v1/agent4/report", headers={"Authorization": "Bearer secret"}, json={
        "job_id": "J1", "sample_id": "S1", "verified_evidence_package": {},
    })
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "private implementation detail" not in response.text


def test_verify_rejects_bad_image(tmp_path):
    c = client(tmp_path)
    payload = {"job_id": "J1", "sample_id": "S1", "claim_list": [{
        "claim_id": "C1", "claim": "A road is blocked.", "claim_type": "road_impact"}],
        "evidence_list": []}
    response = c.post(
        "/api/v1/agent3/verify",
        headers={"Authorization": "Bearer secret"},
        files={
            "payload": ("payload.json", json.dumps(payload).encode(), "application/json"),
            "pre_image": ("pre.png", b"not-an-image", "image/png"),
            "post_image": ("post.png", png_bytes(), "image/png"),
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "IMAGE_DECODE_FAILED"


def test_request_builder_selects_claim_relevant_images(tmp_path):
    assets = {
        key: tmp_path / f"{key}.png"
        for key in (
            "pre_image", "post_image", "damage_map", "fused_overlay",
            "road_status_map", "building_instance_mask",
        )
    }
    payload = VerifyPayload.model_validate({
        "job_id": "J1",
        "sample_id": "S1",
        "claim_list": [
            {"claim_id": "B", "claim": "A building is damaged.",
             "claim_type": "building_damage_presence"},
            {"claim_id": "R", "claim": "A road is blocked.",
             "claim_type": "road_impact"},
        ],
    })
    building, road = build_requests(payload, assets, tmp_path)
    assert "road_status_map" not in building["input"]["image_order"]
    assert "building_instance_mask" not in road["input"]["image_order"]
    assert "damage_map" not in road["input"]["image_order"]
