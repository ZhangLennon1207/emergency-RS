"""Canonical Agent3/4 cross-computer request contract.

The current repository intentionally does not guess how Agent1's ledger maps
to Wei Songchen's historical ``evidence_list``.  Callers must provide an
already-normalized evidence list; the final mapper will be added after real,
de-identified examples are reviewed.
"""

from __future__ import annotations

import re
from typing import Any


AGENT34_CONTRACT_VERSION = "agent34-http-1.0"
AGENT34_PIPELINE_VERSION = "competition-four-agent-v1"
AGENT3_VERIFY_PATH = "/api/v1/agent3/verify"
AGENT4_REPORT_PATH = "/api/v1/agent4/report"

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class Agent34ContractError(ValueError):
    """Raised when a payload cannot safely cross the Agent3/4 boundary."""


def _identifier(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not _IDENTIFIER_PATTERN.fullmatch(text):
        raise Agent34ContractError(
            f"{name} must contain only letters, digits, dots, underscores, and hyphens"
        )
    return text


def _object_list(name: str, value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise Agent34ContractError(f"{name} must be a non-empty list")
    if not all(isinstance(item, dict) for item in value):
        raise Agent34ContractError(f"every {name} item must be an object")
    return [dict(item) for item in value]


def _version(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise Agent34ContractError(f"{name} must not be empty")
    return text


def _unique_ids(items: list[dict[str, Any]], key: str, label: str) -> set[str]:
    identifiers: list[str] = []
    for item in items:
        identifiers.append(_identifier(key, item.get(key)))
    if len(identifiers) != len(set(identifiers)):
        raise Agent34ContractError(f"{label} identifiers must be unique")
    return set(identifiers)


def build_agent3_verify_payload(
    *,
    job_id: str,
    sample_id: str,
    evidence_list: list[dict[str, Any]],
    claim_list: list[dict[str, Any]],
    evidence_schema_version: str,
    claim_schema_version: str = "1.1",
) -> dict[str, Any]:
    """Validate and build the JSON part of Agent3's multipart request."""

    evidence = _object_list("evidence_list", evidence_list)
    claims = _object_list("claim_list", claim_list)
    evidence_ids = _unique_ids(evidence, "evidence_id", "evidence")
    _unique_ids(claims, "claim_id", "claim")

    for claim in claims:
        text = claim.get("claim")
        if not isinstance(text, str) or not text.strip():
            raise Agent34ContractError("each claim must contain non-empty claim text")
        related = claim.get("related_evidence_ids", [])
        if not isinstance(related, list) or not all(
            isinstance(item, str) for item in related
        ):
            raise Agent34ContractError("related_evidence_ids must be a string list")
        unknown = sorted(set(related) - evidence_ids)
        if unknown:
            raise Agent34ContractError(
                "related_evidence_ids contains unknown identifiers: " + ", ".join(unknown)
            )

    return {
        "contract_version": AGENT34_CONTRACT_VERSION,
        "pipeline_version": AGENT34_PIPELINE_VERSION,
        "job_id": _identifier("job_id", job_id),
        "sample_id": _identifier("sample_id", sample_id),
        "source_schema_versions": {
            "evidence_list": _version(
                "evidence_schema_version", evidence_schema_version
            ),
            "claim_list": _version("claim_schema_version", claim_schema_version),
        },
        "evidence_list": evidence,
        "claim_list": claims,
    }


def build_agent4_report_payload(
    *,
    job_id: str,
    sample_id: str,
    verified_evidence_package: dict[str, Any],
) -> dict[str, Any]:
    """Build Agent4's JSON request without adding unverified Agent1 facts."""

    if not isinstance(verified_evidence_package, dict) or not verified_evidence_package:
        raise Agent34ContractError("verified_evidence_package must be a non-empty object")
    return {
        "contract_version": AGENT34_CONTRACT_VERSION,
        "pipeline_version": AGENT34_PIPELINE_VERSION,
        "job_id": _identifier("job_id", job_id),
        "sample_id": _identifier("sample_id", sample_id),
        "verified_evidence_package": dict(verified_evidence_package),
    }
