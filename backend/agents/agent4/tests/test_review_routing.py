from backend.agents.agent4.src.assemble_report import assemble_report


def test_format_failure_does_not_become_semantic_human_review():
    report = assemble_report({}, {
        "accepted_claims": [], "revised_claims": [],
        "rejected_claims": [], "pending_claims": [{"claim_id": "C1"}],
        "audit_records": [{
            "claim_id": "C1", "resolution_state": "model_output_invalid",
            "human_review_required": False,
        }],
    })
    assert report["review_info"]["attention_required"] is True
    assert report["review_info"]["invalid_model_output_count"] == 1
    assert report["review_info"]["human_review_required"] is False
    assert report["review_info"]["human_review_claim_count"] == 0
