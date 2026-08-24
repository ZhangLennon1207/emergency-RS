"""Validate Agent3 with real Agent2-derived claim_list records.

The source records are the preserved Agent2 -> Agent3 integration inputs from
the 20-sample handoff. This script never invents or rewrites claim text: it
audits each claim's source span against agent2_output.json, selects a
deterministic coverage subset, and runs the current Agent3 runtime.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agents.agent3.src.claim_verifier import Agent3Verifier
from backend.agents.agent3.src.config import Agent3Config


def _load_claim_records(handoff: Path, regression: Path) -> tuple[list[dict], dict]:
    records = []
    audit = {"source_files": [], "source_mismatches": [], "claim_count": 0}
    for sample_dir in sorted(regression.iterdir()):
        if not sample_dir.is_dir():
            continue
        integration_path = sample_dir / "agent3_input.json"
        agent2_path = handoff / "agent2_same20_seed20260707" / sample_dir.name / "agent2_output.json"
        if not integration_path.exists() or not agent2_path.exists():
            continue
        integration = json.loads(integration_path.read_text(encoding="utf-8"))
        agent2 = json.loads(agent2_path.read_text(encoding="utf-8"))
        description = agent2.get("description", "")
        audit["source_files"].append({
            "sample_id": sample_dir.name,
            "agent2_output": str(agent2_path),
            "agent3_input": str(integration_path),
            "source_schema_versions": integration.get("source_schema_versions", {}),
        })
        for claim in integration.get("claim_list", []):
            text = str(claim.get("claim", ""))
            span = claim.get("source_text_span") or {}
            start, end = span.get("start"), span.get("end")
            span_text = description[start:end] if isinstance(start, int) and isinstance(end, int) else ""
            if not text or claim.get("source") != "agent2_description_postprocess":
                audit["source_mismatches"].append({"sample_id": sample_dir.name, "claim_id": claim.get("claim_id"), "reason": "invalid_source_or_empty_claim"})
            elif span_text and text not in span_text and span_text not in text:
                audit["source_mismatches"].append({"sample_id": sample_dir.name, "claim_id": claim.get("claim_id"), "reason": "claim_not_consistent_with_agent2_span", "claim": text, "span": span_text})
            records.append({
                "sample_id": sample_dir.name,
                "claim": claim,
                "agent2_description": description,
                "integration": integration,
            })
    audit["claim_count"] = len(records)
    return records, audit


def _coverage_subset(records: list[dict]) -> list[dict]:
    """Select all claim types at least once, then one extra per sample.

    This is a validation subset, not a score estimate. Every selected record
    remains an untouched Agent2 claim object with its original claim_id.
    """
    requested = {
        item.strip()
        for item in __import__("os").environ.get("AGENT3_VALIDATION_IDS", "").split(",")
        if item.strip()
    }
    if requested:
        return [
            record for record in records
            if f"{record['sample_id']}::{record['claim'].get('claim_id')}" in requested
        ]
    selected = []
    seen_types = set()
    seen_samples = set()
    for record in records:
        ctype = record["claim"].get("claim_type")
        if ctype not in seen_types:
            selected.append(record)
            seen_types.add(ctype)
            seen_samples.add(record["sample_id"])
    for record in records:
        if record["sample_id"] not in seen_samples:
            selected.append(record)
            seen_samples.add(record["sample_id"])
    return selected


def _asset_map(agent1: Path) -> dict[str, str]:
    candidates = {
        "pre_image": agent1 / "input/pre_image.png",
        "post_image": agent1 / "input/post_image.png",
        "building_instance_mask": agent1 / "building/building_instance_mask.png",
        "damage_map": agent1 / "building/damage_instance_color.png",
        "road_status_map": agent1 / "road/road_status_color.png",
        "fused_overlay": agent1 / "fusion/fused_overlay.png",
    }
    return {key: str(value) for key, value in candidates.items() if value.is_file()}


def build_request(record: dict, job_dir: Path, handoff: Path) -> tuple[dict, dict]:
    sample_id = record["sample_id"]
    claim = record["claim"]
    agent1 = handoff / "agent1_random20_seed20260707" / sample_id
    ledger = json.loads((agent1 / "for_agent3/evidence_ledger_core.json").read_text(encoding="utf-8"))
    assets = _asset_map(agent1)
    evidence_list = record["integration"].get("evidence_list", [])
    related = set(str(x) for x in claim.get("related_evidence_ids", []))
    selected_evidence = [item for item in evidence_list if str(item.get("evidence_id")) in related]
    if not selected_evidence:
        selected_evidence = evidence_list
    bbox_by_id = {
        str(item["evidence_id"]): item["bbox"]
        for item in evidence_list
        if item.get("bbox")
    }
    # Add Agent1's authoritative road summary when a road evidence item is
    # selected, because some preserved integration records only carry a VIS ID.
    if any(str(x).startswith("R") for x in related):
        road = ledger.get("road_evidence") or {}
        if not any(str(item.get("evidence_id")) == "R0001" for item in selected_evidence):
            selected_evidence.append({
                "evidence_id": "R0001",
                "evidence_type": "road_status",
                "finding": road.get("interpretation_note", "Affected road pixels detected."),
                "confidence": road.get("affected_presence_confidence"),
            })
    image_order = [key for key in ("pre_image", "post_image", "building_instance_mask", "damage_map", "road_status_map", "fused_overlay") if key in assets]
    image_tokens = "\n".join("<image>" for _ in image_order)
    request = {
        "instruction": (
            image_tokens
            + "\nVerify this exact Agent2 atomic claim conservatively against the "
            "supplied Agent1 evidence. Preserve the claim meaning; do not add "
            "facts or replace it with a synthetic extreme claim. Return strict JSON."
        ),
        "input": json.dumps({
            "scene_uid": sample_id,
            "claim_id": claim.get("claim_id"),
            "claim_type": claim.get("claim_type", "other"),
            "atomic_claim": claim.get("claim"),
            "source_agent2_description": record["agent2_description"],
            "source_agent2_claim": claim,
            "structured_evidence": selected_evidence,
            "image_order": image_order,
        }, ensure_ascii=False),
        "images": [assets[key] for key in image_order],
        "second_pass_context": {
            "work_dir": str(job_dir / "second_check"),
            "bbox_by_evidence_id": bbox_by_id,
            "assets": assets,
        },
    }
    return request, {"claim": claim, "assets": assets, "selected_evidence_ids": [x.get("evidence_id") for x in selected_evidence]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff-dir", type=Path, required=True)
    parser.add_argument("--regression-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--image-max-pixels", type=int, default=200704)
    parser.add_argument("--max-new-tokens", type=int, default=384)
    parser.add_argument("--model-version", default="Agent3-semantic-roi-real-agent2-claims")
    args = parser.parse_args()
    handoff = args.handoff_dir.resolve()
    regression = args.regression_dir.resolve()
    output = args.output_dir.resolve()
    records, source_audit = _load_claim_records(handoff, regression)
    if source_audit["source_mismatches"]:
        raise RuntimeError(json.dumps(source_audit, ensure_ascii=False, indent=2))
    selected = _coverage_subset(records)
    output.mkdir(parents=True, exist_ok=True)
    (output / "SOURCE_AUDIT.json").write_text(json.dumps({**source_audit, "selected_count": len(selected), "selected_claim_types": Counter(x["claim"].get("claim_type") for x in selected)}, ensure_ascii=False, indent=2), encoding="utf-8")

    config = Agent3Config(
        base_model_path=str(args.base_model.resolve()),
        adapter_path=str(args.adapter.resolve()),
        image_max_pixels=args.image_max_pixels,
        max_new_tokens=args.max_new_tokens,
        load_in_4bit=True,
        device_map="auto",
        model_version=args.model_version,
    )
    verifier = Agent3Verifier(config=config)
    started = datetime.now(timezone.utc)
    summaries = []
    for index, record in enumerate(selected, start=1):
        job_dir = output / f"{index:03d}_{record['sample_id']}_{record['claim']['claim_id']}"
        job_dir.mkdir(parents=True, exist_ok=True)
        request, metadata = build_request(record, job_dir, handoff)
        (job_dir / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
        result = verifier.verify(request)
        (job_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        first, second, final = result.get("first_check") or {}, result.get("crop_check") or {}, result.get("final_check") or {}
        quality = result.get("generation_quality") or {}
        audit = result.get("audit") or {}
        summary = {
            "index": index,
            "sample_id": record["sample_id"],
            "claim_id": record["claim"].get("claim_id"),
            "claim_type": record["claim"].get("claim_type"),
            "atomic_claim": record["claim"].get("claim"),
            "claim_source": record["claim"].get("source"),
            "first_status": first.get("support_status"),
            "second_status": second.get("support_status"),
            "final_status": final.get("support_status"),
            "resolution_state": result.get("resolution_state"),
            "human_review_required": result.get("human_review_required"),
            "human_review_reasons": audit.get("human_review_reasons", []),
            "second_pass_auto_built": audit.get("second_pass_auto_built"),
            "localization_mode": audit.get("localization_mode"),
            "fallback_reason": audit.get("fallback_reason"),
            "crop_region": audit.get("crop_region"),
            "first_evidence_ids": first.get("evidence_ids", []),
            "second_evidence_ids": second.get("evidence_ids", []),
            "final_evidence_ids": final.get("evidence_ids", []),
            "strict_json": quality.get("first_check_strict_json"),
            "schema_exact": quality.get("first_check_schema_exact"),
            "parse_failure": quality.get("parse_failure"),
            "format_repair_attempted": quality.get("format_repair_attempted", False),
            "structured_decoding_requested": quality.get("structured_decoding_requested", False),
            "second_check_reason_changed": audit.get("second_check_reason_changed", False),
            "source_selected_evidence_ids": metadata["selected_evidence_ids"],
        }
        (job_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        summaries.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    completed = datetime.now(timezone.utc)
    report = {
        "run_id": "agent3_real_agent2_claims_20260820",
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "elapsed_seconds": (completed - started).total_seconds(),
        "source_claim_count": len(records),
        "validated_claim_count": len(summaries),
        "validated_claim_types": dict(Counter(x["claim_type"] for x in summaries)),
        "all_claim_sources_agent2_postprocess": all(x["claim_source"] == "agent2_description_postprocess" for x in summaries),
        "all_contract_valid": all(x["strict_json"] and x["schema_exact"] and not x["parse_failure"] for x in summaries),
        "all_evidence_id_sets_stable": all(
            set(x["first_evidence_ids"]) == set(x["second_evidence_ids"]) == set(x["final_evidence_ids"])
            for x in summaries if x["second_evidence_ids"]
        ),
        "second_pass_count": sum(bool(x["second_pass_auto_built"]) for x in summaries),
        "localized_crop_count": sum(bool(x["crop_region"]) for x in summaries),
        "full_image_fallback_count": sum(
            bool(x["second_pass_auto_built"] and not x["crop_region"])
            for x in summaries
        ),
        "human_review_true_for_boundary_or_invalid": all(
            x["human_review_required"]
            for x in summaries
            if x["final_status"] in {"partially_supported", "exaggerated", "contradicted"}
            or x["resolution_state"] == "model_output_invalid"
        ),
        "summaries": summaries,
    }
    (output / "RUN_SUMMARY.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
