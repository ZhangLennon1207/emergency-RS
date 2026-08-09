from collections import defaultdict, deque

from .assemble_report import (
    assemble_report,
)


def verified_statement(
    claim
):
    for key in [
        "report_text",
        "suggested_revision",
        "atomic_claim",
    ]:

        value = str(
            claim.get(
                key,
                ""
            )
        ).strip()

        if value:
            return value

    return ""


def diverse_select(
    claims,
    limit,
):
    if len(
        claims
    ) <= limit:
        return list(
            claims
        )

    groups = defaultdict(
        deque
    )

    for claim in claims:
        groups[
            str(
                claim.get(
                    "claim_type",
                    "unknown"
                )
            )
        ].append(
            claim
        )

    keys = sorted(
        groups
    )

    selected = []

    while (
        len(selected) < limit
        and any(
            groups[k]
            for k in keys
        )
    ):

        for key in keys:

            if (
                groups[key]
                and len(
                    selected
                ) < limit
            ):

                selected.append(
                    groups[
                        key
                    ].popleft()
                )

    return selected


def section_for_type(
    claim_type
):
    x = str(
        claim_type
    ).lower()

    if (
        "road" in x
        or "agricultural" in x
        or "regional" in x
    ):
        return (
            "regional_assessment"
        )

    return (
        "key_disaster_indicators"
    )


def safe_summary():
    return {
        "zh-CN":
            (
                "本场景已完成初步遥感证据核验。"
                "具体可确认事项及证据依据见后续章节；"
                "本报告不替代现场核查或权威结论。"
            ),

        "en-US":
            (
                "Preliminary remote-sensing evidence verification "
                "has been completed for this scene. "
                "Supported findings and their evidence are provided "
                "in the following sections; this report does not "
                "replace field verification or authoritative conclusions."
            ),
    }


class Agent4Runtime:

    def __init__(
        self,
        runner,
    ):
        self.runner = runner

    def build(
        self,
        package,
    ):
        accepted = package.get(
            "accepted_claims",
            []
        )

        revised = package.get(
            "revised_claims",
            []
        )

        rejected = package.get(
            "rejected_claims",
            []
        )

        pending = package.get(
            "pending_claims",
            []
        )

        formal_source = (
            list(accepted)
            + list(revised)
        )

        formal_source = diverse_select(
            [
                x
                for x in formal_source
                if (
                    verified_statement(x)
                    and x.get(
                        "evidence_ids"
                    )
                )
            ],
            8,
        )

        indicators = []
        regional = []

        runtime_failures = []

        summary_source = []

        for claim in formal_source:

            payload = {
                "claim_id":
                    claim.get(
                        "claim_id"
                    ),

                "claim_type":
                    claim.get(
                        "claim_type"
                    ),

                "support_status":
                    claim.get(
                        "support_status"
                    ),

                "verified_statement":
                    verified_statement(
                        claim
                    ),

                "evidence_ids":
                    claim.get(
                        "evidence_ids",
                        []
                    ),

                "reason":
                    claim.get(
                        "reason",
                        ""
                    ),
            }

            generated = (
                self.runner.generate(
                    "finding_bilingual",
                    payload,
                )
            )

            if not generated[
                "audit"
            ][
                "pass"
            ]:

                runtime_failures.append({
                    "claim_id":
                        claim.get(
                            "claim_id"
                        ),

                    "task":
                        "finding_bilingual",

                    "audit":
                        generated[
                            "audit"
                        ],
                })

                continue

            text = generated[
                "bilingual"
            ]

            finding = {
                "claim_id":
                    str(
                        claim.get(
                            "claim_id",
                            ""
                        )
                    ),

                "claim_type":
                    str(
                        claim.get(
                            "claim_type",
                            ""
                        )
                    ),

                "support_status":
                    claim.get(
                        "support_status"
                    ),

                "evidence_ids":
                    [
                        str(x)
                        for x in claim.get(
                            "evidence_ids",
                            []
                        )
                    ],

                "visual_refs":
                    [],

                "text":
                    text,
            }

            target = section_for_type(
                claim.get(
                    "claim_type"
                )
            )

            if (
                target
                == "regional_assessment"
            ):
                regional.append(
                    finding
                )
            else:
                indicators.append(
                    finding
                )

            summary_source.append(
                payload
            )

        # ----------------------------------------
        # Summary
        # ----------------------------------------

        summary_payload = {
            "scene_uid":
                package.get(
                    "task_info",
                    {}
                ).get(
                    "scene_uid",
                    ""
                ),

            "verified_findings":
                summary_source[:6],

            "report_type":
                (
                    "preliminary_remote_"
                    "sensing_assessment"
                ),
        }

        summary_result = None

        if summary_source:

            summary_result = (
                self.runner.generate(
                    "summary_bilingual",
                    summary_payload,
                )
            )

        if (
            summary_result
            and summary_result[
                "audit"
            ][
                "pass"
            ]
        ):
            summary = (
                summary_result[
                    "bilingual"
                ]
            )

        else:
            summary = safe_summary()

            if summary_result:

                runtime_failures.append({
                    "task":
                        "summary_bilingual",

                    "audit":
                        summary_result[
                            "audit"
                        ],
                })

        # ----------------------------------------
        # Limitations
        # ----------------------------------------

        limitations = []

        limitation_source = (
            [
                (
                    "rejected_claim",
                    x
                )
                for x in rejected
            ]
            +
            [
                (
                    "pending_review",
                    x
                )
                for x in pending
            ]
        )

        for limitation_type, claim in limitation_source[
            :4
        ]:

            payload = {
                "claim_id":
                    claim.get(
                        "claim_id"
                    ),

                "claim_type":
                    claim.get(
                        "claim_type"
                    ),

                "support_status":
                    claim.get(
                        "support_status"
                    ),

                "original_claim":
                    claim.get(
                        "atomic_claim",
                        ""
                    ),

                "reason":
                    claim.get(
                        "reason",
                        ""
                    ),

                "limitation_type":
                    limitation_type,
            }

            result = (
                self.runner.generate(
                    "limitation_bilingual",
                    payload,
                )
            )

            if result[
                "audit"
            ][
                "pass"
            ]:

                text = (
                    result[
                        "bilingual"
                    ]
                )

            else:

                cid = str(
                    claim.get(
                        "claim_id",
                        ""
                    )
                )

                text = {
                    "zh-CN":
                        (
                            f"声明 {cid} 当前不能作为正式灾情结论，"
                            "需结合进一步证据或人工复核。"
                        ),

                    "en-US":
                        (
                            f"Claim {cid} cannot currently be treated "
                            "as a formal disaster finding and requires "
                            "additional evidence or human review."
                        ),
                }

                runtime_failures.append({
                    "claim_id":
                        cid,

                    "task":
                        "limitation_bilingual",

                    "audit":
                        result[
                            "audit"
                        ],
                })

            limitations.append({
                "type":
                    limitation_type,

                "claim_id":
                    str(
                        claim.get(
                            "claim_id",
                            ""
                        )
                    ),

                "text":
                    text,
            })

        # ----------------------------------------
        # Evidence consistency section
        # ----------------------------------------

        evidence_map = {}

        for finding in (
            indicators
            + regional
        ):

            cid = finding[
                "claim_id"
            ]

            for eid in finding[
                "evidence_ids"
            ]:

                evidence_map.setdefault(
                    eid,
                    set()
                )

                evidence_map[
                    eid
                ].add(
                    cid
                )

        evidence_section = [
            {
                "evidence_id":
                    eid,

                "claim_ids":
                    sorted(
                        evidence_map[
                            eid
                        ]
                    ),

                "visual_ref":
                    "",
            }

            for eid in sorted(
                evidence_map
            )
        ]

        sections = {
            "executive_summary":
                summary,

            "key_disaster_indicators":
                indicators,

            "regional_assessment":
                regional,

            "evidence_support_and_consistency_check":
                evidence_section,

            "limitations_and_nonconclusive_items":
                limitations,
        }

        report = assemble_report(
            sections,
            package,
        )

        if runtime_failures:

            report[
                "review_info"
            ][
                "human_review_required"
            ] = True

        report[
            "runtime_audit"
        ] = {
            "generation_failures":
                runtime_failures,

            "generation_failure_count":
                len(
                    runtime_failures
                ),

            "report_generation_state":
                (
                    "human_review_required"
                    if runtime_failures
                    else "completed"
                ),
        }

        return report
