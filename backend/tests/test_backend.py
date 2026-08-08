from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image

from backend.app.artifacts import build_artifact_index
from backend.app.config import Settings
from backend.app.db import JobStore
from backend.app.main import create_app
from backend.app.orchestration.orchestrator import JobOrchestrator


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        runtime_root=tmp_path / "runtime",
        database_path=tmp_path / "runtime" / "jobs.sqlite3",
        frontend_origins=("http://localhost:5173",),
        agent1_config={"marker": "agent1-explicit-config"},
        agent2_config={"marker": "agent2-explicit-config"},
        queue_poll_seconds=0.01,
    )


def image_bytes(size: tuple[int, int] = (16, 16)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(30, 80, 120)).save(buffer, format="PNG")
    return buffer.getvalue()


def create_store_job(
    settings: Settings, store: JobStore, job_id: str = "test-job"
) -> None:
    job_root = settings.runtime_root / "jobs" / job_id
    inputs = job_root / "inputs"
    inputs.mkdir(parents=True)
    pre = inputs / "pre.png"
    post = inputs / "post.png"
    pre.write_bytes(image_bytes())
    post.write_bytes(image_bytes())
    build_artifact_index(job_root, job_id, {})
    store.create_job(
        job_id=job_id,
        sample_id="sample-001",
        pre_image_path=pre,
        post_image_path=post,
        pre_original_name="pre.png",
        post_original_name="post.png",
    )


def test_create_read_and_input_artifact(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    app = create_app(settings, start_worker=False)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/jobs",
            files={
                "pre_image": ("pre.png", image_bytes(), "image/png"),
                "post_image": ("post.png", image_bytes(), "image/png"),
            },
            data={"sample_id": "web-sample-001"},
        )
        assert response.status_code == 202
        created = response.json()
        assert created["status"] == "queued"
        assert created["sample_id"] == "web-sample-001"

        status = client.get(created["status_url"])
        assert status.status_code == 200
        assert status.json()["job_id"] == created["job_id"]

        artifact = client.get(
            f"/api/v1/jobs/{created['job_id']}/artifacts/input_pre"
        )
        assert artifact.status_code == 200
        assert artifact.headers["content-type"] == "image/png"


def test_rejects_mismatched_dimensions(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), start_worker=False)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/jobs",
            files={
                "pre_image": ("pre.png", image_bytes((16, 16)), "image/png"),
                "post_image": ("post.png", image_bytes((32, 16)), "image/png"),
            },
        )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "IMAGE_SIZE_MISMATCH"


def test_cors_allows_configured_frontend(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), start_worker=False)
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/jobs",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_orchestrator_calls_local_adapters_and_skips_agent34(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings.ensure_runtime()
    store = JobStore(settings.database_path)
    store.initialize()
    create_store_job(settings, store)
    seen_configs: dict[str, dict[str, Any]] = {}
    seen_payloads: dict[str, dict[str, Any]] = {}

    def loader(agent_code: str):
        def fake_adapter(payload, work_dir, config):
            seen_configs[agent_code] = config
            seen_payloads[agent_code] = payload
            root = Path(work_dir)
            if agent_code == "agent1":
                artifact = root / "agent1" / "sample-001" / "fusion" / "fused_overlay.png"
                artifact.parent.mkdir(parents=True)
                artifact.write_bytes(image_bytes())
                return {
                    "status": "succeeded",
                    "source_schema_versions": {
                        "evidence_ledger": "2.1",
                        "report_summary": "1.1",
                        "review_flags": "1.2",
                    },
                    "summary": {
                        "total_buildings": 10,
                        "damaged_buildings": 3,
                        "building_damage_ratio": 0.3,
                        "affected_road_ratio": 0.25,
                        "scene_risk_level": "medium",
                        "review_required": False,
                    },
                    "review_flags": {
                        "schema_version": "1.2",
                        "sample_id": "sample-001",
                        "review_required": False,
                        "review_reasons": [],
                        "routing": {
                            "intended_recipient": "backend_review_display"
                        },
                    },
                    "artifacts": [
                        {
                            "artifact_type": "fused_overlay",
                            "path": "agent1/sample-001/fusion/fused_overlay.png",
                        }
                    ],
                }
            return {
                "status": "succeeded",
                "source_schema_version": "1.1",
                "language": "en",
                "description": "A deterministic change description.",
                "claim_builder_version": "sentence-span-v1",
                "claim_list": [
                    {
                        "claim_id": "C001",
                        "claim": "A deterministic change description.",
                        "language": "en",
                        "related_evidence_ids": [],
                    }
                ],
                "notice": "模型生成的变化描述，尚未经过证据校验。",
                "artifacts": [],
            }

        return fake_adapter

    orchestrator = JobOrchestrator(settings, store, adapter_loader=loader)
    assert orchestrator.process_next_job() is True
    job = store.get_job("test-job")
    assert job is not None
    assert job["status"] == "succeeded"
    assert seen_configs["agent1"]["marker"] == "agent1-explicit-config"
    assert seen_configs["agent2"]["marker"] == "agent2-explicit-config"
    assert "visual_evidence" not in seen_payloads["agent2"]
    assert job["result"]["agent1"]["summary"]["damaged_buildings"] == 3
    assert job["result"]["agent1"]["review_flags"]["review_required"] is False
    assert job["result"]["agent2"]["description"].startswith("A deterministic")
    assert job["result"]["agent2"]["claim_list"][0]["claim_id"] == "C001"
    assert job["result"]["sample_id"] == "sample-001"
    assert job["result"]["agent3"]["status"] == "skipped"
    assert job["result"]["agent4"]["status"] == "skipped"
    assert job["result"]["verification"] is None
    assert job["result"]["report"] is None
    assert job["result"]["four_agent_pipeline_complete"] is False
    assert "agent1_fused_overlay" in job["result"]["artifacts"]


def test_one_local_agent_failure_is_partial_success(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings.ensure_runtime()
    store = JobStore(settings.database_path)
    store.initialize()
    create_store_job(settings, store)

    def loader(agent_code: str):
        if agent_code == "agent1":
            def fail(*_args, **_kwargs):
                raise RuntimeError("simulated Agent1 error")
            return fail

        def succeed(*_args, **_kwargs):
            return {"status": "succeeded", "description": "Agent2 completed.", "artifacts": []}
        return succeed

    orchestrator = JobOrchestrator(settings, store, adapter_loader=loader)
    assert orchestrator.process_next_job() is True
    job = store.get_job("test-job")
    assert job is not None
    assert job["status"] == "partial_success"
    assert job["errors"][0]["agent"] == "agent1"
    assert job["errors"][0]["message"] == "agent1 execution failed"
    assert str(tmp_path) not in str(job["errors"])
    assert job["result"]["agent2"]["status"] == "succeeded"


def test_artifact_path_traversal_is_rejected(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    app = create_app(settings, start_worker=False)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/jobs",
            files={
                "pre_image": ("pre.png", image_bytes(), "image/png"),
                "post_image": ("post.png", image_bytes(), "image/png"),
            },
        )
        job_id = response.json()["job_id"]
        blocked = client.get(f"/api/v1/jobs/{job_id}/artifacts/..%2Fsecret")
    assert blocked.status_code == 404
