# -*- coding: utf-8 -*-
"""Run the paired/post-only/mismatched-pre Agent2 ablation experiment."""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import importlib
import json
import os
import random
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

import torch

from backend.agents.agent2.experiments.ablation_utils import annotate_claims


AGENT2_ROOT = Path(__file__).resolve().parents[1]
EBD_ROOT = Path(os.environ.get("AGENT2_EBD_ROOT", "datasets/EBDprocessed"))
TEST_CSV = Path(
    os.environ.get("AGENT2_EBD_TEST_CSV", str(EBD_ROOT / "splits" / "test.csv"))
)
PAIRED_PROMPT_PATH = AGENT2_ROOT / "src" / "prompts" / "paired.txt"
POST_ONLY_PROMPT_PATH = AGENT2_ROOT / "src" / "prompts" / "post_only.txt"
DEFAULT_OUTPUT_ROOT = Path(
    os.environ.get(
        "AGENT2_ABLATION_OUTPUT_ROOT",
        str(AGENT2_ROOT / "outputs" / "pair_ablation"),
    )
)

SEED = 20260728
MISMATCH_REPEATS = 5
MAX_NEW_TOKENS = 320

TARGET_ALLOCATION = {
    "HURRICANE-IAN": 3,
    "PAKISTAN-FLOODING": 3,
    "HURRICANE-IDA": 2,
    "HURRICANE-DELTA": 2,
    "EARTHQUAKE-TURKEY": 2,
    "HURRICANE-IRMA": 2,
    "HURRICANE-LAURA": 1,
    "MOUNT-SEMERU-ERUPTION": 1,
    "HURRICANE-DORIAN": 1,
    "STVINCENT-VOLCANO": 1,
    "TEXAS-TORNADOES": 1,
    "TONGA-VOLCANO": 1,
}

POST_ONLY_BANNED_PATTERNS = (
    "pre-disaster",
    "predisaster",
    "before",
    "first input",
    "second input",
    "first image",
    "second image",
    "compare",
    "comparison",
    "previous",
    "previously",
    "prior",
    "change",
    "changed",
    "unchanged",
)


def utcnow_local() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Prompt is empty: {path}")
    return text


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_config_hash(base_model_path: Path, lora_path: Path) -> str:
    paths = [
        base_model_path / "config.json",
        lora_path / "adapter_config.json",
    ]
    digest = hashlib.sha256()
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Missing model config for hashing: {path}")
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def import_pipeline_module():
    """Import lazily so manifest and metric tests stay CPU/dependency light."""

    return importlib.import_module("backend.agents.agent2.src.pipeline")


def load_test_rows() -> List[Dict[str, str]]:
    if not TEST_CSV.exists():
        raise FileNotFoundError(f"EBD test split not found: {TEST_CSV}")
    with TEST_CSV.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    required = {"sample_id", "disaster_type", "pre_image", "post_image"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"Unexpected EBD test schema in {TEST_CSV}")
    return rows


def absolute_image_path(relative_path: str) -> Path:
    path = EBD_ROOT / Path(relative_path.replace("/", "\\"))
    if not path.exists():
        raise FileNotFoundError(f"EBD image not found: {path}")
    return path


def group_by_disaster(rows: Iterable[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    grouped: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["disaster_type"], []).append(row)
    for values in grouped.values():
        values.sort(key=lambda item: item["sample_id"])
    return grouped


def build_experiment_manifest(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    grouped = group_by_disaster(rows)
    selection_rng = random.Random(SEED)
    targets: List[Dict[str, Any]] = []

    for disaster_type, requested_count in TARGET_ALLOCATION.items():
        candidates = grouped.get(disaster_type, [])
        if len(candidates) < requested_count:
            raise ValueError(
                f"{disaster_type} only has {len(candidates)} test rows; "
                f"{requested_count} required."
            )
        selected = selection_rng.sample(candidates, requested_count)
        selected.sort(key=lambda item: item["sample_id"])
        targets.extend(selected)

    targets.sort(key=lambda item: item["sample_id"])
    mismatch_rng = random.Random(SEED + 1)
    target_records: List[Dict[str, Any]] = []

    for row in targets:
        candidates = [
            candidate
            for candidate in grouped[row["disaster_type"]]
            if candidate["sample_id"] != row["sample_id"]
        ]
        if len(candidates) < MISMATCH_REPEATS:
            raise ValueError(
                f"Not enough mismatch candidates for {row['sample_id']}: "
                f"{len(candidates)}"
            )
        mismatches = mismatch_rng.sample(candidates, MISMATCH_REPEATS)
        target_records.append(
            {
                "sample_id": row["sample_id"],
                "disaster_type": row["disaster_type"],
                "pre_image": str(absolute_image_path(row["pre_image"])),
                "post_image": str(absolute_image_path(row["post_image"])),
                "mismatched_pre_images": [
                    {
                        "source_sample_id": mismatch["sample_id"],
                        "disaster_type": mismatch["disaster_type"],
                        "pre_image": str(absolute_image_path(mismatch["pre_image"])),
                    }
                    for mismatch in mismatches
                ],
            }
        )

    manifest = {
        "schema_version": "1.0",
        "experiment_name": DEFAULT_OUTPUT_ROOT.name,
        "created_at": utcnow_local(),
        "sampling_source": str(TEST_CSV),
        "sampling_split": "test",
        "sampling_seed": SEED,
        "mismatch_seed": SEED + 1,
        "target_count": len(target_records),
        "mismatch_repeats": MISMATCH_REPEATS,
        "target_allocation": TARGET_ALLOCATION,
        "targets": target_records,
        "limitations": [
            (
                "The EBD test split is held out from the local EBD training split, "
                "but membership in the unavailable Qwen LoRA training manifest "
                "cannot be ruled out."
            ),
            (
                "This experiment evaluates the fine-tuned model only and does not "
                "attribute behavior changes to LoRA versus the base model."
            ),
        ],
    }
    validate_experiment_manifest(manifest)
    return manifest


def validate_experiment_manifest(manifest: Dict[str, Any]) -> None:
    targets = manifest.get("targets", [])
    expected_target_count = sum(TARGET_ALLOCATION.values())
    if len(targets) != expected_target_count:
        raise ValueError(f"Expected {expected_target_count} targets, got {len(targets)}")

    seen_target_ids = set()
    disaster_counts: Dict[str, int] = {}
    for target in targets:
        sample_id = target["sample_id"]
        disaster_type = target["disaster_type"]
        if sample_id in seen_target_ids:
            raise ValueError(f"Duplicate target sample: {sample_id}")
        seen_target_ids.add(sample_id)
        disaster_counts[disaster_type] = disaster_counts.get(disaster_type, 0) + 1

        mismatches = target.get("mismatched_pre_images", [])
        if len(mismatches) != MISMATCH_REPEATS:
            raise ValueError(f"{sample_id} must have {MISMATCH_REPEATS} mismatches")
        mismatch_ids = [item["source_sample_id"] for item in mismatches]
        if len(set(mismatch_ids)) != MISMATCH_REPEATS:
            raise ValueError(f"{sample_id} has duplicate mismatch sources")
        for mismatch in mismatches:
            if mismatch["source_sample_id"] == sample_id:
                raise ValueError(f"{sample_id} is self-matched")
            if mismatch["disaster_type"] != disaster_type:
                raise ValueError(f"{sample_id} has a cross-disaster mismatch")

    if disaster_counts != TARGET_ALLOCATION:
        raise ValueError(
            f"Target allocation differs from preregistration: {disaster_counts}"
        )


def load_or_create_manifest(output_root: Path) -> Dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "experiment_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        validate_experiment_manifest(manifest)
        return manifest

    manifest = build_experiment_manifest(load_test_rows())
    manifest["experiment_name"] = output_root.name
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def validate_post_only_text(text: str) -> None:
    lowered = " ".join(text.lower().split())
    found = [term for term in POST_ONLY_BANNED_PATTERNS if term in lowered]
    if found:
        raise ValueError(
            "Post-only text contains forbidden paired-image language: "
            + ", ".join(found)
        )


def post_only_messages(pipeline, agent2_module, post_image_path: Path, prompt: str):
    validate_post_only_text(prompt)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Post-disaster image:"},
                {
                    "type": "image",
                    "image": pipeline._open_image(post_image_path),
                    "min_pixels": agent2_module.MIN_PIXELS,
                    "max_pixels": agent2_module.MAX_PIXELS,
                },
                {"type": "text", "text": prompt},
            ],
        }
    ]
    all_text = " ".join(
        item["text"]
        for item in messages[0]["content"]
        if item["type"] == "text"
    )
    validate_post_only_text(all_text)
    if sum(item["type"] == "image" for item in messages[0]["content"]) != 1:
        raise AssertionError("Post-only message must contain exactly one image")
    return messages


def iter_run_records(
    manifest: Dict[str, Any],
    sample_limit: int | None = None,
    mismatch_limit: int | None = None,
) -> Iterable[Dict[str, Any]]:
    targets = manifest["targets"]
    if sample_limit is not None:
        targets = targets[:sample_limit]
    mismatch_count = (
        MISMATCH_REPEATS if mismatch_limit is None else mismatch_limit
    )
    if not 1 <= mismatch_count <= MISMATCH_REPEATS:
        raise ValueError(f"mismatch_limit must be between 1 and {MISMATCH_REPEATS}")

    for target in targets:
        common = {
            "sample_id": target["sample_id"],
            "disaster_type": target["disaster_type"],
            "true_pre_image": target["pre_image"],
            "post_image": target["post_image"],
        }
        yield {
            **common,
            "record_id": f"{target['sample_id']}__paired",
            "condition": "paired",
            "condition_index": 0,
            "actual_pre_image": target["pre_image"],
            "mismatch_source_sample_id": None,
        }
        yield {
            **common,
            "record_id": f"{target['sample_id']}__post_only",
            "condition": "post_only",
            "condition_index": 0,
            "actual_pre_image": None,
            "mismatch_source_sample_id": None,
        }
        for index, mismatch in enumerate(
            target["mismatched_pre_images"][:mismatch_count],
            start=1,
        ):
            yield {
                **common,
                "record_id": (
                    f"{target['sample_id']}__mismatched_pre_{index:02d}"
                ),
                "condition": "mismatched_pre",
                "condition_index": index,
                "actual_pre_image": mismatch["pre_image"],
                "mismatch_source_sample_id": mismatch["source_sample_id"],
            }


def result_path(output_root: Path, record: Dict[str, Any]) -> Path:
    return (
        output_root
        / "records"
        / record["sample_id"]
        / record["record_id"]
        / "result.json"
    )


def load_success_result(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if payload.get("status") == "success" else None


def write_summary(output_root: Path, records: List[Dict[str, Any]]) -> None:
    records = sorted(records, key=lambda item: item["record_id"])
    payload = {
        "schema_version": "1.0",
        "updated_at": utcnow_local(),
        "record_count": len(records),
        "success_count": sum(item.get("status") == "success" for item in records),
        "failed_count": sum(item.get("status") == "failed" for item in records),
        "records": records,
    }
    (output_root / "run_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    fieldnames = [
        "record_id",
        "sample_id",
        "disaster_type",
        "condition",
        "condition_index",
        "status",
        "caption",
        "word_count",
        "claim_count",
        "mismatch_source_sample_id",
        "result_path",
        "error",
    ]
    with (output_root / "run_summary.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def build_messages(pipeline, agent2_module, record, paired_prompt, post_only_prompt):
    post_path = Path(record["post_image"])
    if record["condition"] == "post_only":
        return post_only_messages(
            pipeline,
            agent2_module,
            post_path,
            post_only_prompt,
        )
    return pipeline._messages(
        pipeline._open_image(Path(record["actual_pre_image"])),
        pipeline._open_image(post_path),
        paired_prompt,
    )


def run_record(
    pipeline,
    agent2_module,
    record: Dict[str, Any],
    output_root: Path,
    paired_prompt: str,
    post_only_prompt: str,
    hashes: Dict[str, str],
) -> Dict[str, Any]:
    path = result_path(output_root, record)
    path.parent.mkdir(parents=True, exist_ok=True)
    start_time = utcnow_local()
    try:
        messages = build_messages(
            pipeline,
            agent2_module,
            record,
            paired_prompt,
            post_only_prompt,
        )
        raw, caption = pipeline.generate_from_messages(
            messages,
            max_new_tokens=MAX_NEW_TOKENS,
        )
        if not caption:
            raise RuntimeError("Model returned an empty caption")
        claims = annotate_claims(caption)
        prompt_path = (
            POST_ONLY_PROMPT_PATH
            if record["condition"] == "post_only"
            else PAIRED_PROMPT_PATH
        )
        payload = {
            "schema_version": "1.0",
            **record,
            "status": "success",
            "started_at": start_time,
            "ended_at": utcnow_local(),
            "input_images": {
                "pre_image": record["actual_pre_image"],
                "post_image": record["post_image"],
            },
            "prompt_path": str(prompt_path),
            "prompt_sha256": (
                hashes["post_only_prompt"]
                if record["condition"] == "post_only"
                else hashes["paired_prompt"]
            ),
            "model_config_sha256": hashes["model_config"],
            "generation": {
                "max_new_tokens": MAX_NEW_TOKENS,
                "do_sample": False,
                "repetition_penalty": 1.05,
                "min_pixels": agent2_module.MIN_PIXELS,
                "max_pixels": agent2_module.MAX_PIXELS,
            },
            "raw_caption": raw,
            "caption": caption,
            "claims": claims,
            "word_count": len(caption.split()),
            "claim_count": len(claims),
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (path.parent / "raw_response.txt").write_text(raw, encoding="utf-8")
        (path.parent / "prompt_snapshot.txt").write_text(
            post_only_prompt if record["condition"] == "post_only" else paired_prompt,
            encoding="utf-8",
        )
        return {
            **record,
            "status": "success",
            "caption": caption,
            "word_count": len(caption.split()),
            "claim_count": len(claims),
            "result_path": str(path),
            "error": "",
        }
    except Exception as error:
        error_text = traceback.format_exc()
        failed_payload = {
            "schema_version": "1.0",
            **record,
            "status": "failed",
            "started_at": start_time,
            "ended_at": utcnow_local(),
            "error": str(error),
            "traceback": error_text,
        }
        path.write_text(
            json.dumps(failed_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (path.parent / "error.txt").write_text(error_text, encoding="utf-8")
        return {
            **record,
            "status": "failed",
            "caption": "",
            "word_count": 0,
            "claim_count": 0,
            "result_path": str(path),
            "error": str(error),
        }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ebd_root", default=str(EBD_ROOT))
    parser.add_argument("--test_csv", default=str(TEST_CSV))
    parser.add_argument("--paired_prompt", default=str(PAIRED_PROMPT_PATH))
    parser.add_argument("--post_only_prompt", default=str(POST_ONLY_PROMPT_PATH))
    parser.add_argument("--output_root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--base_model_path", default=os.environ.get("AGENT2_BASE_MODEL_PATH"))
    parser.add_argument("--lora_path", default=os.environ.get("AGENT2_LORA_PATH"))
    parser.add_argument("--offload_dir", default=None)
    parser.add_argument("--gpu_memory", default="6GiB")
    parser.add_argument("--cpu_memory", default="24GiB")
    parser.add_argument("--sample_limit", type=int, default=None)
    parser.add_argument("--mismatch_limit", type=int, default=None)
    parser.add_argument("--prepare_only", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    global EBD_ROOT, TEST_CSV, PAIRED_PROMPT_PATH, POST_ONLY_PROMPT_PATH

    args = parse_args()
    EBD_ROOT = Path(args.ebd_root)
    TEST_CSV = Path(args.test_csv)
    PAIRED_PROMPT_PATH = Path(args.paired_prompt)
    POST_ONLY_PROMPT_PATH = Path(args.post_only_prompt)
    output_root = Path(args.output_root)
    manifest = load_or_create_manifest(output_root)
    paired_prompt = read_text(PAIRED_PROMPT_PATH)
    post_only_prompt = read_text(POST_ONLY_PROMPT_PATH)
    validate_post_only_text(post_only_prompt)
    requested_records = list(
        iter_run_records(
            manifest,
            sample_limit=args.sample_limit,
            mismatch_limit=args.mismatch_limit,
        )
    )

    print("=" * 100)
    print("Agent2 paired-reference ablation")
    print(f"Output: {output_root}")
    print(f"Requested records: {len(requested_records)}")
    print("=" * 100)

    if args.prepare_only:
        print("Manifest prepared; model inference was not requested.")
        return

    completed: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []
    for record in requested_records:
        existing = None if args.overwrite else load_success_result(
            result_path(output_root, record)
        )
        if existing is None:
            pending.append(record)
        else:
            completed.append(
                {
                    **record,
                    "status": "success",
                    "caption": existing["caption"],
                    "word_count": existing["word_count"],
                    "claim_count": existing["claim_count"],
                    "result_path": str(result_path(output_root, record)),
                    "error": "",
                }
            )

    write_summary(output_root, completed)
    if not pending:
        print("All requested records already completed.")
        return
    if not args.base_model_path:
        raise ValueError("Agent2 base model path is not configured")
    if not args.lora_path:
        raise ValueError("Agent2 LoRA path is not configured")

    agent2_module = import_pipeline_module()
    base_model_path = Path(args.base_model_path)
    lora_path = Path(args.lora_path)
    hashes = {
        "paired_prompt": sha256_bytes(paired_prompt.encode("utf-8")),
        "post_only_prompt": sha256_bytes(post_only_prompt.encode("utf-8")),
        "model_config": model_config_hash(base_model_path, lora_path),
        "adapter_weights": sha256_file(lora_path / "adapter_model.safetensors"),
    }
    (output_root / "run_config.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "created_at": utcnow_local(),
                "base_model": base_model_path.name,
                "lora_adapter": lora_path.name,
                "hashes": hashes,
                "generation": {
                    "max_new_tokens": MAX_NEW_TOKENS,
                    "do_sample": False,
                    "repetition_penalty": 1.05,
                    "min_pixels": agent2_module.MIN_PIXELS,
                    "max_pixels": agent2_module.MAX_PIXELS,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    pipeline = agent2_module.Agent2Pipeline(
        gpu_memory=args.gpu_memory,
        cpu_memory=args.cpu_memory,
        base_model_path=base_model_path,
        lora_path=lora_path,
        prompt_path=PAIRED_PROMPT_PATH,
        offload_dir=args.offload_dir or output_root / "model_offload",
    )
    total_pending = len(pending)
    for index, record in enumerate(pending, start=1):
        print(
            f"[{index}/{total_pending}] "
            f"{record['sample_id']} {record['condition']} "
            f"{record['condition_index']}"
        )
        summary_record = run_record(
            pipeline,
            agent2_module,
            record,
            output_root,
            paired_prompt,
            post_only_prompt,
            hashes,
        )
        completed.append(summary_record)
        write_summary(output_root, completed)
        if summary_record["status"] == "success":
            print(summary_record["caption"])
        else:
            print(f"[FAILED] {summary_record['error']}")
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    failures = [item for item in completed if item["status"] == "failed"]
    print("=" * 100)
    print(f"Completed: {len(completed) - len(failures)}")
    print(f"Failed: {len(failures)}")
    print("=" * 100)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
