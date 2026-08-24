def build_verified_package(
    verification_results,
):
    accepted = []
    revised = []
    rejected = []
    pending = []
    audit_records = []

    for item in verification_results:

        human_review_required = bool(
            item.get("human_review_required")
            or item.get("resolution_state") == "model_output_invalid"
        )

        audit_records.append(
            item
        )

        final = item.get(
            "final_check"
        )

        if final is None:
            pending.append({
                "scene_uid":
                    item.get(
                        "scene_uid"
                    ),

                "claim_id":
                    item.get(
                        "claim_id"
                    ),

                "resolution_state":
                    item.get(
                        "resolution_state"
                    ),

                "human_review_required":
                    human_review_required,

                "failure_category":
                    (
                        item.get("audit", {})
                        .get("failure_category")
                    ),
            })

            continue

        status = final.get(
            "support_status"
        )

        record = {
            "scene_uid":
                final.get(
                    "scene_uid"
                ),

            "claim_id":
                final.get(
                    "claim_id"
                ),

            "claim_type":
                final.get(
                    "claim_type"
                ),

            "support_status":
                status,

            "evidence_ids":
                final.get(
                    "evidence_ids",
                    []
                ),

            "reason":
                final.get(
                    "reason",
                    ""
                ),

            "suggested_revision":
                final.get(
                    "suggested_revision",
                    ""
                ),

            "resolution_state":
                item.get("resolution_state"),

            "human_review_required":
                human_review_required,

            "attention_required":
                human_review_required,
        }

        if status == "supported":
            accepted.append(
                record
            )

        elif status in {
            "partially_supported",
            "exaggerated",
        }:
            revised.append(
                record
            )

        elif status in {
            "unsupported",
            "contradicted",
        }:
            rejected.append(
                record
            )

    return {
        "schema_version":
            "agent3_verified_package_v1",

        "accepted_claims":
            accepted,

        "revised_claims":
            revised,

        "rejected_claims":
            rejected,

        "pending_claims":
            pending,

        "audit_records":
            audit_records,

        "summary": {
            "accepted":
                len(accepted),

            "revised":
                len(revised),

            "rejected":
                len(rejected),

            "pending":
                len(pending),

            "human_review_required":
                sum(
                    bool(
                        x.get("human_review_required")
                        or x.get("resolution_state") == "model_output_invalid"
                    )
                    for x in audit_records
                ),

            "model_output_invalid":
                len({
                    (x.get("scene_uid"), x.get("claim_id"))
                    for x in audit_records
                    if x.get("resolution_state") == "model_output_invalid"
                }),

            "model_output_invalid_counting_unit":
                "unique_scene_uid_claim_id",

            "format_repair_attempted":
                sum(bool(x.get("generation_quality", {}).get("format_repair_attempted")) for x in audit_records),

            "semantic_second_check_required":
                sum(bool(x.get("generation_quality", {}).get("semantic_second_check_required")) for x in audit_records),

            "semantic_second_check_executed":
                sum(bool(x.get("generation_quality", {}).get("semantic_second_check_executed")) for x in audit_records),
        },
    }
