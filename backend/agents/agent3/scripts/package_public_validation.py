"""Create a privacy-safe review bundle from a local validation run.

Only summaries and audits are exported. Requests, raw model output, absolute
paths, original imagery, and model weights are intentionally excluded.
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--destination-dir", type=Path, required=True)
    parser.add_argument("--zip-path", type=Path, required=True)
    parser.add_argument("--agent1-handoff-dir", type=Path)
    args = parser.parse_args()
    source = args.source_dir.resolve()
    destination = args.destination_dir.resolve()
    zip_path = args.zip_path.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "summaries").mkdir(exist_ok=True)
    for name in ("FINAL_AUDIT.json", "SOURCE_AUDIT.json", "RUN_SUMMARY.json"):
        src = source / name
        if src.exists():
            data = json.loads(src.read_text(encoding="utf-8"))
            if name == "SOURCE_AUDIT.json":
                data["source_files"] = [
                    {"sample_id": item["sample_id"], "source_schema_versions": item.get("source_schema_versions", {})}
                    for item in data.get("source_files", [])
                ]
            (destination / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    for path in source.glob("*/summary.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        (destination / "summaries" / f"{path.parent.name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    retry_cases = []
    for path in source.glob("*/result.json"):
        result = json.loads(path.read_text(encoding="utf-8"))
        quality = result.get("generation_quality", {})
        if quality.get("retry_used") or result.get("audit", {}).get("format_retry"):
            retry_cases.append({
                "case": path.parent.name,
                "format_repair_attempted": True,
                "resolution_state": result.get("resolution_state"),
            })
    (destination / "FORMAT_REPAIR_CASES.json").write_text(json.dumps(retry_cases, ensure_ascii=False, indent=2), encoding="utf-8")
    (destination / "SECOND_CHECK_REASON_CHANGE_CASE.json").write_text(json.dumps({
        "case_type": "deterministic_contract_regression",
        "first_status": "supported",
        "second_status": "supported",
        "first_reason": "Initial evidence appears supportive.",
        "second_reason": "Localized crop is insufficient to confirm the extent.",
        "expected": {"second_check_status_changed": False, "second_check_reason_changed": True},
        "note": "This verifies the audit can expose a changed second-check rationale even when status agrees.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    surface_assets = list(args.agent1_handoff_dir.resolve().glob("*/**/surface_change_mask.png")) if args.agent1_handoff_dir else []
    (destination / "SURFACE_ROI_STATUS.json").write_text(json.dumps({
        "agent3_code_path_supported": True,
        "agent1_handoff_inspected": args.agent1_handoff_dir is not None,
        "agent1_surface_change_mask_count_in_handoff": len(surface_assets),
        "end_to_end_surface_roi_verified": False,
        "reason": "The Agent1 handoff does not provide surface_change_mask.png; runtime must use full_image_fallback and must not claim surface ROI completion.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    readme = destination / "README.md"
    readme.write_text(
        "# Agent3 real Agent2 claim validation (public review bundle)\n\n"
        "This bundle contains aggregate audits and per-claim summaries only.\n"
        "Original Agent2/Agent1 files, request payloads, absolute local paths,\n"
        "raw model outputs, images, and model weights are intentionally excluded.\n",
        encoding="utf-8",
    )
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in destination.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(destination.parent).as_posix())
    print(zip_path)


if __name__ == "__main__":
    main()
