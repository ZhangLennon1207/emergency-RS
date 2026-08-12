from __future__ import annotations

import json

import httpx
import pytest

from backend.app.clients.agent34 import Agent34Client, Agent34ServiceError
from backend.app.integration.agent34_contract import (
    Agent34ContractError,
    build_agent3_verify_payload,
    build_agent4_report_payload,
)
from backend.app.orchestration.orchestrator import _review_summary, _source_version


def _evidence():
    return [{"evidence_id": "E001", "evidence_type": "statistics"}]


def _claims():
    return [
        {
            "claim_id": "C001",
            "claim": "Several buildings appear damaged.",
            "language": "en",
            "claim_type": "building_damage_presence",
            "related_evidence_ids": ["E001"],
        }
    ]


def test_build_agent3_payload_uses_current_identifiers_and_versions():
    payload = build_agent3_verify_payload(
        job_id="job-001",
        sample_id="sample-001",
        evidence_list=_evidence(),
        claim_list=_claims(),
        evidence_schema_version="pending-real-sample-review",
    )

    assert payload["contract_version"] == "agent34-http-1.0"
    assert payload["pipeline_version"] == "competition-four-agent-v1"
    assert payload["job_id"] == "job-001"
    assert payload["sample_id"] == "sample-001"
    assert "task_id" not in payload
    json.dumps(payload)


def test_build_agent3_payload_rejects_unknown_related_evidence_id():
    claims = _claims()
    claims[0]["related_evidence_ids"] = ["E999"]

    with pytest.raises(Agent34ContractError, match="unknown identifiers"):
        build_agent3_verify_payload(
            job_id="job-001",
            sample_id="sample-001",
            evidence_list=_evidence(),
            claim_list=claims,
            evidence_schema_version="1.0",
        )


def test_agent3_client_sends_multipart_images_and_bearer_token(tmp_path):
    pre = tmp_path / "pre.png"
    post = tmp_path / "post.png"
    damage = tmp_path / "damage.png"
    fused = tmp_path / "fused.png"
    road = tmp_path / "road.png"
    buildings = tmp_path / "buildings.png"
    pre.write_bytes(b"pre")
    post.write_bytes(b"post")
    damage.write_bytes(b"damage")
    fused.write_bytes(b"fused")
    road.write_bytes(b"road")
    buildings.write_bytes(b"buildings")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/agent3/verify"
        assert request.headers["authorization"] == "Bearer private-token"
        assert request.headers["content-type"].startswith("multipart/form-data")
        body = request.read()
        assert b'name="payload"' in body
        assert b'filename="payload.json"' not in body
        assert b'name="pre_image"' in body
        assert b'name="post_image"' in body
        assert b'name="damage_map"' in body
        assert b'name="fused_overlay"' in body
        assert b'name="road_status_map"' in body
        assert b'name="building_instance_mask"' in body
        return httpx.Response(
            200,
            json={"verified_evidence_package": {"accepted_claims": []}},
        )

    client = Agent34Client(
        base_url="http://wei-host:8100",
        shared_token="private-token",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = client.verify(
            payload={"job_id": "job-001"},
            pre_image=pre,
            post_image=post,
            damage_map=damage,
            fused_overlay=fused,
            road_status_map=road,
            building_instance_mask=buildings,
        )
    finally:
        client.close()

    assert "verified_evidence_package" in result


def test_agent4_client_uses_current_path_and_json_body():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/agent4/report"
        assert request.headers["authorization"] == "Bearer private-token"
        body = json.loads(request.content)
        assert body["job_id"] == "job-001"
        return httpx.Response(
            200,
            json={
                "platform_report_json": {"schema_version": "agent4_report_v3"},
                "markdown_report_zh": "# 中文报告",
                "markdown_report_en": "# English report",
            },
        )

    payload = build_agent4_report_payload(
        job_id="job-001",
        sample_id="sample-001",
        verified_evidence_package={"accepted_claims": []},
    )
    with Agent34Client(
        base_url="http://wei-host:8100",
        shared_token="private-token",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = client.generate_report(payload=payload)

    assert "platform_report_json" in result


def test_remote_error_is_sanitized():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={"error": {"code": "EMPTY_CLAIM_LIST", "message": "claim_list is empty"}},
        )

    with Agent34Client(
        base_url="http://wei-host:8100",
        shared_token="private-token",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(Agent34ServiceError) as caught:
            client.generate_report(payload={"job_id": "job-001"})

    assert caught.value.code == "EMPTY_CLAIM_LIST"
    assert "private-token" not in str(caught.value)


def test_remote_health_version_is_used_for_agent3_runtime():
    health = {
        "agent3": {"version": "Agent3-V5.2.1"},
        "agent4": {"version": "Agent4-V3"},
    }

    assert _source_version(health, "agent3") == "Agent3-V5.2.1"
    assert _source_version(health, "agent4") == "Agent4-V3"


def test_format_failure_is_not_mislabeled_as_human_review():
    verified_package = {
        "summary": {"accepted": 0, "revised": 0, "rejected": 0, "pending": 2},
        "pending_claims": [
            {
                "claim_id": "C001",
                "resolution_state": "model_output_invalid",
                "human_review_required": False,
                "failure_category": "format_contract",
            },
            {
                "claim_id": "C002",
                "resolution_state": "human_review_required",
                "human_review_required": True,
            },
        ],
    }
    # Agent4-V3 historically turns every pending claim into a report-level
    # human_review_required Boolean. Agent3's detailed state remains authoritative.
    platform_report = {"review_info": {"human_review_required": True}}

    summary = _review_summary(
        agent1_result={},
        agent1_ok=True,
        verified_package=verified_package,
        platform_report=platform_report,
    )

    assert summary["attention_required"] is True
    assert summary["human_review_required"] is True
    assert summary["human_review_claim_count"] == 1
    assert summary["model_output_invalid"] is True
    assert summary["model_output_invalid_count"] == 1
    assert summary["pending_claim_count"] == 2


def test_only_format_failure_requires_attention_not_human_review():
    summary = _review_summary(
        agent1_result={},
        agent1_ok=True,
        verified_package={
            "summary": {"pending": 1},
            "pending_claims": [
                {
                    "claim_id": "C001",
                    "resolution_state": "model_output_invalid",
                    "human_review_required": False,
                    "failure_category": "format_contract",
                }
            ],
        },
        platform_report={"review_info": {"human_review_required": True}},
    )

    assert summary["attention_required"] is True
    assert summary["review_required"] is False
    assert summary["human_review_claim_count"] == 0
    assert summary["model_output_invalid_count"] == 1


def test_explicit_zero_human_review_count_overrides_legacy_boolean():
    summary = _review_summary(
        agent1_result={},
        agent1_ok=True,
        verified_package={"summary": {"pending": 0}, "pending_claims": []},
        platform_report={
            "review_info": {
                "human_review_required": True,
                "human_review_claim_count": 0,
                "model_output_invalid_count": 0,
            }
        },
    )

    assert summary["human_review_required"] is False
    assert summary["attention_required"] is False
