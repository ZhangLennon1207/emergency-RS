"""Cross-agent integration contracts owned by the total-control backend."""

from .agent34_contract import (
    AGENT34_CONTRACT_VERSION,
    AGENT34_PIPELINE_VERSION,
    build_agent3_verify_payload,
    build_agent4_report_payload,
)

__all__ = [
    "AGENT34_CONTRACT_VERSION",
    "AGENT34_PIPELINE_VERSION",
    "build_agent3_verify_payload",
    "build_agent4_report_payload",
]
