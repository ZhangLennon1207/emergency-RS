# -*- coding: utf-8 -*-

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.agents.agent2.experiments import pair_ablation as runner
from backend.agents.agent2.experiments import review_pair_ablation as review
from backend.agents.agent2.experiments.ablation_utils import (
    annotate_claims,
    english_single_paragraph_compliant,
    rouge_l_f1,
    token_jaccard,
)


class DummyPipeline:
    @staticmethod
    def _open_image(path):
        return str(path)

    @staticmethod
    def _messages(pre, post, prompt):
        return [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Pre-disaster image:"},
                    {"type": "image", "image": pre},
                    {"type": "text", "text": "Post-disaster image:"},
                    {"type": "image", "image": post},
                    {"type": "text", "text": prompt},
                ],
            }
        ]


class DummyAgent2Module:
    MIN_PIXELS = 256 * 28 * 28
    MAX_PIXELS = 512 * 28 * 28


class PairAblationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        runner.EBD_ROOT = Path(cls.temp_dir.name)
        cls.rows = []
        for disaster_type in runner.TARGET_ALLOCATION:
            for index in range(6):
                sample_id = f"{disaster_type}_{index:03d}"
                pre_name = f"{sample_id}_pre.png"
                post_name = f"{sample_id}_post.png"
                (runner.EBD_ROOT / pre_name).touch()
                (runner.EBD_ROOT / post_name).touch()
                cls.rows.append(
                    {
                        "sample_id": sample_id,
                        "disaster_type": disaster_type,
                        "pre_image": pre_name,
                        "post_image": post_name,
                    }
                )
        cls.manifest = runner.build_experiment_manifest(cls.rows)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_manifest_has_preregistered_allocation(self):
        runner.validate_experiment_manifest(self.manifest)
        counts = {}
        for target in self.manifest["targets"]:
            counts[target["disaster_type"]] = counts.get(target["disaster_type"], 0) + 1
        self.assertEqual(counts, runner.TARGET_ALLOCATION)

    def test_manifest_is_deterministic(self):
        second = runner.build_experiment_manifest(self.rows)
        first_projection = [
            (
                target["sample_id"],
                [
                    item["source_sample_id"]
                    for item in target["mismatched_pre_images"]
                ],
            )
            for target in self.manifest["targets"]
        ]
        second_projection = [
            (
                target["sample_id"],
                [
                    item["source_sample_id"]
                    for item in target["mismatched_pre_images"]
                ],
            )
            for target in second["targets"]
        ]
        self.assertEqual(first_projection, second_projection)

    def test_full_run_has_140_records(self):
        records = list(runner.iter_run_records(self.manifest))
        self.assertEqual(len(records), 140)
        self.assertEqual(
            sum(record["condition"] == "paired" for record in records),
            20,
        )
        self.assertEqual(
            sum(record["condition"] == "post_only" for record in records),
            20,
        )
        self.assertEqual(
            sum(record["condition"] == "mismatched_pre" for record in records),
            100,
        )

    def test_mismatches_are_same_disaster_unique_and_not_self(self):
        for target in self.manifest["targets"]:
            mismatches = target["mismatched_pre_images"]
            ids = [item["source_sample_id"] for item in mismatches]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertNotIn(target["sample_id"], ids)
            self.assertTrue(
                all(
                    item["disaster_type"] == target["disaster_type"]
                    for item in mismatches
                )
            )

    def test_post_only_prompt_and_message_have_no_pair_language(self):
        prompt = runner.read_text(runner.POST_ONLY_PROMPT_PATH)
        runner.validate_post_only_text(prompt)
        messages = runner.post_only_messages(
            DummyPipeline(),
            DummyAgent2Module,
            Path("post.png"),
            prompt,
        )
        content = messages[0]["content"]
        self.assertEqual(sum(item["type"] == "image" for item in content), 1)
        all_text = " ".join(
            item["text"] for item in content if item["type"] == "text"
        )
        runner.validate_post_only_text(all_text)

    def test_paired_and_mismatch_use_same_wrapper_and_prompt(self):
        prompt = runner.read_text(runner.PAIRED_PROMPT_PATH)
        paired = DummyPipeline._messages("true-pre", "post", prompt)
        mismatch = DummyPipeline._messages("wrong-pre", "post", prompt)
        paired_content = paired[0]["content"]
        mismatch_content = mismatch[0]["content"]
        self.assertEqual(
            [item["type"] for item in paired_content],
            [item["type"] for item in mismatch_content],
        )
        self.assertEqual(paired_content[-1]["text"], mismatch_content[-1]["text"])
        self.assertEqual(
            sum(item["type"] == "image" for item in paired_content),
            2,
        )

    def test_claim_annotation_and_text_metrics(self):
        caption = (
            "Several buildings appear damaged compared with the earlier view, "
            "while the central road remains visible. Overall, flooding is possible."
        )
        claims = annotate_claims(caption)
        self.assertGreaterEqual(len(claims), 3)
        self.assertTrue(any(claim["is_temporal"] for claim in claims))
        self.assertTrue(
            any("building" in claim["categories"] for claim in claims)
        )
        self.assertAlmostEqual(token_jaccard("a b", "a b"), 1.0)
        self.assertAlmostEqual(rouge_l_f1("a b", "a b"), 1.0)
        self.assertTrue(english_single_paragraph_compliant(caption))
        self.assertIn(
            "flood",
            review.extract_disaster_labels("Overall, possible flooding is visible."),
        )

    def test_strict_qualification_logic_with_synthetic_pass(self):
        results = []
        metrics = {}
        for index in range(20):
            sample_id = f"SAMPLE_{index:03d}"
            record_specs = [
                ("paired", 0, 0.80),
                ("post_only", 0, 0.10),
                *[("mismatched_pre", repeat, 0.20) for repeat in range(1, 6)],
            ]
            for condition, condition_index, grounding in record_specs:
                record_id = f"{sample_id}__{condition}_{condition_index}"
                results.append(
                    {
                        "record_id": record_id,
                        "sample_id": sample_id,
                        "condition": condition,
                        "condition_index": condition_index,
                        "caption": "Buildings and roads show clearly visible disaster impacts.",
                    }
                )
                metrics[record_id] = {
                    "claim_count": 5.0,
                    "claim_support_rate": 0.95 if condition == "paired" else 0.70,
                    "unsupported_rate": 0.05 if condition == "paired" else 0.30,
                    "temporal_claim_count": 4.0,
                    "temporal_accuracy": 0.90 if condition == "paired" else 0.50,
                    "pair_grounding_score": grounding,
                }
        outcome = review.qualification_analysis(
            results,
            metrics,
            {
                "status": "two_reviewer_consensus",
                "reviewer_count": 2,
                "strict_conclusion_allowed": True,
            },
        )
        self.assertEqual(outcome["verdict"], "qualified")
        self.assertTrue(outcome["all_checks_pass"])


if __name__ == "__main__":
    unittest.main()
