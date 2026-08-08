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


if __name__ == "__main__":
    unittest.main()
