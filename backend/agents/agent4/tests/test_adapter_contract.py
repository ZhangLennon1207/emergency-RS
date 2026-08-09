from backend.agents.agent4 import adapter as module


class FakeRuntime:
    def generate_report(self, package):
        counts = package.get("summary", {})
        return {
            "schema_version": "agent4_report_v3",
            "report_type": "preliminary_remote_sensing_assessment",
            "task_info": package["task_info"],
            "report_summary": {
                "accepted_count": counts.get("accepted", 0), "revised_count": 0,
                "rejected_count": 0, "pending_count": 0,
            },
            "sections": {
                "executive_summary": {"zh-CN": "摘要", "en-US": "Summary"},
                "key_disaster_indicators": [], "regional_assessment": [],
                "evidence_support_and_consistency_check": [],
                "limitations_and_nonconclusive_items": [],
            },
            "evidence_index": [],
            "review_info": {"report_review_state": "unreviewed", "human_review_required": False},
            "disclaimer": {"zh-CN": "限制。", "en-US": "Limitations."},
        }


def test_run_returns_v3_and_bilingual_markdown(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "_runtime", lambda _config: FakeRuntime())
    result = module.run(
        {"task_info": {"scene_uid": "S1"}, "accepted_claims": [],
         "revised_claims": [], "rejected_claims": [], "pending_claims": [],
         "summary": {"accepted": 0}},
        str(tmp_path),
    )
    assert result["platform_report_json"]["schema_version"] == "agent4_report_v3"
    assert result["markdown_report_zh"]
    assert result["markdown_report_en"]
    assert result["markdown_report"] == result["markdown_report_zh"]
