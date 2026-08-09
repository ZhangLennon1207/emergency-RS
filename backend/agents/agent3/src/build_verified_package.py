def build_verified_package(
    verification_results,
):
    accepted = []
    revised = []
    rejected = []
    pending = []
    audit_records = []

    for item in verification_results:

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
        },
    }
