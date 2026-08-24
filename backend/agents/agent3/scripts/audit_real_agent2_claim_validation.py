"""Post-run audit for the real Agent2 claim validation artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.input_dir.resolve()
    source = json.loads((root / "SOURCE_AUDIT.json").read_text(encoding="utf-8"))
    summaries = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(root.glob("*/summary.json"))
    ]
    checks = {
        "source_claim_count": source["claim_count"],
        "source_mismatches": len(source["source_mismatches"]),
        "validated_count": len(summaries),
        "all_agent2_postprocess_source": all(x["claim_source"] == "agent2_description_postprocess" for x in summaries),
        "all_strict_json": all(x["strict_json"] is True for x in summaries),
        "all_schema_exact": all(x["schema_exact"] is True for x in summaries),
        "no_parse_failure": all(x["parse_failure"] is False for x in summaries),
        "all_second_checks_with_policy": all(
            x["second_pass_auto_built"] is True
            for x in summaries
            if x["final_status"] in {"partially_supported", "exaggerated", "contradicted"}
        ),
        "all_boundary_reviews_true": all(
            x["human_review_required"] is True
            for x in summaries
            if x["final_status"] in {"partially_supported", "exaggerated", "contradicted"}
        ),
        "all_evidence_id_sets_stable": all(
            set(x["first_evidence_ids"]) == set(x["second_evidence_ids"]) == set(x["final_evidence_ids"])
            for x in summaries
            if x["second_evidence_ids"]
        ),
        "localized_crop_count": sum(bool(x["crop_region"]) for x in summaries),
        "safe_fallback_count": sum(bool(x["second_pass_auto_built"] and not x["crop_region"]) for x in summaries),
        "crop_artifact_count": len(list(root.glob("**/second_check/**/*.png"))),
    }
    report = {"run_id": "agent3_real_agent2_claims_20260820", "checks": checks}
    (root / "FINAL_AUDIT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
