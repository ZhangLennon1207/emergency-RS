"""Frozen Agent3 JSON Schema used by constrained decoding and validation."""

SUPPORT_STATUSES = [
    "supported", "partially_supported", "unsupported", "contradicted", "exaggerated",
]
HUMAN_REVIEW_STATES = [
    "unreviewed", "reviewed_accepted", "reviewed_revised", "reviewed_rejected",
]


def verification_json_schema(*, scene_uid: str, claim_id: str, claim_type: str, evidence_ids: list[str]):
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version", "scene_uid", "claim_id", "claim_type", "support_status",
            "evidence_ids", "reason", "suggested_revision", "second_check", "human_review_state",
        ],
        "properties": {
            "schema_version": {"type": "string", "const": "3.1"},
            "scene_uid": {"type": "string", "const": str(scene_uid)},
            "claim_id": {"type": "string", "const": str(claim_id)},
            "claim_type": {"type": "string", "const": str(claim_type)},
            "support_status": {"type": "string", "enum": SUPPORT_STATUSES},
            "evidence_ids": {"type": "array", "uniqueItems": True, "items": {"type": "string", "enum": list(evidence_ids)}},
            "reason": {"type": "string", "minLength": 1, "maxLength": 1024},
            "suggested_revision": {"type": "string", "maxLength": 1024},
            "second_check": {
                "type": "object", "additionalProperties": False,
                "required": ["required", "trigger_reasons", "recommended_inputs", "recommended_next_step"],
                "properties": {
                    "required": {"type": "boolean"},
                    "trigger_reasons": {"type": "array", "items": {"type": "string", "maxLength": 128}},
                    "recommended_inputs": {"type": "array", "items": {"type": "string", "maxLength": 128}},
                    "recommended_next_step": {"type": "string", "maxLength": 256},
                },
            },
            "human_review_state": {"type": "string", "enum": HUMAN_REVIEW_STATES},
        },
    }
