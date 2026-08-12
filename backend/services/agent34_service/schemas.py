from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


CLAIM_TYPES = {
    "agricultural_change", "building_damage_level", "building_damage_presence",
    "building_damage_quantity", "disaster_type_inference", "generic_visual_change",
    "other", "road_displacement", "road_impact", "terrain_change",
    "vegetation_change", "water_change",
}


class Claim(BaseModel):
    model_config = ConfigDict(extra="allow")
    claim_id: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    language: str = "en"
    claim_type: str
    related_evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_type(self):
        if self.claim_type not in CLAIM_TYPES:
            raise ValueError(f"unsupported claim_type: {self.claim_type}")
        return self


class Evidence(BaseModel):
    model_config = ConfigDict(extra="allow")
    evidence_id: str = Field(min_length=1)
    source_agent: str = "agent1"
    evidence_type: str = "unknown"
    finding: str = ""
    supporting_statistics: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    confidence_is_calibrated: bool = False
    bbox: list[int] | dict[str, int] | None = None


class VerifyPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    contract_version: str = "agent34-http-1.0"
    pipeline_version: str = "competition-four-agent-v1"
    job_id: str = Field(min_length=1)
    sample_id: str = Field(min_length=1)
    claim_list: list[Claim] = Field(min_length=1)
    evidence_list: list[Evidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self):
        claim_ids = [x.claim_id for x in self.claim_list]
        evidence_ids = [x.evidence_id for x in self.evidence_list]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("duplicate claim_id")
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("duplicate evidence_id")
        known = set(evidence_ids)
        for claim in self.claim_list:
            unknown = sorted(set(claim.related_evidence_ids) - known)
            if unknown:
                raise ValueError(
                    "related_evidence_ids contains unknown identifiers: "
                    + ", ".join(unknown)
                )
        return self


class ReportPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    contract_version: str = "agent34-http-1.0"
    pipeline_version: str = "competition-four-agent-v1"
    job_id: str = Field(min_length=1)
    sample_id: str = Field(min_length=1)
    verified_evidence_package: dict[str, Any]
