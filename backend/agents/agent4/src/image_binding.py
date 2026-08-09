from pathlib import Path


TYPE_RANK = {
    "pre_post_pair": 0,
    "damage_overlay": 1,
    "damage_crop": 2,
    "road_status": 3,
    "fused_overlay": 4,
}


def bind_images(
    report,
    manifest,
    max_images=4,
):
    referenced = set()

    sections = report.get(
        "sections",
        {}
    )

    for key in [
        "key_disaster_indicators",
        "regional_assessment",
    ]:

        for finding in sections.get(
            key,
            []
        ):

            referenced.update(
                str(x)
                for x in finding.get(
                    "evidence_ids",
                    []
                )
            )

    candidates = []

    for asset in manifest.get(
        "assets",
        []
    ):

        path = Path(
            asset.get(
                "path",
                ""
            )
        )

        if not path.is_file():
            continue

        asset_evidence = {
            str(x)
            for x in asset.get(
                "evidence_ids",
                []
            )
        }

        overlap = (
            referenced
            & asset_evidence
        )

        score = (
            0
            if overlap
            else 100,

            TYPE_RANK.get(
                asset.get(
                    "asset_type",
                    ""
                ),
                99,
            ),

            int(
                asset.get(
                    "priority",
                    999
                )
            ),
        )

        candidates.append(
            (
                score,
                asset
            )
        )

    candidates.sort(
        key=lambda x:
            x[0]
    )

    selected = []
    used_types = set()

    for _, asset in candidates:

        asset_type = asset.get(
            "asset_type"
        )

        if asset_type in used_types:
            continue

        selected.append(
            asset
        )

        used_types.add(
            asset_type
        )

        if len(
            selected
        ) >= max_images:
            break

    evidence_to_assets = {}

    for asset in selected:

        for eid in asset.get(
            "evidence_ids",
            []
        ):

            evidence_to_assets.setdefault(
                str(eid),
                []
            ).append(
                asset.get(
                    "asset_id"
                )
            )

    for key in [
        "key_disaster_indicators",
        "regional_assessment",
    ]:

        for finding in sections.get(
            key,
            []
        ):

            refs = []

            for eid in finding.get(
                "evidence_ids",
                []
            ):

                refs.extend(
                    evidence_to_assets.get(
                        str(eid),
                        []
                    )
                )

            finding[
                "visual_refs"
            ] = sorted(
                set(
                    refs
                )
            )

    report[
        "selected_visual_evidence"
    ] = selected

    return report
