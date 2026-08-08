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


def _evidence():
    return [{"evidence_id": "E001", "evidence_type": "statistics"}]


def _claims():
    return [
        {
            "claim_id": "C001",
            "claim": "Several buildings appear damaged.",
            "related_evidence_ids": [],
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
    pre.write_bytes(b"pre")
    post.write_bytes(b"post")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/agent3/verify"
        assert request.headers["authorization"] == "Bearer private-token"
        assert request.headers["content-type"].startswith("multipart/form-data")
        body = request.read()
        assert b'name="payload"' in body
        assert b'name="pre_image"' in body
        assert b'name="post_image"' in body
        return httpx.Response(200, json={"check_result": {}, "verified_evidence_package": {}})

    client = Agent34Client(
        base_url="http://wei-host:8100",
        shared_token="private-token",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = client.verify(payload={"job_id": "job-001"}, pre_image=pre, post_image=post)
    finally:
        client.close()

    assert "verified_evidence_package" in result


def test_agent4_client_uses_current_path_and_json_body():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/agent4/report"
        assert request.headers["authorization"] == "Bearer private-token"
        body = json.loads(request.content)
        assert body["job_id"] == "job-001"
        return httpx.Response(200, json={"platform_report_json": {}, "markdown_report": ""})

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
