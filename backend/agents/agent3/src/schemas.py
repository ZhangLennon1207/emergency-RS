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

    return errors
