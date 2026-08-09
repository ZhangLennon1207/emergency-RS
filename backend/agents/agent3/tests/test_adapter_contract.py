from backend.agents.agent3.adapter import Agent3Adapter, run
from backend.agents.agent3.src.config import Agent3Config
from backend.agents.agent3.src.verified_package_bridge import enrich_verified_package


def test_adapter_is_lazy_and_run_is_public():
    adapter = Agent3Adapter(Agent3Config(base_model_path="unused", adapter_path="unused"))
    assert adapter.health()["source_version"] == "Agent3-V5.2"
    assert adapter.health()["loaded"] is False
    assert callable(run)


def test_bridge_uses_v11_and_restores_original_claim():
    package = {
        "schema_version": "agent3_verified_package_v1",
        "accepted_claims": [{"claim_id": "C1", "claim_type": "road_impact"}],
        "revised_claims": [], "rejected_claims": [], "pending_claims": [],
    }
    result = enrich_verified_package(
        package,
        sample_id="S1",
        claim_list=[{"claim_id": "C1", "claim": "A road is blocked.", "claim_type": "road_impact"}],
    )
    assert result["schema_version"] == "agent3_verified_package_v1.1"
    assert result["task_info"]["scene_uid"] == "S1"
    assert result["accepted_claims"][0]["atomic_claim"] == "A road is blocked."
