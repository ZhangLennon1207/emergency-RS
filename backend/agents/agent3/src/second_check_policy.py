RISK_STATUSES = {
    "partially_supported",
    "contradicted",
    "exaggerated",
}


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

    if status in RISK_STATUSES:
        reasons.append(
            f"boundary_status:{status}"
        )

    evidence_ids = verification.get(
        "evidence_ids",
        []
    )

    if not evidence_ids:
        reasons.append(
            "missing_evidence_id"
        )

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
