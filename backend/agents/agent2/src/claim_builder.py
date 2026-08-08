"""Lossless claim extraction for the existing Agent2 description output.

This module deliberately does not call or retrain the Agent2 model. It keeps
the trained model's English paragraph unchanged and adds a deterministic,
backward-compatible ``claim_list`` for the downstream Agent3 contract.
"""

from __future__ import annotations

import re
from typing import Any


CLAIM_BUILDER_VERSION = "sentence-span-v1"
_CLAIM_SPAN_PATTERN = re.compile(r"[^.!?;]+(?:[.!?;]+|$)")
_MAX_CLAIMS = 32


def _normalize_description(description: str) -> str:
    if not isinstance(description, str):
        raise TypeError("Agent2 description must be a string")
    normalized = " ".join(description.split())
    if not normalized:
        raise ValueError("Agent2 description must not be empty")
    return normalized


def build_claim_list(description: str) -> list[dict[str, Any]]:
    """Split a generated paragraph at explicit sentence boundaries.

    The claim text is copied from the normalized description without semantic
    rewriting. Conjunctions are intentionally not split because doing so with
    heuristics can invent or change meaning. A later, separately evaluated
    structured-output model may replace this conservative v1 postprocessor.
    """

    normalized = _normalize_description(description)
    claims: list[dict[str, Any]] = []
    for match in _CLAIM_SPAN_PATTERN.finditer(normalized):
        claim = match.group(0).strip()
        if not claim:
            continue
        claim_id = f"C{len(claims) + 1:03d}"
        leading = len(match.group(0)) - len(match.group(0).lstrip())
        start = match.start() + leading
        claims.append(
            {
                "claim_id": claim_id,
                "claim": claim,
                "language": "en",
                "source": "agent2_description_postprocess",
                "source_text_span": {"start": start, "end": start + len(claim)},
                "related_evidence_ids": [],
            }
        )
        if len(claims) > _MAX_CLAIMS:
            raise ValueError(f"Agent2 description produced more than {_MAX_CLAIMS} claims")

    if not claims:
        raise ValueError("Agent2 description did not contain a usable claim")
    return claims
