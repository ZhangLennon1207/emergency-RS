# -*- coding: utf-8 -*-
"""Deterministic text utilities shared by the Agent2 ablation scripts."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List


CATEGORY_TERMS = {
    "building": (
        "building", "buildings", "structure", "structures", "roof", "roofs",
        "house", "houses",
    ),
    "road": (
        "road", "roads", "street", "streets", "route", "routes",
        "access", "transport",
    ),
    "water_flood": (
        "water", "flood", "flooding", "floodwater", "submerged", "inundat",
        "river", "waterlogged", "pooling",
    ),
    "vegetation": (
        "vegetation", "forest", "forested", "tree", "trees", "crop", "crops",
        "field", "fields", "greenery",
    ),
    "surface_terrain": (
        "surface", "soil", "terrain", "erosion", "sediment", "debris",
        "landslide", "mudflow", "ground",
    ),
    "disaster_type": (
        "overall", "disaster", "hurricane", "storm", "earthquake", "volcan",
        "tornado", "landslide", "mudflow", "flood",
    ),
}

TEMPORAL_PATTERNS = (
    r"\bcompar(?:e|ed|ing|ison)\b",
    r"\bprevious(?:ly)?\b",
    r"\bformerly\b",
    r"\bno longer\b",
    r"\bremain(?:s|ed|ing)?\b",
    r"\bunchanged\b",
    r"\bnow\b",
    r"\bchange(?:s|d|ing)?\b",
    r"\balter(?:s|ed|ation|ing)?\b",
    r"\bincreas(?:e|ed|ing)\b",
    r"\brise\b",
    r"\brose\b",
    r"\breduc(?:e|ed|tion|ing)\b",
    r"\bdecreas(?:e|ed|ing)\b",
    r"\bloss\b",
    r"\blost\b",
    r"\bdisappear(?:s|ed|ing)?\b",
    r"\bshift(?:s|ed|ing)?\b",
    r"\bdisplac(?:e|ed|ement|ing)\b",
    r"\bdamag(?:e|ed|ing)\b",
    r"\bdestroy(?:ed|ing)?\b",
    r"\bcollaps(?:e|ed|ing)\b",
    r"\btransform(?:ed|ation|ing)?\b",
    r"\bbecome\b",
    r"\bbecame\b",
    r"\bappears? to have\b",
    r"\bseems? to have\b",
)

CLAUSE_SPLIT_RE = re.compile(
    r";+\s*|,\s+(?=(?:but|while|whereas|although|however)\b)",
    flags=re.IGNORECASE,
)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?", flags=re.IGNORECASE)


def split_claims(caption: str) -> List[str]:
    """Split a paragraph into stable sentence/clause-level review units."""
    normalized = " ".join(caption.strip().split())
    if not normalized:
        return []

    claims: List[str] = []
    for sentence in SENTENCE_SPLIT_RE.split(normalized):
        for clause in CLAUSE_SPLIT_RE.split(sentence):
            cleaned = clause.strip(" \t,;")
            if cleaned:
                claims.append(cleaned)
    return claims


def has_temporal_relation(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in TEMPORAL_PATTERNS)


def classify_categories(text: str) -> List[str]:
    lowered = text.lower()
    categories = [
        category
        for category, terms in CATEGORY_TERMS.items()
        if any(term in lowered for term in terms)
    ]
    return categories or ["other"]


def annotate_claims(caption: str) -> List[Dict[str, object]]:
    records: List[Dict[str, object]] = []
    for index, claim in enumerate(split_claims(caption), start=1):
        temporal = has_temporal_relation(claim)
        records.append(
            {
                "claim_index": index,
                "claim_text": claim,
                "categories": classify_categories(claim),
                "is_temporal": temporal,
                "auto_evidence_requirement": (
                    "temporal_pair" if temporal else "post_only"
                ),
            }
        )
    return records


def tokenize(text: str) -> List[str]:
    return TOKEN_RE.findall(text.lower())


def token_jaccard(left: str, right: str) -> float:
    left_tokens = set(tokenize(left))
    right_tokens = set(tokenize(right))
    if not left_tokens and not right_tokens:
        return 1.0
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0


def rouge_l_f1(left: str, right: str) -> float:
    left_tokens = tokenize(left)
    right_tokens = tokenize(right)
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0

    previous = [0] * (len(right_tokens) + 1)
    for left_token in left_tokens:
        current = [0]
        for index, right_token in enumerate(right_tokens, start=1):
            if left_token == right_token:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(current[-1], previous[index]))
        previous = current

    lcs = previous[-1]
    precision = lcs / len(left_tokens)
    recall = lcs / len(right_tokens)
    return (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )


def english_single_paragraph_compliant(text: str) -> bool:
    stripped = text.strip()
    if not stripped or "\n" in stripped or "\r" in stripped:
        return False
    letters = [char for char in stripped if char.isalpha()]
    if not letters:
        return False
    ascii_letters = sum(char.isascii() for char in letters)
    return ascii_letters / len(letters) >= 0.95


def mean(values: Iterable[float]) -> float:
    materialized = list(values)
    return sum(materialized) / len(materialized) if materialized else 0.0
