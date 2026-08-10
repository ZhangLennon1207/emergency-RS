"""Declared target pipeline and the currently active integration scope."""

PIPELINE_ORDER = (
    ("agent1", "visual_evidence"),
    ("agent2", "change_description"),
    ("agent3", "evidence_verification"),
    ("agent4", "report_generation"),
)

# Agent3/4 are invoked through the frozen remote-service contract when their
# URL and shared token are configured. Otherwise the orchestrator keeps the
# established Agent1/2 local-only fallback.
ACTIVE_PIPELINE_ORDER = PIPELINE_ORDER
