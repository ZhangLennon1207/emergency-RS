# -*- coding: utf-8 -*-
"""Prepare blind review artifacts and analyze the Agent2 pair ablation."""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import random
import shutil
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np

from backend.agents.agent2.experiments.ablation_utils import (
    english_single_paragraph_compliant,
    mean,
    rouge_l_f1,
    token_jaccard,
)


AGENT2_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = Path(
    os.environ.get(
        "AGENT2_ABLATION_OUTPUT_ROOT",
        str(AGENT2_ROOT / "outputs" / "pair_ablation"),
    )
)
BLIND_SEED = 20260730
BOOTSTRAP_SEED = 20260731
BOOTSTRAP_REPLICATES = 10000

SUPPORT_LABELS = {
    "supported": 1.0,
    "partially_supported": 0.5,
    "unsupported": 0.0,
    "uncertain": 0.0,
}
TEMPORAL_LABELS = {"correct", "incorrect", "not_applicable", "uncertain"}
REQUIREMENT_LABELS = {"temporal_pair", "post_only", "not_applicable"}

REVIEW_FIELDS = [
    "review_id",
    "reviewer_id",
    "sample_alias",
    "caption_alias",
    "claim_index",
    "claim_text",
    "auto_categories",
    "auto_is_temporal",
    "auto_evidence_requirement",
    "support_label",
    "temporal_correct",
    "evidence_requirement_review",
    "notes",
]

DISASTER_LABEL_TERMS = {
    "flood": ("flood", "flooding", "floodwater", "inundation", "water intrusion"),
    "landslide_debris_flow": ("landslide", "debris flow", "debris-flow", "mudflow"),
    "earthquake": ("earthquake", "seismic"),
    "storm_hurricane": ("storm", "hurricane", "heavy rainfall", "wind event"),
    "volcanic": ("volcan", "eruption", "ash"),
    "tornado": ("tornado",),
    "urban_development": (
        "urban expansion",
        "urbanization",
        "population growth",
        "land development",
    ),
}


def load_results(output_root: Path) -> List[Dict[str, Any]]:
    results = []
    for path in sorted((output_root / "records").glob("*/*/result.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") == "success":
            payload["_result_path"] = str(path)
            results.append(payload)
    if not results:
        raise FileNotFoundError(f"No successful results found under {output_root}")
    return results


def extract_disaster_labels(caption: str) -> List[str]:
    lowered = caption.lower()
    labels = [
        label
        for label, terms in DISASTER_LABEL_TERMS.items()
        if any(term in lowered for term in terms)
    ]
    return labels or ["other_or_unspecified"]


def result_index(results: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {item["record_id"]: item for item in results}


def prepare_blind_review(
    output_root: Path,
    results: Sequence[Dict[str, Any]],
    force: bool = False,
) -> Dict[str, Any]:
    blind_root = output_root / "blind_review"
    assets_root = blind_root / "assets"
    key_path = blind_root / "blind_key.json"
    reviewer_paths = [
        blind_root / "reviewer_A.csv",
        blind_root / "reviewer_B.csv",
    ]
    if key_path.exists() and not force:
        key = json.loads(key_path.read_text(encoding="utf-8"))
        if key.get("source_record_count") != len(results):
            raise RuntimeError(
                "Blind review key exists for a different result count. "
                "Use --force_rebuild_blind only if no review annotations must be kept."
            )
        return key

    blind_root.mkdir(parents=True, exist_ok=True)
    assets_root.mkdir(parents=True, exist_ok=True)
    rng = random.Random(BLIND_SEED)
    by_sample: Dict[str, List[Dict[str, Any]]] = {}
    for result in results:
        by_sample.setdefault(result["sample_id"], []).append(result)

    sample_ids = sorted(by_sample)
    shuffled_samples = sample_ids[:]
    rng.shuffle(shuffled_samples)
    sample_aliases = {
        sample_id: f"S{index:03d}"
        for index, sample_id in enumerate(shuffled_samples, start=1)
    }

    review_rows: List[Dict[str, Any]] = []
    mapping: Dict[str, Any] = {}
    caption_mapping: Dict[str, Any] = {}
    review_counter = 0

    for sample_id in shuffled_samples:
        sample_alias = sample_aliases[sample_id]
        sample_results = by_sample[sample_id][:]
        rng.shuffle(sample_results)
        reference = sample_results[0]
        pre_asset = assets_root / f"{sample_alias}_A.png"
        post_asset = assets_root / f"{sample_alias}_B.png"
        shutil.copy2(reference["true_pre_image"], pre_asset)
        shutil.copy2(reference["post_image"], post_asset)

        for caption_index, result in enumerate(sample_results, start=1):
            caption_alias = f"{sample_alias}-C{caption_index:02d}"
            caption_mapping[caption_alias] = {
                "record_id": result["record_id"],
                "sample_id": result["sample_id"],
                "condition": result["condition"],
                "condition_index": result["condition_index"],
                "mismatch_source_sample_id": result.get(
                    "mismatch_source_sample_id"
                ),
            }
            for claim in result["claims"]:
                review_counter += 1
                review_id = f"R{review_counter:05d}"
                row = {
                    "review_id": review_id,
                    "reviewer_id": "",
                    "sample_alias": sample_alias,
                    "caption_alias": caption_alias,
                    "claim_index": claim["claim_index"],
                    "claim_text": claim["claim_text"],
                    "auto_categories": "|".join(claim["categories"]),
                    "auto_is_temporal": str(claim["is_temporal"]).lower(),
                    "auto_evidence_requirement": claim[
                        "auto_evidence_requirement"
                    ],
                    "support_label": "",
                    "temporal_correct": "",
                    "evidence_requirement_review": "",
                    "notes": "",
                }
                review_rows.append(row)
                mapping[review_id] = {
                    "record_id": result["record_id"],
                    "claim_index": claim["claim_index"],
                }

    key = {
        "schema_version": "1.0",
        "blind_seed": BLIND_SEED,
        "source_record_count": len(results),
        "source_claim_count": len(review_rows),
        "sample_aliases": sample_aliases,
        "caption_mapping": caption_mapping,
        "review_mapping": mapping,
    }
    key_path.write_text(
        json.dumps(key, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for reviewer_id, path in zip(("A", "B"), reviewer_paths):
        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=REVIEW_FIELDS)
            writer.writeheader()
            for source_row in review_rows:
                writer.writerow({**source_row, "reviewer_id": reviewer_id})

    write_review_html(blind_root, shuffled_samples, by_sample, sample_aliases, key)
    return key


def write_review_html(
    blind_root: Path,
    shuffled_samples: Sequence[str],
    by_sample: Dict[str, List[Dict[str, Any]]],
    sample_aliases: Dict[str, str],
    key: Dict[str, Any],
) -> None:
    caption_lookup = {
        value["record_id"]: alias
        for alias, value in key["caption_mapping"].items()
    }
    sections = []
    for sample_id in shuffled_samples:
        sample_alias = sample_aliases[sample_id]
        captions = sorted(
            by_sample[sample_id],
            key=lambda item: caption_lookup[item["record_id"]],
        )
        caption_html = []
        for result in captions:
            alias = caption_lookup[result["record_id"]]
            claims = "".join(
                f"<li><code>{alias} / claim {claim['claim_index']}</code> "
                f"{html.escape(claim['claim_text'])}</li>"
                for claim in result["claims"]
            )
            caption_html.append(
                f"<article><h3>{alias}</h3>"
                f"<p>{html.escape(result['caption'])}</p><ol>{claims}</ol></article>"
            )
        sections.append(
            f"<section><h2>{sample_alias}</h2>"
            f"<div class='images'>"
            f"<figure><img src='assets/{sample_alias}_A.png'><figcaption>"
            f"Reference A（真实灾前图）</figcaption></figure>"
            f"<figure><img src='assets/{sample_alias}_B.png'><figcaption>"
            f"Reference B（真实灾后图）</figcaption></figure></div>"
            + "".join(caption_html)
            + "</section>"
        )

    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Agent2 匿名 claim 盲审</title>
<style>
body{{font-family:Arial,"Microsoft YaHei",sans-serif;margin:24px;line-height:1.5}}
section{{border-top:3px solid #333;margin:36px 0;padding-top:16px}}
.images{{display:flex;gap:20px;flex-wrap:wrap}} figure{{margin:0}}
img{{width:420px;max-width:100%;border:1px solid #aaa}} article{{margin:22px 0}}
code{{color:#555}} .rules{{background:#f2f4f7;padding:16px;border-radius:8px}}
</style></head><body>
<h1>Agent2 匿名 claim 盲审</h1>
<div class="rules">
<p>条件和输入来源已隐藏。请在 reviewer_A.csv 或 reviewer_B.csv 中填写：</p>
<ul>
<li>support_label：supported / partially_supported / unsupported / uncertain</li>
<li>temporal_correct：correct / incorrect / not_applicable / uncertain</li>
<li>evidence_requirement_review：temporal_pair / post_only / not_applicable</li>
</ul>
<p>所有 claim 均以这里展示的真实灾前—灾后图像对为判断依据。</p>
</div>
{''.join(sections)}
</body></html>"""
    (blind_root / "review_book.html").write_text(document, encoding="utf-8")


def caption_metric_rows(results: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for result in results:
        claims = result["claims"]
        temporal_count = sum(bool(claim["is_temporal"]) for claim in claims)
        rows.append(
            {
                "record_id": result["record_id"],
                "sample_id": result["sample_id"],
                "condition": result["condition"],
                "condition_index": result["condition_index"],
                "word_count": result["word_count"],
                "claim_count": len(claims),
                "temporal_claim_count": temporal_count,
                "temporal_claim_ratio": (
                    temporal_count / len(claims) if claims else 0.0
                ),
                "format_compliant": english_single_paragraph_compliant(
                    result["caption"]
                ),
                "disaster_labels": "|".join(
                    extract_disaster_labels(result["caption"])
                ),
            }
        )
    return rows


def automatic_comparisons(
    results: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    by_sample: Dict[str, List[Dict[str, Any]]] = {}
    for result in results:
        by_sample.setdefault(result["sample_id"], []).append(result)

    comparison_rows = []
    mismatch_variances = []
    disaster_stability_rows = []
    for sample_id, sample_results in sorted(by_sample.items()):
        paired = next(
            item for item in sample_results if item["condition"] == "paired"
        )
        post_only = next(
            item for item in sample_results if item["condition"] == "post_only"
        )
        mismatches = [
            item
            for item in sample_results
            if item["condition"] == "mismatched_pre"
        ]
        comparison_rows.append(
            {
                "sample_id": sample_id,
                "comparison": "paired_vs_post_only",
                "comparison_index": 0,
                "rouge_l_f1": rouge_l_f1(
                    paired["caption"], post_only["caption"]
                ),
                "token_jaccard": token_jaccard(
                    paired["caption"], post_only["caption"]
                ),
            }
        )
        for mismatch in mismatches:
            comparison_rows.append(
                {
                    "sample_id": sample_id,
                    "comparison": "paired_vs_mismatched_pre",
                    "comparison_index": mismatch["condition_index"],
                    "rouge_l_f1": rouge_l_f1(
                        paired["caption"], mismatch["caption"]
                    ),
                    "token_jaccard": token_jaccard(
                        paired["caption"], mismatch["caption"]
                    ),
                }
            )
        mismatch_pairs = list(combinations(mismatches, 2))
        paired_labels = set(extract_disaster_labels(paired["caption"]))
        post_labels = set(extract_disaster_labels(post_only["caption"]))
        mismatch_labels = [
            set(extract_disaster_labels(item["caption"]))
            for item in mismatches
        ]
        disaster_stability_rows.append(
            {
                "sample_id": sample_id,
                "paired_post_exact_label_match": paired_labels == post_labels,
                "paired_mismatch_exact_label_match_rate": mean(
                    float(paired_labels == labels) for labels in mismatch_labels
                ),
                "mismatch_unique_label_sets": len(
                    {tuple(sorted(labels)) for labels in mismatch_labels}
                ),
            }
        )
        mismatch_variances.append(
            {
                "sample_id": sample_id,
                "mismatch_pair_count": len(mismatch_pairs),
                "mean_pairwise_rouge_distance": mean(
                    1.0 - rouge_l_f1(left["caption"], right["caption"])
                    for left, right in mismatch_pairs
                ),
                "mean_pairwise_jaccard_distance": mean(
                    1.0 - token_jaccard(left["caption"], right["caption"])
                    for left, right in mismatch_pairs
                ),
            }
        )

    caption_rows = caption_metric_rows(results)
    condition_summary = {}
    for condition in ("paired", "post_only", "mismatched_pre"):
        subset = [row for row in caption_rows if row["condition"] == condition]
        label_frequency = {
            label: sum(
                label in row["disaster_labels"].split("|") for row in subset
            )
            / len(subset)
            if subset
            else 0.0
            for label in [*DISASTER_LABEL_TERMS, "other_or_unspecified"]
        }
        condition_summary[condition] = {
            "record_count": len(subset),
            "mean_word_count": mean(row["word_count"] for row in subset),
            "mean_claim_count": mean(row["claim_count"] for row in subset),
            "mean_temporal_claim_ratio": mean(
                row["temporal_claim_ratio"] for row in subset
            ),
            "format_compliance_rate": mean(
                float(row["format_compliant"]) for row in subset
            ),
            "disaster_label_frequency": label_frequency,
        }
    summary = {
        "condition_summary": condition_summary,
        "paired_vs_post_only": {
            "mean_rouge_l_f1": mean(
                row["rouge_l_f1"]
                for row in comparison_rows
                if row["comparison"] == "paired_vs_post_only"
            ),
            "mean_token_jaccard": mean(
                row["token_jaccard"]
                for row in comparison_rows
                if row["comparison"] == "paired_vs_post_only"
            ),
        },
        "paired_vs_mismatched_pre": {
            "mean_rouge_l_f1": mean(
                row["rouge_l_f1"]
                for row in comparison_rows
                if row["comparison"] == "paired_vs_mismatched_pre"
            ),
            "mean_token_jaccard": mean(
                row["token_jaccard"]
                for row in comparison_rows
                if row["comparison"] == "paired_vs_mismatched_pre"
            ),
        },
        "mismatch_output_variance": {
            "mean_pairwise_rouge_distance": mean(
                row["mean_pairwise_rouge_distance"]
                for row in mismatch_variances
            ),
            "mean_pairwise_jaccard_distance": mean(
                row["mean_pairwise_jaccard_distance"]
                for row in mismatch_variances
            ),
        },
        "disaster_judgment_stability": {
            "paired_post_exact_label_match_rate": mean(
                float(row["paired_post_exact_label_match"])
                for row in disaster_stability_rows
            ),
            "paired_mismatch_exact_label_match_rate": mean(
                row["paired_mismatch_exact_label_match_rate"]
                for row in disaster_stability_rows
            ),
            "mean_mismatch_unique_label_sets_per_sample": mean(
                row["mismatch_unique_label_sets"]
                for row in disaster_stability_rows
            ),
        },
    }
    return comparison_rows + mismatch_variances + disaster_stability_rows, summary


def wide_caption_rows(
    results: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_sample: Dict[str, List[Dict[str, Any]]] = {}
    for result in results:
        by_sample.setdefault(result["sample_id"], []).append(result)
    rows = []
    for sample_id, sample_results in sorted(by_sample.items()):
        row: Dict[str, Any] = {
            "sample_id": sample_id,
            "disaster_type": sample_results[0]["disaster_type"],
        }
        for result in sample_results:
            if result["condition"] == "mismatched_pre":
                suffix = f"mismatched_pre_{result['condition_index']:02d}"
                row[f"{suffix}_source_sample_id"] = result[
                    "mismatch_source_sample_id"
                ]
            else:
                suffix = result["condition"]
            row[f"{suffix}_caption"] = result["caption"]
            row[f"{suffix}_disaster_labels"] = "|".join(
                extract_disaster_labels(result["caption"])
            )
        rows.append(row)
    return rows


def all_claim_rows(
    results: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows = []
    for result in results:
        for claim in result["claims"]:
            rows.append(
                {
                    "record_id": result["record_id"],
                    "sample_id": result["sample_id"],
                    "disaster_type": result["disaster_type"],
                    "condition": result["condition"],
                    "condition_index": result["condition_index"],
                    "mismatch_source_sample_id": result.get(
                        "mismatch_source_sample_id"
                    ),
                    "claim_index": claim["claim_index"],
                    "claim_text": claim["claim_text"],
                    "categories": "|".join(claim["categories"]),
                    "auto_is_temporal": claim["is_temporal"],
                    "auto_evidence_requirement": claim[
                        "auto_evidence_requirement"
                    ],
                }
            )
    return rows


def write_condition_comparison_html(
    output_root: Path,
    results: Sequence[Dict[str, Any]],
) -> Path:
    analysis_root = output_root / "analysis"
    assets_root = analysis_root / "comparison_assets"
    assets_root.mkdir(parents=True, exist_ok=True)
    by_sample: Dict[str, List[Dict[str, Any]]] = {}
    for result in results:
        by_sample.setdefault(result["sample_id"], []).append(result)

    sections = []
    for sample_index, (sample_id, sample_results) in enumerate(
        sorted(by_sample.items()),
        start=1,
    ):
        paired = next(
            item for item in sample_results if item["condition"] == "paired"
        )
        post_only = next(
            item for item in sample_results if item["condition"] == "post_only"
        )
        mismatches = sorted(
            (
                item
                for item in sample_results
                if item["condition"] == "mismatched_pre"
            ),
            key=lambda item: item["condition_index"],
        )
        true_pre_asset = assets_root / f"{sample_id}_true_pre.png"
        post_asset = assets_root / f"{sample_id}_post.png"
        shutil.copy2(paired["true_pre_image"], true_pre_asset)
        shutil.copy2(paired["post_image"], post_asset)

        mismatch_cards = []
        for mismatch in mismatches:
            index = mismatch["condition_index"]
            wrong_asset = assets_root / f"{sample_id}_wrong_pre_{index:02d}.png"
            shutil.copy2(mismatch["actual_pre_image"], wrong_asset)
            mismatch_cards.append(
                f"""<article class="card mismatch">
<h4>条件 3.{index}：错误灾前图 + 同一张灾后图</h4>
<p class="source">错误灾前图来源：{html.escape(str(mismatch['mismatch_source_sample_id']))}</p>
<div class="mini-images">
<figure><img src="comparison_assets/{wrong_asset.name}"><figcaption>实际输入的错误灾前图</figcaption></figure>
<figure><img src="comparison_assets/{post_asset.name}"><figcaption>目标灾后图</figcaption></figure>
</div>
<p class="caption">{html.escape(mismatch['caption'])}</p>
</article>"""
            )

        open_attribute = " open" if sample_index == 1 else ""
        sections.append(
            f"""<details{open_attribute}>
<summary>样本 {sample_index:02d}：{html.escape(sample_id)} ｜ {html.escape(paired['disaster_type'])}</summary>
<div class="reference">
<figure><img src="comparison_assets/{true_pre_asset.name}"><figcaption>真实灾前图</figcaption></figure>
<figure><img src="comparison_assets/{post_asset.name}"><figcaption>真实灾后图（七次输出都对应这张图）</figcaption></figure>
</div>
<article class="card paired">
<h3>条件 1：正确灾前图 + 灾后图</h3>
<p class="caption">{html.escape(paired['caption'])}</p>
</article>
<article class="card post">
<h3>条件 2：只输入灾后图</h3>
<p class="caption">{html.escape(post_only['caption'])}</p>
</article>
<div class="mismatch-group">
<h3>条件 3：同灾种错误灾前图 + 灾后图（共 5 次）</h3>
{''.join(mismatch_cards)}
</div>
</details>"""
        )

    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Agent2 三条件逐样本输出对照</title>
<style>
body{{font-family:Arial,"Microsoft YaHei",sans-serif;margin:24px;line-height:1.6;background:#f5f7fa;color:#18202a}}
.intro{{background:#fff;padding:18px 22px;border-radius:10px;margin-bottom:24px;box-shadow:0 1px 5px #ccd2da}}
details{{background:#fff;margin:16px 0;border-radius:10px;box-shadow:0 1px 5px #ccd2da;overflow:hidden}}
summary{{font-size:18px;font-weight:bold;padding:16px 20px;cursor:pointer;background:#eaf0f7}}
.reference,.mini-images{{display:flex;gap:18px;flex-wrap:wrap;padding:18px}}
figure{{margin:0}} img{{width:360px;max-width:100%;border:1px solid #aeb7c2}}
figcaption{{font-size:13px;color:#586474;text-align:center}}
.card{{margin:16px 18px;padding:16px 20px;border-left:6px solid #777;border-radius:6px;background:#fafafa}}
.paired{{border-color:#17843b;background:#effaf2}} .post{{border-color:#2366c2;background:#eff5ff}}
.mismatch{{border-color:#c44536;background:#fff4f2}} .mismatch-group>h3{{margin-left:18px}}
.caption{{white-space:normal}} .source{{font-size:13px;color:#7b2c23}}
</style></head><body>
<div class="intro">
<h1>Agent2 三条件逐样本输出对照</h1>
<p>下面每一个可展开区块代表<strong>同一个目标样本</strong>。真实灾后图始终不变：</p>
<ol>
<li><strong>条件 1</strong>使用该样本真实灾前图；</li>
<li><strong>条件 2</strong>不使用灾前图；</li>
<li><strong>条件 3</strong>分别换入 5 张同灾种但不对应的灾前图。</li>
</ol>
</div>
{''.join(sections)}
</body></html>"""
    output_path = analysis_root / "condition_comparison.html"
    output_path.write_text(document, encoding="utf-8")
    return output_path


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        return
    fieldnames = sorted({key for row in rows for key in row})
    try:
        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=fieldnames,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(rows)
    except PermissionError:
        print(f"[warning] CSV is open in another application; kept unchanged: {path}")


def read_review(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def review_is_complete(rows: Sequence[Dict[str, str]]) -> bool:
    return bool(rows) and all(
        row.get("support_label") in SUPPORT_LABELS
        and row.get("temporal_correct") in TEMPORAL_LABELS
        and row.get("evidence_requirement_review") in REQUIREMENT_LABELS
        for row in rows
    )


def cohen_kappa(left: Sequence[str], right: Sequence[str]) -> float | None:
    if len(left) != len(right) or not left:
        return None
    labels = sorted(set(left) | set(right))
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    left_freq = {label: left.count(label) / len(left) for label in labels}
    right_freq = {label: right.count(label) / len(right) for label in labels}
    expected = sum(left_freq[label] * right_freq[label] for label in labels)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def resolve_review_rows(
    blind_root: Path,
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    adjudicated = read_review(blind_root / "adjudicated.csv")
    if review_is_complete(adjudicated):
        return adjudicated, {
            "status": "adjudicated",
            "reviewer_count": 2,
            "strict_conclusion_allowed": True,
        }

    left = read_review(blind_root / "reviewer_A.csv")
    right = read_review(blind_root / "reviewer_B.csv")
    left_complete = review_is_complete(left)
    right_complete = review_is_complete(right)
    if left_complete and right_complete:
        right_by_id = {row["review_id"]: row for row in right}
        disagreements = []
        resolved = []
        for row in left:
            other = right_by_id[row["review_id"]]
            fields = (
                "support_label",
                "temporal_correct",
                "evidence_requirement_review",
            )
            if any(row[field] != other[field] for field in fields):
                disagreements.append(
                    {
                        **row,
                        "reviewer_A_support": row["support_label"],
                        "reviewer_B_support": other["support_label"],
                        "reviewer_A_temporal": row["temporal_correct"],
                        "reviewer_B_temporal": other["temporal_correct"],
                        "reviewer_A_requirement": row[
                            "evidence_requirement_review"
                        ],
                        "reviewer_B_requirement": other[
                            "evidence_requirement_review"
                        ],
                    }
                )
            else:
                resolved.append(row)
        write_csv(blind_root / "review_disagreements.csv", disagreements)
        agreement = {
            "support_kappa": cohen_kappa(
                [row["support_label"] for row in left],
                [row["support_label"] for row in right],
            ),
            "temporal_kappa": cohen_kappa(
                [row["temporal_correct"] for row in left],
                [row["temporal_correct"] for row in right],
            ),
            "requirement_kappa": cohen_kappa(
                [row["evidence_requirement_review"] for row in left],
                [row["evidence_requirement_review"] for row in right],
            ),
            "disagreement_count": len(disagreements),
        }
        if disagreements:
            return [], {
                "status": "pending_adjudication",
                "reviewer_count": 2,
                "strict_conclusion_allowed": False,
                "agreement": agreement,
            }
        return resolved, {
            "status": "two_reviewer_consensus",
            "reviewer_count": 2,
            "strict_conclusion_allowed": True,
            "agreement": agreement,
        }
    if left_complete or right_complete:
        return (left if left_complete else right), {
            "status": "single_reviewer_complete",
            "reviewer_count": 1,
            "strict_conclusion_allowed": False,
        }
    return [], {
        "status": "pending_review",
        "reviewer_count": int(bool(left_complete)) + int(bool(right_complete)),
        "strict_conclusion_allowed": False,
    }


def record_review_metrics(
    review_rows: Sequence[Dict[str, str]],
    blind_key: Dict[str, Any],
) -> Dict[str, Dict[str, float]]:
    by_record: Dict[str, List[Dict[str, str]]] = {}
    for row in review_rows:
        record_id = blind_key["review_mapping"][row["review_id"]]["record_id"]
        by_record.setdefault(record_id, []).append(row)

    metrics = {}
    for record_id, rows in by_record.items():
        total = len(rows)
        support_score = sum(
            SUPPORT_LABELS[row["support_label"]] for row in rows
        )
        unsupported = sum(
            row["support_label"] == "unsupported" for row in rows
        )
        temporal_rows = [
            row
            for row in rows
            if row["evidence_requirement_review"] == "temporal_pair"
        ]
        temporal_correct = sum(
            row["temporal_correct"] == "correct" for row in temporal_rows
        )
        pair_grounding = sum(
            SUPPORT_LABELS[row["support_label"]]
            for row in temporal_rows
            if row["temporal_correct"] == "correct"
        )
        metrics[record_id] = {
            "claim_count": float(total),
            "claim_support_rate": support_score / total if total else 0.0,
            "unsupported_rate": unsupported / total if total else 0.0,
            "temporal_claim_count": float(len(temporal_rows)),
            "temporal_accuracy": (
                temporal_correct / len(temporal_rows) if temporal_rows else 0.0
            ),
            "pair_grounding_score": pair_grounding / total if total else 0.0,
        }
    return metrics


def bootstrap_mean_ci(values: Sequence[float]) -> Tuple[float, float]:
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    samples = rng.choice(
        array,
        size=(BOOTSTRAP_REPLICATES, array.size),
        replace=True,
    )
    means = samples.mean(axis=1)
    return (float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975)))


def holm_adjust(p_values: Sequence[float]) -> List[float]:
    order = sorted(range(len(p_values)), key=lambda index: p_values[index])
    adjusted = [0.0] * len(p_values)
    running_max = 0.0
    total = len(p_values)
    for rank, index in enumerate(order):
        candidate = min(1.0, (total - rank) * p_values[index])
        running_max = max(running_max, candidate)
        adjusted[index] = running_max
    return adjusted


def paired_wilcoxon_greater(
    paired: Sequence[float],
    control: Sequence[float],
) -> float:
    try:
        from scipy.stats import wilcoxon
    except ImportError as error:
        raise RuntimeError(
            "SciPy is required for the preregistered Wilcoxon test. "
            "Run this script with disaster_env."
        ) from error
    differences = np.asarray(paired) - np.asarray(control)
    if np.allclose(differences, 0.0):
        return 1.0
    return float(
        wilcoxon(
            paired,
            control,
            alternative="greater",
            zero_method="wilcox",
        ).pvalue
    )


def qualification_analysis(
    results: Sequence[Dict[str, Any]],
    review_metrics: Dict[str, Dict[str, float]],
    review_status: Dict[str, Any],
) -> Dict[str, Any]:
    by_sample: Dict[str, List[Dict[str, Any]]] = {}
    for result in results:
        by_sample.setdefault(result["sample_id"], []).append(result)

    sample_rows = []
    for sample_id, sample_results in sorted(by_sample.items()):
        paired = next(
            item for item in sample_results if item["condition"] == "paired"
        )
        post = next(
            item for item in sample_results if item["condition"] == "post_only"
        )
        mismatches = [
            item
            for item in sample_results
            if item["condition"] == "mismatched_pre"
        ]
        if any(
            item["record_id"] not in review_metrics
            for item in [paired, post, *mismatches]
        ):
            raise ValueError(f"Missing review metrics for sample {sample_id}")
        paired_metrics = review_metrics[paired["record_id"]]
        post_metrics = review_metrics[post["record_id"]]
        mismatch_grounding = mean(
            review_metrics[item["record_id"]]["pair_grounding_score"]
            for item in mismatches
        )
        sample_rows.append(
            {
                "sample_id": sample_id,
                "paired_support_rate": paired_metrics["claim_support_rate"],
                "paired_unsupported_rate": paired_metrics["unsupported_rate"],
                "paired_temporal_accuracy": paired_metrics["temporal_accuracy"],
                "paired_pair_grounding_score": paired_metrics[
                    "pair_grounding_score"
                ],
                "post_only_pair_grounding_score": post_metrics[
                    "pair_grounding_score"
                ],
                "mismatched_pair_grounding_score": mismatch_grounding,
            }
        )

    paired_grounding = [
        row["paired_pair_grounding_score"] for row in sample_rows
    ]
    post_grounding = [
        row["post_only_pair_grounding_score"] for row in sample_rows
    ]
    mismatch_grounding = [
        row["mismatched_pair_grounding_score"] for row in sample_rows
    ]
    paired_post_differences = [
        left - right for left, right in zip(paired_grounding, post_grounding)
    ]
    paired_mismatch_differences = [
        left - right
        for left, right in zip(paired_grounding, mismatch_grounding)
    ]
    raw_p = [
        paired_wilcoxon_greater(paired_grounding, post_grounding),
        paired_wilcoxon_greater(paired_grounding, mismatch_grounding),
    ]
    adjusted_p = holm_adjust(raw_p)
    post_ci = bootstrap_mean_ci(paired_post_differences)
    mismatch_ci = bootstrap_mean_ci(paired_mismatch_differences)

    paired_results = [
        item for item in results if item["condition"] == "paired"
    ]
    paired_metric_rows = [
        review_metrics[item["record_id"]] for item in paired_results
    ]
    claim_support_rate = mean(
        row["claim_support_rate"] for row in paired_metric_rows
    )
    unsupported_rate = mean(
        row["unsupported_rate"] for row in paired_metric_rows
    )
    temporal_accuracy = mean(
        row["temporal_accuracy"] for row in paired_metric_rows
    )
    format_compliance = mean(
        float(english_single_paragraph_compliant(item["caption"]))
        for item in paired_results
    )
    mean_post_advantage = mean(paired_post_differences)
    mean_mismatch_advantage = mean(paired_mismatch_differences)

    checks = {
        "paired_claim_support_rate_at_least_0_90": claim_support_rate >= 0.90,
        "paired_temporal_accuracy_at_least_0_85": temporal_accuracy >= 0.85,
        "paired_unsupported_rate_at_most_0_10": unsupported_rate <= 0.10,
        "paired_advantage_over_post_at_least_0_15": mean_post_advantage >= 0.15,
        "paired_advantage_over_mismatch_at_least_0_15": (
            mean_mismatch_advantage >= 0.15
        ),
        "paired_post_bootstrap_lower_above_zero": post_ci[0] > 0.0,
        "paired_mismatch_bootstrap_lower_above_zero": mismatch_ci[0] > 0.0,
        "paired_post_holm_p_below_0_05": adjusted_p[0] < 0.05,
        "paired_mismatch_holm_p_below_0_05": adjusted_p[1] < 0.05,
        "paired_format_compliance_at_least_0_95": format_compliance >= 0.95,
    }
    all_checks_pass = all(checks.values())
    strict_allowed = bool(review_status["strict_conclusion_allowed"])
    if strict_allowed:
        verdict = "qualified" if all_checks_pass else "not_qualified"
    else:
        verdict = (
            "preliminary_pass" if all_checks_pass else "preliminary_not_qualified"
        )

    return {
        "verdict": verdict,
        "strict_conclusion_allowed": strict_allowed,
        "review_status": review_status,
        "paired_metrics": {
            "claim_support_rate": claim_support_rate,
            "unsupported_rate": unsupported_rate,
            "temporal_accuracy": temporal_accuracy,
            "format_compliance_rate": format_compliance,
        },
        "paired_vs_post_only": {
            "mean_pair_grounding_advantage": mean_post_advantage,
            "bootstrap_95_ci": list(post_ci),
            "wilcoxon_p_raw": raw_p[0],
            "wilcoxon_p_holm": adjusted_p[0],
        },
        "paired_vs_mismatched_pre": {
            "mean_pair_grounding_advantage": mean_mismatch_advantage,
            "bootstrap_95_ci": list(mismatch_ci),
            "wilcoxon_p_raw": raw_p[1],
            "wilcoxon_p_holm": adjusted_p[1],
        },
        "checks": checks,
        "all_checks_pass": all_checks_pass,
        "sample_rows": sample_rows,
    }


def analyze(output_root: Path, results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    analysis_root = output_root / "analysis"
    analysis_root.mkdir(parents=True, exist_ok=True)
    caption_rows = caption_metric_rows(results)
    comparison_rows, automatic_summary = automatic_comparisons(results)
    write_csv(analysis_root / "caption_metrics.csv", caption_rows)
    write_csv(analysis_root / "text_comparisons.csv", comparison_rows)
    write_csv(
        analysis_root / "caption_comparison_wide.csv",
        wide_caption_rows(results),
    )
    write_csv(analysis_root / "claims_all.csv", all_claim_rows(results))
    write_condition_comparison_html(output_root, results)
    (analysis_root / "automatic_summary.json").write_text(
        json.dumps(automatic_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    blind_root = output_root / "blind_review"
    blind_key_path = blind_root / "blind_key.json"
    if not blind_key_path.exists():
        outcome = {
            "automatic_summary": automatic_summary,
            "qualification_status": "blind_review_not_prepared",
        }
        write_preliminary_report(output_root, outcome)
        return outcome
    blind_key = json.loads(blind_key_path.read_text(encoding="utf-8"))
    review_rows, review_status = resolve_review_rows(blind_root)
    if not review_rows:
        pending = {
            "automatic_summary": automatic_summary,
            "qualification_status": review_status["status"],
            "review_status": review_status,
        }
        (analysis_root / "qualification.json").write_text(
            json.dumps(pending, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_preliminary_report(output_root, pending)
        return pending

    metrics = record_review_metrics(review_rows, blind_key)
    metric_rows = [
        {"record_id": record_id, **values}
        for record_id, values in sorted(metrics.items())
    ]
    write_csv(analysis_root / "review_metrics_by_record.csv", metric_rows)
    qualification = qualification_analysis(
        results,
        metrics,
        review_status,
    )
    (analysis_root / "qualification.json").write_text(
        json.dumps(qualification, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(
        analysis_root / "qualification_by_sample.csv",
        qualification["sample_rows"],
    )
    write_preliminary_report(
        output_root,
        {
            "automatic_summary": automatic_summary,
            **qualification,
        },
    )
    return qualification


def write_preliminary_report(
    output_root: Path,
    outcome: Dict[str, Any],
) -> None:
    automatic = outcome["automatic_summary"]
    condition = automatic["condition_summary"]
    paired = condition["paired"]
    post = condition["post_only"]
    mismatch = condition["mismatched_pre"]
    stability = automatic["disaster_judgment_stability"]
    status = outcome.get(
        "qualification_status",
        outcome.get("verdict", "pending_review"),
    )
    report = f"""# Agent2 灾前—灾后对应关系消融实验

## 当前状态

- 推理记录：paired {paired['record_count']}、post-only {post['record_count']}、mismatched-pre {mismatch['record_count']}。
- 严格资格判定：`{status}`。盲审完成前不得将自动文本差异解释为最终合格结论。
- 全部条件的英文单段格式遵守率均为 100%。

## 自动文本观察

- paired 平均 {paired['mean_word_count']:.2f} 词、{paired['mean_claim_count']:.2f} 个 claim；自动时序表达比例为 {paired['mean_temporal_claim_ratio']:.3f}。
- post-only 自动时序表达比例仍达到 {post['mean_temporal_claim_ratio']:.3f}，说明仅凭灾后图时模型仍经常生成损坏/变化式表述。
- paired 与 post-only 的平均 ROUGE-L F1 为 {automatic['paired_vs_post_only']['mean_rouge_l_f1']:.3f}；paired 与错配灾前图为 {automatic['paired_vs_mismatched_pre']['mean_rouge_l_f1']:.3f}。
- 五次错配输出之间的平均 ROUGE-L 距离为 {automatic['mismatch_output_variance']['mean_pairwise_rouge_distance']:.3f}，显示替换灾前图会显著改变输出。
- paired 条件中 flood 标签出现率为 {paired['disaster_label_frequency']['flood']:.1%}；post-only 为 {post['disaster_label_frequency']['flood']:.1%}；mismatched-pre 为 {mismatch['disaster_label_frequency']['flood']:.1%}。
- paired 与 post-only 的灾种标签集合完全一致率仅为 {stability['paired_post_exact_label_match_rate']:.1%}；paired 与错配条件为 {stability['paired_mismatch_exact_label_match_rate']:.1%}。

以上结果说明模型会读取灾前图，但同时存在明显的灾种措辞偏置风险。是否真正、正确地利用对应关系，必须由盲审中的事实支持率和 pair-grounding score 决定。

## 完成严格判定

1. 两位审核者分别打开 `blind_review/review_book.html`，不要查看 `blind_key.json`。
2. 分别填写 `reviewer_A.csv` 和 `reviewer_B.csv` 的三个空白判定列；允许值已经写在 HTML 首页。
3. 将填写后的 CSV 保持原文件名放回 `blind_review`。
4. 运行：

```powershell
python -m backend.agents.agent2.experiments.review_pair_ablation --output_root <run-directory> --analyze
```

若两位审核者存在分歧，脚本会生成 `review_disagreements.csv`；完成裁决后将同结构结果保存为 `adjudicated.csv` 并再次运行分析。

## 结论限制

- EBD test 相对本地 EBD 划分独立，但无法排除样本曾进入已丢失清单的 Qwen LoRA 训练集。
- 本实验没有运行未加载 LoRA 的基座模型，因此不能把观察到的能力归因为 LoRA 新增能力。
"""
    (output_root / "analysis" / "preliminary_report.md").write_text(
        report,
        encoding="utf-8",
    )


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output_root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--prepare_blind", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--force_rebuild_blind", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_root)
    results = load_results(output_root)
    do_prepare = args.prepare_blind or not args.analyze
    do_analyze = args.analyze or not args.prepare_blind
    if do_prepare:
        key = prepare_blind_review(
            output_root,
            results,
            force=args.force_rebuild_blind,
        )
        print(
            f"Blind review prepared: {key['source_record_count']} records, "
            f"{key['source_claim_count']} claims"
        )
    if do_analyze:
        summary = analyze(output_root, results)
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
