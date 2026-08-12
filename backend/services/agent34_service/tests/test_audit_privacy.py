import json

from backend.services.agent34_service.audit_privacy import persist_private_outputs, public_copy, public_package


def test_raw_outputs_are_recursive_private_and_public_summary_is_safe(tmp_path):
    package = {
        "audit_records": [{
            "claim_id": "C1",
            "resolution_state": "model_output_invalid",
            "audit": {
                "failure_category": "format_contract",
                "raw_first_output": "secret first model output",
                "format_retry": {"raw_first_output": "secret retry context"},
                "raw_retry_output": "secret retry output",
            },
        }],
    }
    count = persist_private_outputs(tmp_path, job_id="J1", sample_id="S1", payload=package)
    public = public_copy(package)
    serialized = json.dumps(public)
    assert count == 3
    assert "raw_first_output" not in serialized
    assert "raw_retry_output" not in serialized
    assert "secret" not in serialized
    assert public["audit_records"][0]["audit"]["failure_category"] == "format_contract"
    private_file = tmp_path / "private_model_audit" / "agent3_raw_outputs.jsonl"
    private_text = private_file.read_text(encoding="utf-8")
    assert "secret first model output" in private_text
    assert "secret retry output" in private_text


def test_public_copy_does_not_mutate_private_source():
    source = {"audit": {"raw_model_output": "secret", "crop_region": [1, 2, 3, 4]}}
    public = public_copy(source)
    assert source["audit"]["raw_model_output"] == "secret"
    assert public == {"audit": {"crop_region": [1, 2, 3, 4]}}


def test_public_package_reduces_audit_record_to_whitelist():
    source = {"audit_records": [{
        "scene_uid": "S1", "claim_id": "C1",
        "first_check": {"reason": "full parsed model output"},
        "crop_check": {"reason": "full crop output"},
        "final_check": {"reason": "full final output"},
        "resolution_state": "finalized", "human_review_required": False,
        "audit": {"trigger_reasons": [], "model_version": "Agent3-V5.2.1"},
        "generation_quality": {"retry_used": False, "parse_failure": False},
    }]}
    public = public_package(source)
    text = json.dumps(public)
    assert "first_check" not in text
    assert "crop_check" not in text
    assert "final_check" not in text
    assert public["audit_records"][0]["claim_id"] == "C1"
    assert public["audit_records"][0]["model_version"] == "Agent3-V5.2.1"
