"""Shared pipeline metadata.

The integration owner will connect each agent adapter here. Agent contributors
should keep implementation changes inside backend/agents/agentX by default.
"""

PIPELINE_ORDER = (
    ("agent1", "visual_evidence"),
    ("agent2", "change_description"),
    ("agent3", "evidence_verification"),
    ("agent4", "report_generation"),
)
