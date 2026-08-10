"""Cross-agent integration contracts owned by the total-control backend."""

from .agent34_contract import (
    AGENT34_CONTRACT_VERSION,
    AGENT34_PIPELINE_VERSION,
    build_agent3_verify_payload,
    build_agent4_report_payload,
)
from .agent1_evidence_mapper import EVIDENCE_MAPPER_VERSION, build_evidence_list
from .claim_type_mapper import (
    CLAIM_TYPE_MAPPER_VERSION,
    FROZEN_CLAIM_TYPES,
    add_claim_types,
    infer_claim_type,
)
from .evidence_linker import EVIDENCE_LINKER_VERSION, link_claims_to_evidence

__all__ = [
    "AGENT34_CONTRACT_VERSION",
    "AGENT34_PIPELINE_VERSION",
    "CLAIM_TYPE_MAPPER_VERSION",
    "EVIDENCE_LINKER_VERSION",
    "EVIDENCE_MAPPER_VERSION",
    "FROZEN_CLAIM_TYPES",
    "add_claim_types",
    "build_evidence_list",
    "build_agent3_verify_payload",
    "build_agent4_report_payload",
    "infer_claim_type",
    "link_claims_to_evidence",
]
