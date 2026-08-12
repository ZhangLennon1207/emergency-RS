import json
import unittest

from src.postprocess_minimal_check import (
    postprocess_minimal_check,
)


class PostprocessTest(
    unittest.TestCase
):

    def setUp(self):
        self.result = {
            "schema_version":
                "3.1",

            "scene_uid":
                "S0001",

            "claim_id":
                "C000001",

            "claim_type":
                "building_damage_presence",

            "support_status":
                "supported",

            "evidence_ids":
                ["B0001"],

            "reason":
                "Evidence supports the claim.",

            "suggested_revision":
                "",

            "second_check": {
                "required":
                    False,

                "trigger_reasons":
                    [],

                "recommended_inputs":
                    [],

                "recommended_next_step":
                    "",
            },

            "human_review_state":
                "unreviewed",
        }

    def test_strict_json(self):
        raw = json.dumps(
            self.result
        )

        parsed = (
            postprocess_minimal_check(
                raw
            )
        )

        self.assertTrue(
            parsed[
                "strict_json"
            ]
        )

    def test_markdown_recovery(self):
        raw = (
            "```json\n"
            + json.dumps(
                self.result
            )
            + "\n```"
        )

        parsed = (
            postprocess_minimal_check(
                raw
            )
        )

        self.assertEqual(
            parsed[
                "verification"
            ][
                "support_status"
            ],
            "supported",
        )

    def test_repairs_only_truncated_suffix(self):
        raw = json.dumps(self.result)[:-1]
        parsed = postprocess_minimal_check(raw)
        self.assertEqual(parsed["verification"], self.result)

    def test_rejects_legacy_field_drift(self):
        legacy = dict(self.result)
        legacy["structured_evidence"] = []
        with self.assertRaises(Exception):
            postprocess_minimal_check(json.dumps(legacy))

    def test_repairs_known_support_status_typo(self):
        typo = dict(self.result)
        typo["supported_status"] = typo.pop("support_status")
        parsed = postprocess_minimal_check(json.dumps(typo))
        self.assertEqual(parsed["verification"]["support_status"], "supported")
        self.assertNotIn("supported_status", parsed["verification"])

    def test_restores_only_missing_second_check_constant(self):
        missing = dict(self.result)
        missing.pop("second_check")
        parsed = postprocess_minimal_check(json.dumps(missing))["verification"]
        self.assertEqual(
            parsed["second_check"],
            {"required": False, "trigger_reasons": [],
             "recommended_inputs": [], "recommended_next_step": ""},
        )

    def test_rejects_supported_with_zero_affected_pixels(self):
        inconsistent = dict(self.result)
        inconsistent["reason"] = "The road layer reports 0 affected pixels."
        with self.assertRaises(Exception):
            postprocess_minimal_check(json.dumps(inconsistent))


if __name__ == "__main__":
    unittest.main()
