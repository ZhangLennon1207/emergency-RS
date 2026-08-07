"""Declared target pipeline and the currently active integration scope."""

PIPELINE_ORDER = (
    ("agent1", "visual_evidence"),
    ("agent2", "change_description"),
    ("agent3", "evidence_verification"),
    ("agent4", "report_generation"),
)

# Only these adapters are invoked by the current backend. Agent3/4 remain in
# PIPELINE_ORDER as the target contract, but no completed implementation is
# claimed until their real adapters or services are delivered and validated.
ACTIVE_PIPELINE_ORDER = PIPELINE_ORDER[:2]
