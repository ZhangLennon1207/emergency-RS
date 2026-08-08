from __future__ import annotations

import pytest

from backend.agents.agent2.src.claim_builder import build_claim_list


def test_build_claim_list_preserves_sentence_text_and_stable_ids():
    description = (
        "Several buildings in the center appear damaged. "
        "The eastern road may show suspected impact; localized water is visible."
    )

    claims = build_claim_list(description)

    assert [item["claim_id"] for item in claims] == ["C001", "C002", "C003"]
    assert [item["claim"] for item in claims] == [
        "Several buildings in the center appear damaged.",
        "The eastern road may show suspected impact;",
        "localized water is visible.",
    ]
    assert all(item["related_evidence_ids"] == [] for item in claims)


def test_build_claim_list_does_not_split_conjunctions_or_rewrite_meaning():
    claims = build_claim_list("Buildings and roads in the center appear affected.")

    assert len(claims) == 1
    assert claims[0]["claim"] == "Buildings and roads in the center appear affected."


@pytest.mark.parametrize("description", ["", "   ", "\n\t"])
def test_build_claim_list_rejects_empty_descriptions(description):
    with pytest.raises(ValueError):
        build_claim_list(description)
