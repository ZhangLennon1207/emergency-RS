SUPPORT_STATUSES = {
    "supported",
    "partially_supported",
    "unsupported",
    "contradicted",
    "exaggerated",
}


TOP_LEVEL_KEYS = {
    "schema_version",
    "scene_uid",
    "claim_id",
    "claim_type",
    "support_status",
    "evidence_ids",
    "reason",
    "suggested_revision",
    "second_check",
    "human_review_state",
}


SECOND_CHECK_KEYS = {
    "required",
    "trigger_reasons",
    "recommended_inputs",
    "recommended_next_step",
}


class Agent3ContractError(ValueError):
    pass


def validate_verification(check):
    errors = []

    if not isinstance(check, dict):
        return [
            "verification result must be a JSON object"
        ]

    status = check.get(
        "support_status"
    )

    if status not in SUPPORT_STATUSES:
        errors.append(
            f"invalid support_status: {status!r}"
        )

    if check.get("schema_version") != "3.1":
        errors.append("schema_version must be '3.1'")

    if not isinstance(check.get("reason"), str):
        errors.append("reason must be a string")

    if not isinstance(check.get("suggested_revision"), str):
        errors.append("suggested_revision must be a string")

    if check.get("human_review_state") not in {
        "unreviewed", "reviewed_accepted", "reviewed_revised", "reviewed_rejected"
    }:
        errors.append("invalid human_review_state")

    evidence_ids = check.get(
        "evidence_ids"
    )

    if not isinstance(
        evidence_ids,
        list
    ):
        errors.append(
            "evidence_ids must be a list"
        )

    if not str(
        check.get(
            "scene_uid",
            ""
        )
    ).strip():
        errors.append(
            "scene_uid is missing"
        )

    if not str(
        check.get(
            "claim_id",
            ""
        )
    ).strip():
        errors.append(
            "claim_id is missing"
        )

    if not str(
        check.get(
            "claim_type",
            ""
        )
    ).strip():
        errors.append(
            "claim_type is missing"
        )

    second = check.get(
        "second_check"
    )

    if not isinstance(
        second,
        dict
    ):
        errors.append(
            "second_check must be an object"
        )
    else:
        if not isinstance(second.get("required"), bool):
            errors.append("second_check.required must be boolean")
        for key in ("trigger_reasons", "recommended_inputs"):
            if not isinstance(second.get(key), list):
                errors.append(f"second_check.{key} must be a list")
        if not isinstance(second.get("recommended_next_step"), str):
            errors.append("second_check.recommended_next_step must be a string")

    return errors
