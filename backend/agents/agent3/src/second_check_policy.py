CONFLICT_STATUSES = {
    "contradicted",
    "exaggerated",
}

LOW_CONFIDENCE_BOUND = 0.45
UNCERTAINTY_UPPER_BOUND = 0.70


def _recommended_inputs(
    evidence_ids,
):
    evidence_ids = [
        str(x)
        for x in evidence_ids
    ]

    if any(
        x.startswith("B")
        for x in evidence_ids
    ):
        return [
            "pre_crop",
            "post_crop",
            "target_mask_crop",
            "damage_map_crop",
            "fused_overlay_crop",
        ]

    if any(
        x.startswith("R")
        for x in evidence_ids
    ):
        return [
            "pre_crop",
            "post_crop",
            "road_status_map_crop",
            "fused_overlay_crop",
        ]

    return [
        "pre_image",
        "post_image",
        "fused_overlay",
        "damage_map",
        "road_status_map",
    ]


def decide_second_check(
    verification,
    *,
    evidence_context=None,
):
    reasons = []

    model_second = verification.get(
        "second_check",
        {}
    )

    if model_second.get(
        "required"
    ):
        reasons.append(
            "model_requested_second_check"
        )

    status = verification.get(
        "support_status"
    )

    if status in CONFLICT_STATUSES:
        reasons.append(
            f"boundary_status:{status}"
        )

    # partially_supported is not, by itself, a reason to rerun the model.
    # It triggers only when the model explicitly requests it, evidence IDs
    # are absent, or calibrated evidence falls in a low/uncertain interval.

    evidence_ids = verification.get(
        "evidence_ids",
        []
    )

    if not evidence_ids:
        reasons.append(
            "missing_evidence_id"
        )

    confidences = []
    for item in evidence_context or []:
        if not isinstance(item, dict) or item.get("confidence") is None:
            continue
        try:
            value = float(item["confidence"])
        except (TypeError, ValueError):
            continue
        if 0.0 <= value <= 1.0:
            confidences.append(value)

    if confidences:
        minimum = min(confidences)
        if minimum < LOW_CONFIDENCE_BOUND:
            reasons.append("low_evidence_confidence")
        elif minimum <= UNCERTAINTY_UPPER_BOUND:
            reasons.append("evidence_confidence_uncertainty_interval")

    reasons = sorted(
        set(reasons)
    )

    return {
        "required":
            bool(reasons),

        "trigger_reasons":
            reasons,

        "recommended_inputs":
            _recommended_inputs(
                evidence_ids
            ),

        "recommended_next_step":
            (
                "run_localized_second_check"
                if reasons
                else "finalize_first_check"
            ),
    }
