import copy


DISCLAIMER_ZH = (
    "本报告为基于现有遥感证据生成的初步研判结果，"
    "不替代现场核查或权威部门最终结论。"
)

DISCLAIMER_EN = (
    "This report is a preliminary assessment based on "
    "the available remote-sensing evidence and does not "
    "replace field verification or authoritative conclusions."
)


def derive_evidence_index(
    sections,
):
    """
    Deterministically derive evidence-to-claim mappings
    from formal findings already generated in sections.

    No new disaster fact is created here.
    """

    mapping = {}

    for key in [
        "key_disaster_indicators",
        "regional_assessment",
    ]:

        findings = sections.get(
            key,
            []
        )

        if not isinstance(
            findings,
            list
        ):
            continue

        for finding in findings:

            if not isinstance(
                finding,
                dict
            ):
                continue

            claim_id = str(
                finding.get(
                    "claim_id",
                    ""
                )
            ).strip()

            evidence_ids = (
                finding.get(
                    "evidence_ids",
                    []
                )
            )

            if not isinstance(
                evidence_ids,
                list
            ):
                continue

            for eid in evidence_ids:

                eid = str(
                    eid
                ).strip()

                if not eid:
                    continue

                if eid not in mapping:
                    mapping[eid] = set()

                if claim_id:
                    mapping[eid].add(
                        claim_id
                    )

    return [
        {
            "evidence_id":
                eid,

            "claim_ids":
                sorted(
                    mapping[eid]
                ),

            "visual_ref":
                "",
        }

        for eid in sorted(
            mapping
        )
    ]


def assemble_report(
    sections,
    source_package,
):
    """
    Assemble the machine-readable complete Agent4 report.

    LLM-generated factual content:
      - sections

    Deterministic runtime metadata:
      - schema_version
      - report_type
      - task_info
      - report_summary
      - evidence_index
      - review_info
      - disclaimer
    """

    if not isinstance(
        sections,
        dict
    ):
        raise TypeError(
            "sections must be a dict"
        )

    sections = copy.deepcopy(
        sections
    )

    accepted = source_package.get(
        "accepted_claims",
        []
    )

    revised = source_package.get(
        "revised_claims",
        []
    )

    rejected = source_package.get(
        "rejected_claims",
        []
    )

    pending = source_package.get(
        "pending_claims",
        []
    )

    scene_uid = (
        source_package
        .get(
            "task_info",
            {}
        )
        .get(
            "scene_uid",
            ""
        )
    )

    return {
        "schema_version":
            "agent4_report_v3",

        "report_type":
            "preliminary_remote_sensing_assessment",

        "task_info": {
            "scene_uid":
                scene_uid
        },

        "report_summary": {
            "accepted_count":
                len(accepted),

            "revised_count":
                len(revised),

            "rejected_count":
                len(rejected),

            "pending_count":
                len(pending),
        },

        "sections":
            sections,

        "evidence_index":
            derive_evidence_index(
                sections
            ),

        "review_info": {
            "report_review_state":
                "unreviewed",

            "human_review_required":
                bool(pending),
        },

        "disclaimer": {
            "zh-CN":
                DISCLAIMER_ZH,

            "en-US":
                DISCLAIMER_EN,
        },
    }
