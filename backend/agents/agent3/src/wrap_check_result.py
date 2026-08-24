import copy
from datetime import (
    datetime,
    timezone,
)


ALWAYS_REVIEW_STATUSES = {
    "partially_supported",
    "exaggerated",
    # Product policy: a direct contradiction is treated as high risk. A
    # plain unsupported result may still finalize when both checks agree.
    "contradicted",
}

REVIEW_TRIGGER_REASONS = {
    "low_evidence_confidence",
    "evidence_confidence_uncertainty_interval",
    "missing_evidence_id",
}


def _human_review_reasons(
    *,
    policy,
    resolution,
    final_check,
):
    reasons = []

    if resolution == "human_review_required":
        reasons.append("second_check_conflict")

    if resolution == "second_check_required":
        reasons.append("required_second_check_unavailable")

    status = (
        final_check.get("support_status")
        if isinstance(final_check, dict)
        else None
    )
    if status in ALWAYS_REVIEW_STATUSES:
        reasons.append(f"high_risk_status:{status}")

    trigger_reasons = set(policy.get("trigger_reasons", []))
    reasons.extend(sorted(trigger_reasons & REVIEW_TRIGGER_REASONS))

    return sorted(set(reasons))


def _utc_now():
    return (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )


def wrap_check_result(
    first_check,
    policy,
    crop_check=None,
    *,
    model_version="agent3-final",
    crop_region=None,
):
    resolution = (
        "finalized"
    )

    final_check = None

    if not policy[
        "required"
    ]:
        final_check = copy.deepcopy(
            first_check
        )

    elif crop_check is None:
        resolution = (
            "second_check_required"
        )

    elif (
        crop_check.get(
            "support_status"
        )
        ==
        first_check.get(
            "support_status"
        )
    ):
        final_check = copy.deepcopy(
            crop_check
        )

        merged_ids = sorted(
            set(
                first_check.get(
                    "evidence_ids",
                    []
                )
            )
            |
            set(
                crop_check.get(
                    "evidence_ids",
                    []
                )
            )
        )

        final_check[
            "evidence_ids"
        ] = merged_ids

        resolution = (
            "second_check_agreement"
        )

    else:
        resolution = (
            "human_review_required"
        )

    review_reasons = _human_review_reasons(
        policy=policy,
        resolution=resolution,
        final_check=final_check,
    )
    human_review_required = bool(review_reasons)
    first_reason = str(first_check.get("reason", "")).strip()
    second_reason = (
        str(crop_check.get("reason", "")).strip()
        if isinstance(crop_check, dict)
        else None
    )
    first_status = first_check.get("support_status")
    second_status = crop_check.get("support_status") if isinstance(crop_check, dict) else None

    return {
        "runtime_schema_version":
            "3.1-runtime",

        "scene_uid":
            first_check.get(
                "scene_uid"
            ),

        "claim_id":
            first_check.get(
                "claim_id"
            ),

        "first_check":
            first_check,

        "crop_check":
            crop_check,

        "final_check":
            final_check,

        "resolution_state":
            resolution,

        "human_review_required":
            human_review_required,

        "audit": {
            "trigger_reasons":
                policy[
                    "trigger_reasons"
                ],

            "recommended_inputs":
                policy[
                    "recommended_inputs"
                ],

            "recommended_next_step":
                policy[
                    "recommended_next_step"
                ],

            "crop_region":
                crop_region,

            "model_version":
                model_version,

            "human_review_reasons":
                review_reasons,

            "first_status": first_status,
            "second_status": second_status,
            "second_check_status_changed": (
                second_status is not None and second_status != first_status
            ),
            "second_check_reason_changed": (
                second_reason is not None and second_reason != first_reason
            ),

            "created_at":
                _utc_now(),
        },
    }
