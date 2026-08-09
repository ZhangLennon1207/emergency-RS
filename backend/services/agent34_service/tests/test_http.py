import io
import json

from fastapi.testclient import TestClient
from PIL import Image

from backend.services.agent34_service.main import create_app
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
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


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
