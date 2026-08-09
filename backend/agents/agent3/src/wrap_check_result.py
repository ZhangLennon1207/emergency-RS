import copy
from datetime import (
    datetime,
    timezone,
)


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

    human_review_required = False

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

        human_review_required = True

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

            "created_at":
                _utc_now(),
        },
    }
